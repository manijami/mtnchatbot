import mongoose from 'mongoose';
import { FileContext } from 'librechat-data-provider';
import { MongoMemoryServer } from 'mongodb-memory-server';
import { createMethods, createModels } from '@librechat/data-schemas';
import type { IMongoFile } from '@librechat/data-schemas';
import type { MCPFileOutputDeps } from './mcpOutputs';
import { persistMCPFileOutput, takeMCPFileOutputs, isMCPToolName } from './mcpOutputs';
import { MCP_FILE_OUTPUTS_ARTIFACT_KEY } from '~/mcp/fileOutputs';

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const docxBytes = Buffer.concat([
  Buffer.from([0x50, 0x4b, 0x03, 0x04]),
  Buffer.alloc(26),
  Buffer.from('[Content_Types].xml', 'latin1'),
]);

let mongo: MongoMemoryServer;
let File: mongoose.Model<IMongoFile>;
let methods: ReturnType<typeof createMethods>;

const owner = new mongoose.Types.ObjectId().toString();
const other = new mongoose.Types.ObjectId().toString();
const req = { user: { id: owner, tenantId: undefined }, config: { fileStrategy: 'local' } };

function makeDeps(overrides: Partial<MCPFileOutputDeps> = {}) {
  const stored = new Map<string, Buffer>();
  const saveBuffer = jest.fn(async ({ userId, fileName, buffer }) => {
    const filepath = `/uploads/${userId}/${fileName}`;
    stored.set(filepath, buffer);
    return filepath;
  });
  const deleteFile = jest.fn(async (_req: never, file: { filepath: string }) => {
    stored.delete(file.filepath);
  });
  const deps: MCPFileOutputDeps = {
    getFileStrategy: () => 'local',
    getStrategyFunctions: () => ({ saveBuffer, deleteFile }),
    createFile: (data, disableTTL) => methods.createFile(data as never, disableTTL),
    findFileById: (id) => methods.findFileById(id),
    getRetentionExpiry: async () => ({ expiredAt: new Date('2030-01-01T00:00:00Z') }),
    logger: { error: jest.fn(), warn: jest.fn() },
    ...overrides,
  };
  return { deps, stored, saveBuffer, deleteFile };
}

beforeAll(async () => {
  mongo = await MongoMemoryServer.create();
  createModels(mongoose);
  await mongoose.connect(mongo.getUri());
  File = mongoose.models.File as mongoose.Model<IMongoFile>;
  methods = createMethods(mongoose);
}, 30_000);

afterAll(async () => {
  await mongoose.disconnect();
  await mongo.stop();
});

beforeEach(async () => {
  await File.deleteMany({});
});

describe('persistMCPFileOutput', () => {
  const file = {
    filename: 'plan.docx',
    mimeType: DOCX,
    bytes: docxBytes.byteLength,
    data: docxBytes.toString('base64'),
  };

  it('saves a user-owned file record through the storage strategy', async () => {
    const { deps, stored, saveBuffer } = makeDeps();
    const saved = await persistMCPFileOutput({ req, file }, deps);
    expect(saved).toEqual(
      expect.objectContaining({
        filename: 'plan.docx',
        type: DOCX,
        bytes: docxBytes.byteLength,
        context: FileContext.mcp_output,
        source: 'local',
      }),
    );
    expect(saveBuffer).toHaveBeenCalledWith(expect.objectContaining({ userId: owner }));
    expect([...stored.values()][0].equals(docxBytes)).toBe(true);

    const [record] = (await methods.getFiles({ file_id: saved!.file_id as string })) ?? [];
    expect(String(record.user)).toBe(owner);
    expect(record.context).toBe(FileContext.mcp_output);
    expect(record.expiredAt).toEqual(new Date('2030-01-01T00:00:00Z'));
    /* disableTTL: no 1-hour TTL index expiry, like other saved attachments. */
    expect(record.expiresAt).toBeUndefined();
  });

  it("appears in the owner's file list and never in another user's", async () => {
    const { deps } = makeDeps();
    await persistMCPFileOutput({ req, file }, deps);
    expect(await methods.getFiles({ user: owner })).toHaveLength(1);
    expect(await methods.getFiles({ user: other })).toHaveLength(0);
  });

  it('re-validates the signature and size before saving anything', async () => {
    const { deps, saveBuffer } = makeDeps();
    const fake = { ...file, data: Buffer.from('<html/>').toString('base64') };
    expect(await persistMCPFileOutput({ req, file: fake }, deps)).toBeNull();
    const tight = { ...req, config: { fileConfig: { serverFileSizeLimit: 10 } } };
    expect(await persistMCPFileOutput({ req: tight, file }, deps)).toBeNull();
    expect(saveBuffer).not.toHaveBeenCalled();
    expect(await File.countDocuments()).toBe(0);
  });

  it('removes the stored object when the record write fails', async () => {
    const failing = jest.fn().mockRejectedValue(new Error('db down'));
    const { deps, stored, deleteFile } = makeDeps({ createFile: failing });
    await expect(persistMCPFileOutput({ req, file }, deps)).rejects.toThrow('db down');
    expect(deleteFile).toHaveBeenCalled();
    expect(stored.size).toBe(0);
  });
});

describe('takeMCPFileOutputs', () => {
  const files = [{ filename: 'a.docx', mimeType: DOCX, bytes: 3, data: 'AAAA' }];

  it('returns files for MCP tools and strips the bytes from the artifact', () => {
    const artifact: Record<string, unknown> = {
      [MCP_FILE_OUTPUTS_ARTIFACT_KEY]: { serverName: 'mtn-office', files },
    };
    expect(takeMCPFileOutputs('create_word_document_mcp_mtn-office', artifact)).toEqual(files);
    expect(JSON.stringify(artifact)).not.toContain('AAAA');
    expect(artifact[MCP_FILE_OUTPUTS_ARTIFACT_KEY]).toEqual({
      serverName: 'mtn-office',
      files: [{ filename: 'a.docx', mimeType: DOCX, bytes: 3 }],
    });
  });

  it('returns nothing for non-MCP tools, whatever their artifact claims', () => {
    const artifact: Record<string, unknown> = {
      [MCP_FILE_OUTPUTS_ARTIFACT_KEY]: { serverName: 'x', files },
    };
    expect(isMCPToolName('web_search')).toBe(false);
    expect(takeMCPFileOutputs('web_search', artifact)).toEqual([]);
    expect(JSON.stringify(artifact)).not.toContain('AAAA');
    expect(takeMCPFileOutputs('anything', undefined)).toEqual([]);
  });
});
