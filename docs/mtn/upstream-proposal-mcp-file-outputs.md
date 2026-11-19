# Upstream proposal: opt-in MCP file outputs

**Status:** implemented in the MTN fork (`mtn/phase4-office`), proposed for upstream LibreChat to
remove fork drift. Base: `v0.8.9-rc1-84-gf4154b649`.

## Problem

An MCP tool cannot give the user a generated file. `packages/api/src/mcp/parsers.ts` turns an
embedded `resource` whose `blob` is not an image into the text `Resource Content: N bytes of
binary data (omitted; not UTF-8 text)`. The bytes are discarded, and the model is told a file
exists that nobody can download.

LibreChat already persists tool outputs as user-owned files in two cases: image artifacts
(`saveBase64Image`) and Code Interpreter outputs (`processCodeOutput`). Document-generating MCP
servers (Word, PowerPoint, Excel, PDF) have no equivalent. Workarounds all have problems:
- links to the MCP server need it to be publicly reachable and to run its own authentication;
- MCP Apps with embedded base64 are not real LibreChat files;
- uploading through the files API needs a user token, which exists only for OIDC.

`upstream/dev` had no equivalent as of 2026-11-08.

## Design

**Config.** A new optional server field in `MCPOptionsSchema`, off by default:

```yaml
mcpServers:
  office:
    type: streamable-http
    url: http://office-mcp:8080/mcp
    fileOutputs:
      enabled: true                 # default false; absent = upstream behaviour
      mimeTypes: [ ... ]            # default: docx, pptx, xlsx, pdf
      maxBytes: 26214400            # default 25 MiB; hard cap MAX_MCP_FILE_OUTPUT_BYTES (50 MiB)
      maxFiles: 5                   # per tool result (max 20)
```

**Trust: librechat.yaml servers only.**
- The policy is read from `MCPServersRegistry.getYamlServerOptions(name)`, the startup snapshot of
  `getAppConfig({ baseOnly: true })`. It is never read from the merged per-request config, so a
  Config-tier (Admin Panel) override cannot switch it on.
- The resolved server must itself have `source === 'yaml'` and no `dbId`.
- User-added servers (`source: 'user'`), Config-tier servers (`'config'`) and Agent Plugins servers
  (`'plugin'`, which are merged into the startup map) never deliver files.
- `fileOutputs` is in `omitServerManagedFields`, so `MCPServerUserInputSchema` strips it from UI/API
  input, and it drops out of the schema-derived `MCP_USER_INPUT_FIELDS`.

**Extraction (`packages/api/src/mcp/fileOutputs.ts`).** In `MCPManager.callTool`, before
`formatToolContent`, each `resource` blob whose MIME type is in the allowlist is:
- decoded as strict base64;
- size- and count-checked;
- signature-checked: ZIP local header plus `[Content_Types].xml` for OOXML, `%PDF-` for PDF. Types
  the feature cannot verify are dropped from the allowlist.

It is then given a sanitised filename with the correct extension. The model receives one text line
(`Generated file "x.docx" (12 KB) is attached…`) or a rejection reason, never the bytes. Files ride
in the tool artifact under `mcp_file_outputs`. Error results and non-allowlisted types keep upstream
behaviour.

**Persistence (`packages/api/src/files/mcpOutputs.ts`).**
- `takeMCPFileOutputs` takes the files out of the artifact and strips their bytes in place, so
  graph state, background-task storage and history never retain base64.
- It returns nothing unless the tool name contains `Constants.mcp_delimiter`.
- `persistMCPFileOutput` re-validates signature and size (also against
  `fileConfig.serverFileSizeLimit`), then saves through the deployment's `fileStrategy`
  (`saveBuffer`).
- It creates the record with `createFile(…, disableTTL=true)`: `user: req.user.id`, `tenantId`,
  `context: FileContext.mcp_output`, plus retention `expiredAt` from `getRetentionExpiry`. It uses
  `withStoredUploadCleanup`, so a failed record write deletes the stored object.
- Files therefore get the normal ownership checks, appear in the user's Files list (which lists by
  `user` without a context filter), and follow chat retention. v0.8.9-rc1 has no per-user storage
  quota; when one lands, this path should call it like other uploads.

**Wiring (`/api`, ~75 lines).**
- `Files/process.js` exports `getMCPFileOutputDeps()` (`getFileStrategy`, `getStrategyFunctions`,
  `createFile`, `findFileById`, `getRetentionExpiry`, `logger`).
- `createToolEndCallback` and `createResponsesToolEndCallback` add a loop that persists each file and
  emits it with the same attachment events as tool images. The loop does not `return`, so image
  artifacts (such as previews) in the same result are still processed.

## Subagents

A subagent's tool calls run through the parent's `ON_TOOL_EXECUTE` handler, so the same policy
(`MCPManager.callTool`) and the same tool-end callback apply: files are delivered the same way.
The child run reports its own `run_id`, so the attachment's `messageId` comes from
`executionContext.rootRunId` (the parent response) when present
(`resolveMCPFileOutputMessageId`). Bytes are stripped from the artifact before the result returns
to the run, so no base64 reaches message history in either case.

## Tests

| Suite | What it proves |
|---|---|
| `packages/api/src/mcp/__tests__/fileOutputs.test.ts` (16) | Off by default. YAML-only. User, DB, Config-tier and plugin servers refused. The YAML snapshot beats overlays. User input is stripped. Signature, size, base64 and count checks. Filename sanitising (`../` traversal). Bytes never reach the model text. |
| `packages/api/src/mcp/__tests__/MCPManager.test.ts` › `callTool - MCP file outputs` (4) | End to end through `callTool`: a YAML server attaches; user, Config-tier, plugin and "override adds the field" do not. |
| `packages/api/src/files/mcpOutputs.database.spec.ts` (6, mongodb-memory-server) | Real `createFile`: owner, context and retention stored. Visible to the owner, not to another user. Bad files never reach storage. Stored object removed when the record write fails. Bytes stripped. Non-MCP tools ignored. |
| `api/server/controllers/agents/__tests__/callbacks.spec.js` › `MCP file outputs` (3) | Wiring: an attachment is emitted with message, tool-call and conversation IDs; a subagent's file is attached to the parent response; non-MCP tool payloads are ignored. |
| `packages/api/src/files/mcpOutputs.subagent.spec.ts` (3) | Through the real `createToolExecuteHandler`: a subagent's MCP tool call reaches the tool-end callback like a parent call, its file is assigned to `executionContext.rootRunId` (the parent response), and the result returned to the agent run carries no base64. |

All 261 existing `MCPManager` tests and 51 existing callbacks tests still pass unchanged. The call
uses `registry.getYamlServerOptions?.()`, so partial registry stubs keep working, and a missing
snapshot means files stay off.

## Open questions for upstream

- A per-user storage quota hook, when quota support lands.
- Whether `mcp_output` files should also be offered as context to later turns (currently they are
  attachments only).
- Whether to let operators extend the signature table (for example CSV, which has no magic number).
