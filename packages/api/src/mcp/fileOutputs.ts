/**
 * MCP file outputs: opt-in delivery of files that an MCP tool embeds in its result
 * (`resource` content with a base64 `blob`) as user-owned chat attachments.
 *
 * Upstream behaviour (unchanged when the feature is off): a non-image blob is summarised to the
 * model as "N bytes of binary data (omitted)", so an MCP tool cannot hand a generated .docx,
 * .pptx, .xlsx or .pdf to the user.
 *
 * Trust model:
 * - The policy is read ONLY from the librechat.yaml snapshot taken at startup
 *   (`MCPServersRegistry.getYamlServerOptions`), never from the merged per-request config, so a
 *   Config-tier override cannot switch it on.
 * - The resolved server must itself be a librechat.yaml server (`source === 'yaml'`). User-added
 *   servers (`source: 'user'` / `dbId`), Config-tier servers and Agent Plugins servers never
 *   deliver files, even when they carry the field.
 * - Every file is checked against a MIME allowlist, its file signature, a size cap and a count
 *   cap. The model only sees a short text line, never the bytes.
 */
import path from 'path';
import { MAX_MCP_FILE_OUTPUT_BYTES } from 'librechat-data-provider';
import type { TMCPFileOutputs, MCPOptions } from 'librechat-data-provider';
import type * as t from './types';
import { sanitizeFilename } from '~/utils/files';
import { isPluginSourced } from '~/utils/env';

/** Artifact key the tool-end callback reads; an MCP-tool-only, transient payload. */
export const MCP_FILE_OUTPUTS_ARTIFACT_KEY = 'mcp_file_outputs' as const;

export const DEFAULT_MCP_FILE_OUTPUT_MAX_BYTES: number = 25 * 1024 * 1024;
export const DEFAULT_MCP_FILE_OUTPUT_MAX_FILES: number = 5;

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const PPTX = 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const PDF = 'application/pdf';
const PNG = 'image/png';
const HTML = 'text/html';

/**
 * Types this feature can verify by signature, with the extension a saved file must carry.
 * A configured type outside this table is ignored: an unverifiable type is never saved.
 */
const SUPPORTED_TYPES: Readonly<
  Record<string, { ext: string; signature: 'zip' | 'pdf' | 'png' | 'html' }>
> = {
  [DOCX]: { ext: '.docx', signature: 'zip' },
  [PPTX]: { ext: '.pptx', signature: 'zip' },
  [XLSX]: { ext: '.xlsx', signature: 'zip' },
  [PDF]: { ext: '.pdf', signature: 'pdf' },
  /* MTN: chart images and dashboards (Excel insights). Opt-in per server via `mimeTypes`; not
   * in the default list. Downloads are served as `attachment` with `nosniff`. */
  [PNG]: { ext: '.png', signature: 'png' },
  [HTML]: { ext: '.html', signature: 'html' },
};

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
/** Anything that can run code or submit data; only static HTML is accepted. */
const ACTIVE_HTML =
  /<\s*(script|iframe|object|embed|form|meta\s+[^>]*http-equiv)|\son[a-z]+\s*=|javascript:|vbscript:/i;

/** True for a static HTML document: a doctype first, and no script, frames, forms or handlers. */
function isStaticHtml(bytes: Buffer): boolean {
  const text = bytes.toString('utf8').replace(/^\uFEFF/, '');
  return /^\s*<!doctype html>/i.test(text) && !ACTIVE_HTML.test(text);
}

export const DEFAULT_MCP_FILE_OUTPUT_MIME_TYPES: readonly string[] = [DOCX, PPTX, XLSX, PDF];

export interface MCPFileOutputPolicy {
  mimeTypes: ReadonlySet<string>;
  maxBytes: number;
  maxFiles: number;
}

export interface MCPFileOutput {
  filename: string;
  mimeType: string;
  bytes: number;
  /** Base64 file body. Transient: persisted by the tool-end callback, never shown to the model. */
  data: string;
}

export interface MCPFileOutputsArtifact {
  serverName: string;
  files: MCPFileOutput[];
}

/** Any server config (resolved or librechat.yaml snapshot); only these fields are read. */
type FileOutputsCarrier = Pick<MCPOptions, 'fileOutputs'> & {
  source?: string;
  dbId?: unknown;
  [key: string]: unknown;
};

/**
 * Resolves the file-output policy for a tool call, or `null` when files must not be delivered.
 *
 * @param resolvedConfig - The effective config the call runs with (may be overlaid).
 * @param yamlOptions - The librechat.yaml snapshot entry for the same server name.
 */
export function resolveMCPFileOutputPolicy(
  resolvedConfig: FileOutputsCarrier | undefined,
  yamlOptions: FileOutputsCarrier | undefined,
): MCPFileOutputPolicy | null {
  if (!resolvedConfig || !yamlOptions) {
    return null;
  }
  /* Only operator-declared librechat.yaml servers. A DB-backed entry is user-authored. */
  if (resolvedConfig.source !== 'yaml' || resolvedConfig.dbId != null) {
    return null;
  }
  /* Agent Plugins servers are merged into the startup snapshot; they are not operator-declared. */
  if (isPluginSourced(yamlOptions) || isPluginSourced(resolvedConfig)) {
    return null;
  }
  const declared: TMCPFileOutputs | undefined = yamlOptions.fileOutputs;
  if (declared?.enabled !== true) {
    return null;
  }
  const requested = declared.mimeTypes?.length
    ? declared.mimeTypes
    : DEFAULT_MCP_FILE_OUTPUT_MIME_TYPES;
  const mimeTypes = new Set(
    requested.map((type) => type.trim().toLowerCase()).filter((type) => type in SUPPORTED_TYPES),
  );
  if (mimeTypes.size === 0) {
    return null;
  }
  return {
    mimeTypes,
    maxBytes: Math.min(
      declared.maxBytes ?? DEFAULT_MCP_FILE_OUTPUT_MAX_BYTES,
      MAX_MCP_FILE_OUTPUT_BYTES,
    ),
    maxFiles: declared.maxFiles ?? DEFAULT_MCP_FILE_OUTPUT_MAX_FILES,
  };
}

const BASE64_PATTERN = /^[A-Za-z0-9+/]*={0,2}$/;

/** Decodes strict base64 (whitespace tolerated); returns null for anything else. */
function decodeBase64(blob: string): Buffer | null {
  const compact = blob.replace(/[\t\n\f\r ]/g, '');
  if (compact.length === 0 || compact.length % 4 !== 0 || !BASE64_PATTERN.test(compact)) {
    return null;
  }
  return Buffer.from(compact, 'base64');
}

/** True when the bytes carry the signature the declared type requires. */
export function hasExpectedSignature(bytes: Buffer, mimeType: string): boolean {
  const kind = SUPPORTED_TYPES[mimeType]?.signature;
  if (kind === 'pdf') {
    return bytes.subarray(0, 5).toString('latin1') === '%PDF-';
  }
  if (kind === 'png') {
    return bytes.length > PNG_SIGNATURE.length && bytes.subarray(0, 8).equals(PNG_SIGNATURE);
  }
  if (kind === 'html') {
    return isStaticHtml(bytes);
  }
  if (kind === 'zip') {
    /* OOXML is a ZIP package whose first entry is conventionally [Content_Types].xml. */
    return (
      bytes.length > 30 &&
      bytes[0] === 0x50 &&
      bytes[1] === 0x4b &&
      bytes[2] === 0x03 &&
      bytes[3] === 0x04 &&
      bytes.includes(Buffer.from('[Content_Types].xml', 'latin1'))
    );
  }
  return false;
}

/** Derives a safe display filename from the resource URI, forcing the type's extension. */
export function deriveMCPOutputFilename(uri: string | undefined, mimeType: string): string {
  const ext = SUPPORTED_TYPES[mimeType]?.ext ?? '';
  let candidate = '';
  if (uri) {
    try {
      candidate = decodeURIComponent(new URL(uri).pathname.split('/').pop() ?? '');
    } catch {
      candidate = uri.split(/[\\/]/).pop() ?? '';
    }
  }
  let name = sanitizeFilename(candidate || `output${ext}`);
  if (path.extname(name).toLowerCase() !== ext) {
    name = `${path.basename(name, path.extname(name)) || 'output'}${ext}`;
  }
  return name;
}

function formatSize(bytes: number): string {
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/**
 * Pulls admissible file blobs out of a tool result. Each extracted item is replaced by a short
 * text part for the model; a rejected file gets a text part with the reason, and an item whose
 * type is not in the allowlist is left for the standard parser (upstream behaviour).
 */
export function extractMCPFileOutputs(
  result: t.MCPToolCallResponse,
  policy: MCPFileOutputPolicy,
): { result: t.MCPToolCallResponse; files: MCPFileOutput[] } {
  if (!result?.content?.length || result.isError === true) {
    return { result, files: [] };
  }
  const files: MCPFileOutput[] = [];
  const content: t.ToolContentPart[] = [];
  for (const item of result.content) {
    if (item.type !== 'resource' || !item.resource || !('blob' in item.resource)) {
      content.push(item);
      continue;
    }
    const resource = item.resource;
    const mimeType = (resource.mimeType ?? '').trim().toLowerCase();
    if (!policy.mimeTypes.has(mimeType) || typeof resource.blob !== 'string') {
      content.push(item);
      continue;
    }
    const filename = deriveMCPOutputFilename(resource.uri, mimeType);
    const reject = (reason: string) =>
      content.push({ type: 'text', text: `File "${filename}" was not attached: ${reason}.` });
    if (files.length >= policy.maxFiles) {
      reject(`limit of ${policy.maxFiles} files per tool result reached`);
      continue;
    }
    const bytes = decodeBase64(resource.blob);
    if (!bytes) {
      reject('the file data is not valid base64');
      continue;
    }
    if (bytes.byteLength > policy.maxBytes) {
      reject(`it is larger than the ${formatSize(policy.maxBytes)} limit`);
      continue;
    }
    if (!hasExpectedSignature(bytes, mimeType)) {
      reject('its content does not match the declared file type');
      continue;
    }
    files.push({ filename, mimeType, bytes: bytes.byteLength, data: bytes.toString('base64') });
    content.push({
      type: 'text',
      text: `Generated file "${filename}" (${formatSize(bytes.byteLength)}) is attached to this message for the user.`,
    });
  }
  return { result: { ...result, content }, files };
}

/** Adds extracted files to a formatted tool response's artifacts. */
export function attachMCPFileOutputs(
  formatted: t.FormattedContentResult,
  serverName: string,
  files: MCPFileOutput[],
): t.FormattedContentResult {
  if (!files.length) {
    return formatted;
  }
  const [text, artifacts] = formatted;
  const payload: MCPFileOutputsArtifact = { serverName, files };
  return [text, { ...(artifacts ?? {}), [MCP_FILE_OUTPUTS_ARTIFACT_KEY]: payload }];
}
