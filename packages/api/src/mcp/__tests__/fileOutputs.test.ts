import { MCPServerUserInputSchema, MCPOptionsSchema } from 'librechat-data-provider';
import type * as t from '~/mcp/types';
import {
  MCP_FILE_OUTPUTS_ARTIFACT_KEY,
  DEFAULT_MCP_FILE_OUTPUT_MAX_BYTES,
  attachMCPFileOutputs,
  deriveMCPOutputFilename,
  extractMCPFileOutputs,
  hasExpectedSignature,
  resolveMCPFileOutputPolicy,
} from '~/mcp/fileOutputs';

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const PDF = 'application/pdf';

/** Smallest byte string that passes the OOXML signature check (ZIP local header + manifest name). */
const ooxmlBytes = (extra = 0) =>
  Buffer.concat([
    Buffer.from([0x50, 0x4b, 0x03, 0x04]),
    Buffer.alloc(26),
    Buffer.from('[Content_Types].xml', 'latin1'),
    Buffer.alloc(extra),
  ]);

const resource = (blob: string, mimeType = DOCX, uri = 'file:///out/report.docx') =>
  ({ type: 'resource', resource: { uri, mimeType, blob } }) as t.ToolContentPart;

const enabledYaml = {
  type: 'streamable-http',
  url: 'http://office-mcp:8080/mcp',
  fileOutputs: { enabled: true },
};

describe('resolveMCPFileOutputPolicy', () => {
  it('enables only librechat.yaml servers that opt in', () => {
    const policy = resolveMCPFileOutputPolicy({ ...enabledYaml, source: 'yaml' }, enabledYaml);
    expect(policy).not.toBeNull();
    expect(policy!.maxBytes).toBe(DEFAULT_MCP_FILE_OUTPUT_MAX_BYTES);
    expect([...policy!.mimeTypes]).toEqual(expect.arrayContaining([DOCX, XLSX, PDF]));
  });

  it('is off by default (field absent or enabled: false)', () => {
    const { fileOutputs: _omit, ...plain } = enabledYaml;
    expect(resolveMCPFileOutputPolicy({ ...plain, source: 'yaml' }, plain)).toBeNull();
    const disabled = { ...plain, fileOutputs: { enabled: false } };
    expect(resolveMCPFileOutputPolicy({ ...disabled, source: 'yaml' }, disabled)).toBeNull();
  });

  it('never enables user-added (UI/DB) servers, even when they set the field', () => {
    const userServer = { ...enabledYaml, source: 'user' };
    expect(resolveMCPFileOutputPolicy(userServer, enabledYaml)).toBeNull();
    expect(resolveMCPFileOutputPolicy(userServer, undefined)).toBeNull();
    /* A DB-backed entry is user-authored even if a source tag is missing or spoofed. */
    expect(
      resolveMCPFileOutputPolicy({ ...enabledYaml, source: 'yaml', dbId: 'x' }, enabledYaml),
    ).toBeNull();
  });

  it('never enables Config-tier (admin override) or Agent Plugins servers', () => {
    expect(resolveMCPFileOutputPolicy({ ...enabledYaml, source: 'config' }, undefined)).toBeNull();
    const pluginRaw = { ...enabledYaml, source: 'plugin' };
    expect(resolveMCPFileOutputPolicy({ ...enabledYaml, source: 'plugin' }, pluginRaw)).toBeNull();
    expect(resolveMCPFileOutputPolicy({ ...enabledYaml, source: 'yaml' }, pluginRaw)).toBeNull();
  });

  it('reads the policy from the librechat.yaml snapshot, not from an overlaid config', () => {
    const { fileOutputs: _omit, ...yamlWithout } = enabledYaml;
    /* An override that adds `fileOutputs` to a yaml server must not switch it on. */
    expect(resolveMCPFileOutputPolicy({ ...enabledYaml, source: 'yaml' }, yamlWithout)).toBeNull();
  });

  it('drops types it cannot verify and caps maxBytes', () => {
    const yaml = {
      ...enabledYaml,
      fileOutputs: { enabled: true, mimeTypes: ['text/plain', XLSX], maxBytes: 1024 },
    };
    const policy = resolveMCPFileOutputPolicy({ ...yaml, source: 'yaml' }, yaml)!;
    expect([...policy.mimeTypes]).toEqual([XLSX]);
    expect(policy.maxBytes).toBe(1024);
    const unverifiable = {
      ...enabledYaml,
      fileOutputs: { enabled: true, mimeTypes: ['text/plain'] },
    };
    expect(
      resolveMCPFileOutputPolicy({ ...unverifiable, source: 'yaml' }, unverifiable),
    ).toBeNull();
  });
});

describe('config schema', () => {
  it('accepts fileOutputs in librechat.yaml and defaults enabled to false', () => {
    const parsed = MCPOptionsSchema.parse({
      type: 'streamable-http',
      url: 'http://x/mcp',
      fileOutputs: {},
    });
    expect(parsed.fileOutputs).toEqual({ enabled: false });
  });

  it('strips fileOutputs from user-submitted server definitions', () => {
    const parsed = MCPServerUserInputSchema.parse({
      type: 'streamable-http',
      url: 'https://example.com/mcp',
      fileOutputs: { enabled: true },
    });
    expect(parsed).not.toHaveProperty('fileOutputs');
  });
});

describe('extractMCPFileOutputs', () => {
  const policy = resolveMCPFileOutputPolicy({ ...enabledYaml, source: 'yaml' }, enabledYaml)!;

  it('extracts a valid file and gives the model a text line instead of the bytes', () => {
    const blob = ooxmlBytes(10).toString('base64');
    const { result, files } = extractMCPFileOutputs(
      { content: [{ type: 'text', text: 'Done.' }, resource(blob)] },
      policy,
    );
    expect(files).toEqual([
      { filename: 'report.docx', mimeType: DOCX, bytes: ooxmlBytes(10).byteLength, data: blob },
    ]);
    const texts = result!.content!.map((part) => (part as { text?: string }).text);
    expect(texts[1]).toMatch(/Generated file "report.docx" .* attached to this message/);
    expect(JSON.stringify(result)).not.toContain(blob);
  });

  it('rejects a file whose bytes do not match the declared type', () => {
    const blob = Buffer.from('<html>not a docx</html>').toString('base64');
    const { result, files } = extractMCPFileOutputs({ content: [resource(blob)] }, policy);
    expect(files).toHaveLength(0);
    expect((result!.content![0] as { text: string }).text).toMatch(
      /does not match the declared file type/,
    );
  });

  it('rejects oversize files, invalid base64 and files beyond the count limit', () => {
    const small = { ...policy, maxBytes: 60, maxFiles: 1 };
    const big = resource(ooxmlBytes(100).toString('base64'));
    const bad = resource('***not-base64***');
    const ok = resource(ooxmlBytes().toString('base64'), DOCX, 'file:///a.docx');
    const extra = resource(ooxmlBytes().toString('base64'), DOCX, 'file:///b.docx');
    const { result, files } = extractMCPFileOutputs({ content: [big, bad, ok, extra] }, small);
    expect(files.map((f) => f.filename)).toEqual(['a.docx']);
    const texts = result!.content!.map((part) => (part as { text: string }).text);
    expect(texts[0]).toMatch(/larger than/);
    expect(texts[1]).toMatch(/not valid base64/);
    expect(texts[3]).toMatch(/limit of 1 files/);
  });

  it('leaves types outside the allowlist to the standard parser', () => {
    const png = {
      type: 'resource',
      resource: { uri: 'file:///x.png', mimeType: 'image/png', blob: 'AAAA' },
    };
    const { result, files } = extractMCPFileOutputs(
      { content: [png as t.ToolContentPart] },
      policy,
    );
    expect(files).toHaveLength(0);
    expect(result!.content![0]).toBe(png);
  });

  it('does nothing for error results', () => {
    const input = { isError: true, content: [resource(ooxmlBytes().toString('base64'))] };
    expect(extractMCPFileOutputs(input, policy)).toEqual({ result: input, files: [] });
  });
});

describe('helpers', () => {
  it('checks PDF and OOXML signatures', () => {
    expect(hasExpectedSignature(Buffer.from('%PDF-1.7\n'), PDF)).toBe(true);
    expect(hasExpectedSignature(Buffer.from('PK\x03\x04 but no manifest'), DOCX)).toBe(false);
    expect(hasExpectedSignature(ooxmlBytes(), DOCX)).toBe(true);
    expect(hasExpectedSignature(ooxmlBytes(), 'text/plain')).toBe(false);
  });

  it('checks PNG signatures (MTN: chart images)', () => {
    const png = Buffer.concat([
      Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
      Buffer.alloc(16),
    ]);
    expect(hasExpectedSignature(png, 'image/png')).toBe(true);
    expect(hasExpectedSignature(Buffer.from('GIF89a......'), 'image/png')).toBe(false);
  });

  it('accepts only static HTML documents (MTN: dashboards)', () => {
    const html = (body: string) => Buffer.from(`<!DOCTYPE html><html><body>${body}</body></html>`);
    expect(hasExpectedSignature(html('<h1>Dashboard</h1><svg><rect/></svg>'), 'text/html')).toBe(
      true,
    );
    expect(hasExpectedSignature(Buffer.from('\uFEFF<!doctype html><p>ok</p>'), 'text/html')).toBe(
      true,
    );
    for (const active of [
      '<script>alert(1)</script>',
      '<img src=x onerror=alert(1)>',
      '<a href="javascript:alert(1)">x</a>',
      '<iframe src="https://example.com"></iframe>',
      '<form action="/x"></form>',
      '<object data="x"></object>',
      '<meta http-equiv="refresh" content="0;url=https://example.com">',
    ]) {
      expect(hasExpectedSignature(html(active), 'text/html')).toBe(false);
    }
    expect(hasExpectedSignature(Buffer.from('<p>no doctype</p>'), 'text/html')).toBe(false);
  });

  it('keeps PNG and HTML out of the default allowlist (opt-in per server)', () => {
    const policy = resolveMCPFileOutputPolicy({ ...enabledYaml, source: 'yaml' }, enabledYaml);
    expect(policy?.mimeTypes.has('image/png')).toBe(false);
    expect(policy?.mimeTypes.has('text/html')).toBe(false);
  });

  it('derives a safe filename with the type extension', () => {
    expect(deriveMCPOutputFilename('file:///x/../../etc/passwd', DOCX)).toBe('passwd.docx');
    expect(deriveMCPOutputFilename('file:///out/Q3%20plan.xlsx', XLSX)).toMatch(/^Q3.plan\.xlsx$/);
    expect(deriveMCPOutputFilename(undefined, PDF)).toBe('output.pdf');
  });

  it('adds files to the artifact without touching the text', () => {
    const formatted: t.FormattedContentResult = ['text', undefined];
    const files = [{ filename: 'a.docx', mimeType: DOCX, bytes: 1, data: 'AA==' }];
    const [text, artifacts] = attachMCPFileOutputs(formatted, 'mtn-office', files);
    expect(text).toBe('text');
    expect(artifacts?.[MCP_FILE_OUTPUTS_ARTIFACT_KEY]).toEqual({ serverName: 'mtn-office', files });
    expect(attachMCPFileOutputs(formatted, 'mtn-office', [])).toBe(formatted);
  });
});
