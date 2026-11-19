/**
 * MCP file outputs from a subagent's tool call (Phase 4 checkpoint item 5).
 *
 * A subagent's tool calls run through the parent's ON_TOOL_EXECUTE handler, which hands the
 * result to the parent's tool-end callback. These tests drive the real handler and check that:
 * the file reaches the callback (delivered the same way as a parent call), it is assigned to the
 * parent response via `executionContext.rootRunId`, and the artifact returned to the agent run
 * (and so to message history) no longer carries the base64 bytes.
 */
import type {
  ToolCallRequest,
  ToolExecuteBatchRequest,
  ToolExecuteResult,
} from '@librechat/agents';
import type { ToolExecuteOptions } from '~/agents/handlers';
import { resolveMCPFileOutputMessageId, takeMCPFileOutputs } from './mcpOutputs';
import { createToolExecuteHandler } from '~/agents/handlers';

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const BLOB = Buffer.concat([
  Buffer.from([0x50, 0x4b, 0x03, 0x04]),
  Buffer.alloc(26),
  Buffer.from('[Content_Types].xml', 'latin1'),
]).toString('base64');
const TOOL = 'create_word_document_mcp_mtn-office';

function mcpTool() {
  return {
    name: TOOL,
    invoke: jest.fn(async () => ({
      content: 'Generated file "plan.docx" (1 KB) is attached to this message for the user.',
      artifact: {
        mcp_file_outputs: {
          serverName: 'mtn-office',
          files: [{ filename: 'plan.docx', mimeType: DOCX, bytes: 49, data: BLOB }],
        },
      },
    })),
  };
}

/** Mirrors the /api tool-end wiring: take the files (stripping bytes) and record where they go. */
function recordingCallback() {
  const delivered: Array<{ filename: string; messageId?: string; hadData: boolean }> = [];
  const callback = jest.fn(
    async (
      data: { output: { name: string; artifact?: Record<string, unknown> } },
      metadata: unknown,
    ) => {
      for (const file of takeMCPFileOutputs(data.output.name, data.output.artifact)) {
        delivered.push({
          filename: file.filename,
          messageId: resolveMCPFileOutputMessageId(metadata),
          hadData: typeof file.data === 'string' && file.data.length > 0,
        });
      }
    },
  );
  return { callback, delivered };
}

function run(
  handler: ReturnType<typeof createToolExecuteHandler>,
  extra: Record<string, unknown>,
): Promise<ToolExecuteResult[]> {
  return new Promise((resolve, reject) => {
    const toolCalls: ToolCallRequest[] = [{ id: 'call_doc', name: TOOL, args: { title: 'Plan' } }];
    handler.handle('on_tool_execute', {
      toolCalls,
      resolve,
      reject,
      ...extra,
    } as ToolExecuteBatchRequest);
  });
}

describe('MCP file outputs from subagent tool calls', () => {
  const loadTools: ToolExecuteOptions['loadTools'] = jest.fn(async () => ({
    loadedTools: [mcpTool()] as never[],
  }));

  it('delivers a subagent file to the parent response and returns no bytes to the run', async () => {
    const { callback, delivered } = recordingCallback();
    const handler = createToolExecuteHandler({ loadTools, toolEndCallback: callback as never });

    const [result] = await run(handler, {
      metadata: { run_id: 'child-run', thread_id: 'convo-1' },
      executionContext: {
        rootRunId: 'parent-run',
        hookSessionId: 'parent-run',
        depth: 1,
        ancestry: [],
      },
    });

    expect(callback).toHaveBeenCalledTimes(1);
    expect(delivered).toEqual([{ filename: 'plan.docx', messageId: 'parent-run', hadData: true }]);
    /* What the subagent run (and so message history) keeps: metadata only, no base64. */
    expect(JSON.stringify(result)).not.toContain(BLOB);
    expect(JSON.stringify(result.artifact)).toContain('plan.docx');
  });

  it('keeps the run id for a parent (non-subagent) tool call', async () => {
    const { callback, delivered } = recordingCallback();
    const handler = createToolExecuteHandler({ loadTools, toolEndCallback: callback as never });

    const [result] = await run(handler, {
      metadata: { run_id: 'parent-run', thread_id: 'convo-1' },
    });

    expect(delivered).toEqual([{ filename: 'plan.docx', messageId: 'parent-run', hadData: true }]);
    expect(JSON.stringify(result)).not.toContain(BLOB);
  });

  it('resolves the message id from metadata', () => {
    expect(
      resolveMCPFileOutputMessageId({ run_id: 'r', executionContext: { rootRunId: 'root' } }),
    ).toBe('root');
    expect(resolveMCPFileOutputMessageId({ run_id: 'r', executionContext: null })).toBe('r');
    expect(
      resolveMCPFileOutputMessageId({ run_id: 'r', executionContext: { rootRunId: '' } }),
    ).toBe('r');
    expect(resolveMCPFileOutputMessageId(undefined)).toBeUndefined();
  });
});
