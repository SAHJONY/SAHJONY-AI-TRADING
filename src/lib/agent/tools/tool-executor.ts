// Tool Executor - Real implementation
import { Tool, ToolCall, ToolResult } from '../types';
import { webSearchTool, executeWebSearch } from './builtin/web-search';
import { browserTool, executeBrowserAction } from './builtin/browser';
import { codeExecutionTool, executeCode } from './builtin/code-execution';
import { fileToolsTool, executeFileOperation } from './builtin/file-tools';

class ToolExecutorClass {
  private tools: Map<string, Tool> = new Map();
  private executors: Map<string, (args: Record<string, unknown>, toolCallId: string) => Promise<ToolResult>> = new Map();

  constructor() {
    this.registerTool(webSearchTool, executeWebSearch);
    this.registerTool(browserTool, executeBrowserAction);
    this.registerTool(codeExecutionTool, executeCode);
    this.registerTool(fileToolsTool, executeFileOperation);
  }

  private registerTool(tool: Tool, executor: (args: Record<string, unknown>, toolCallId: string) => Promise<ToolResult>) {
    this.tools.set(tool.name, tool);
    this.executors.set(tool.name, executor);
  }

  async executeToolCalls(toolCalls: ToolCall[], _context: any): Promise<ToolResult[]> {
    const results: ToolResult[] = [];

    for (const call of toolCalls) {
      try {
        const executor = this.executors.get(call.name);
        
        if (!executor) {
          results.push({
            tool_call_id: call.id,
            result: JSON.stringify({ error: `Tool '${call.name}' not found` }),
            success: false,
            error: `Tool '${call.name}' not found`,
            content: JSON.stringify({ error: `Tool '${call.name}' not found` }),
          });
          continue;
        }

        const result = await executor(call.arguments, call.id);
        results.push(result);
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        results.push({
          tool_call_id: call.id,
          result: JSON.stringify({ error: errorMessage }),
          success: false,
          error: errorMessage,
          content: JSON.stringify({ error: errorMessage }),
        });
      }
    }

    return results;
  }

  getEnabledTools(): Tool[] {
    return Array.from(this.tools.values());
  }

  getTool(name: string): Tool | undefined {
    return this.tools.get(name);
  }
}

export const toolExecutor = new ToolExecutorClass();
export { ToolExecutorClass };