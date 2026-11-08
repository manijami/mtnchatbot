/**
 * Persists MCP file outputs (see `mcp/fileOutputs.ts`) as ordinary user-owned LibreChat files.
 *
 * Saved through the deployment's `fileStrategy` and the same record/cleanup path as tool images,
 * so file access checks, retention and the user's Files list apply unchanged. `/api` supplies the
 * storage and database functions; all decisions live here.
 */
import { v4 } from 'uuid';
import { Constants, FileContext, MAX_MCP_FILE_OUTPUT_BYTES } from 'librechat-data-provider';
import type { MCPFileOutput, MCPFileOutputsArtifact } from '~/mcp/fileOutputs';
import type { StoredUploadRef } from './orphan';
import {
  MCP_FILE_OUTPUTS_ARTIFACT_KEY,
  deriveMCPOutputFilename,
  hasExpectedSignature,
} from '~/mcp/fileOutputs';
import { createRecordExists, withStoredUploadCleanup } from './orphan';
import { getStorageMetadata } from '~/storage/metadata';

type SaveBuffer = (params: {
  userId: string;
  fileName: string;
  buffer: Buffer;
  tenantId?: string;
}) => Promise<string>;

type DeleteFile = (req: never, file: StoredUploadRef) => Promise<unknown>;

export interface MCPFileOutputRequest {
  user: { id: string; tenantId?: string };
  config?: { fileStrategy?: string; fileConfig?: { serverFileSizeLimit?: number } } & Record<
    string,
    unknown
  >;
}

export interface MCPFileOutputDeps {
  /** Resolves the storage strategy for a non-image document (`getFileStrategy` in /api). */
  getFileStrategy: (appConfig: MCPFileOutputRequest['config']) => string;
  getStrategyFunctions: (source: string) => { saveBuffer?: SaveBuffer; deleteFile?: DeleteFile };
  createFile: (data: Record<string, unknown>, disableTTL?: boolean) => Promise<unknown>;
  findFileById: (id: string) => Promise<unknown>;
  getRetentionExpiry: (req: MCPFileOutputRequest) => Promise<Record<string, unknown> | undefined>;
  logger: { error: (message: string, meta?: unknown) => void; warn: (message: string) => void };
}

/** True for a tool name produced by an MCP server (`<tool>_mcp_<server>`). */
export function isMCPToolName(toolName: unknown): boolean {
  return typeof toolName === 'string' && toolName.includes(Constants.mcp_delimiter);
}

/**
 * Takes the MCP file outputs out of a tool artifact and strips their bytes from it in place, so
 * no base64 is retained by graph state, background-task storage or message history. Returns
 * nothing for non-MCP tools, whatever their artifact claims.
 */
export function takeMCPFileOutputs(
  toolName: unknown,
  artifact: Record<string, unknown> | undefined,
): MCPFileOutput[] {
  const payload = artifact?.[MCP_FILE_OUTPUTS_ARTIFACT_KEY] as MCPFileOutputsArtifact | undefined;
  if (!payload || !Array.isArray(payload.files)) {
    return [];
  }
  const files = payload.files;
  (artifact as Record<string, unknown>)[MCP_FILE_OUTPUTS_ARTIFACT_KEY] = {
    serverName: payload.serverName,
    files: files.map(({ filename, mimeType, bytes }) => ({ filename, mimeType, bytes })),
  };
  return isMCPToolName(toolName) ? files : [];
}

/**
 * Saves one MCP file output for the requesting user and returns the file record, or `null` when
 * the file fails re-validation. Re-checks type, signature and size here because the artifact
 * crossed the agent runtime between extraction and persistence.
 */
export async function persistMCPFileOutput(
  { req, file }: { req: MCPFileOutputRequest; file: MCPFileOutput },
  deps: MCPFileOutputDeps,
): Promise<Record<string, unknown> | null> {
  const buffer = Buffer.from(String(file?.data ?? ''), 'base64');
  const serverLimit = req.config?.fileConfig?.serverFileSizeLimit;
  const maxBytes = Math.min(MAX_MCP_FILE_OUTPUT_BYTES, serverLimit || MAX_MCP_FILE_OUTPUT_BYTES);
  if (!buffer.byteLength || buffer.byteLength > maxBytes) {
    deps.logger.warn(`[MCP file outputs] Rejected "${file?.filename}": size ${buffer.byteLength}`);
    return null;
  }
  if (!hasExpectedSignature(buffer, file.mimeType)) {
    deps.logger.warn(`[MCP file outputs] Rejected "${file?.filename}": signature mismatch`);
    return null;
  }
  const filename = deriveMCPOutputFilename(`file:///${file.filename}`, file.mimeType);
  const file_id = v4();
  const source = deps.getFileStrategy(req.config);
  const { saveBuffer } = deps.getStrategyFunctions(source);
  if (!saveBuffer) {
    throw new Error(`[MCP file outputs] Storage strategy "${source}" cannot save buffers`);
  }
  const filepath = await saveBuffer({
    userId: req.user.id,
    fileName: `${file_id}__${filename}`,
    buffer,
    tenantId: req.user.tenantId,
  });
  const storageMetadata = getStorageMetadata({ filepath, source });
  return withStoredUploadCleanup(
    {
      req,
      logger: deps.logger,
      trackWrite: true,
      recordExists: createRecordExists(deps.findFileById),
      resolveDeleteFile: () => deps.getStrategyFunctions(source).deleteFile,
      stored: { file_id, filepath, source, ...storageMetadata },
    },
    async (beginWrite) => {
      const retention = await deps.getRetentionExpiry(req);
      beginWrite();
      return (await deps.createFile(
        {
          file_id,
          filepath,
          filename,
          source,
          type: file.mimeType,
          bytes: buffer.byteLength,
          context: FileContext.mcp_output,
          user: req.user.id,
          tenantId: req.user.tenantId,
          ...storageMetadata,
          ...(retention ?? {}),
        },
        true,
      )) as Record<string, unknown>;
    },
  );
}
