// Code Execution Tool - Real implementation using isolated-vm sandbox
import { Tool, ToolCall, ToolResult } from '../../types';
import * as vm from 'isolated-vm';

export const codeExecutionTool: Tool = {
  name: 'code_execution',
  description: 'Execute JavaScript code in a sandboxed environment with resource limits and timeout.',
};

interface CodeExecutionArgs {
  code: string;
  language?: string;
  timeout_ms?: number;
}

export async function executeCode(args: Record<string, unknown>, toolCallId: string): Promise<ToolResult> {
  const { code, language = 'javascript', timeout_ms = 5000 } = args as CodeExecutionArgs;
  
  if (!code || typeof code !== 'string') {
    return {
      tool_call_id: toolCallId,
      result: JSON.stringify({ error: 'Code is required' }),
      success: false,
      error: 'Code is required',
      content: JSON.stringify({ error: 'Code is required' }),
    };
  }

  if (language !== 'javascript') {
    return {
      tool_call_id: toolCallId,
      result: JSON.stringify({ error: `Language '${language}' is not supported. Only JavaScript is supported.` }),
      success: false,
      error: `Language '${language}' is not supported`,
      content: JSON.stringify({ error: `Language '${language}' is not supported` }),
    };
  }

  let isolate: vm.Isolate | null = null;
  let context: vm.Context | null = null;
  
  try {
    // Create isolate with memory limit
    isolate = new vm.Isolate({ memoryLimit: 128 }); // 128MB limit
    
    // Create context
    context = await isolate.createContext();
    
    // Set up console capture
    const logs: string[] = [];
    const errors: string[] = [];
    
    await context.global.set('console', {
      log: (...args: any[]) => {
        logs.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '));
      },
      error: (...args: any[]) => {
        errors.push(args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '));
      },
      warn: (...args: any[]) => {
        logs.push('[WARN] ' + args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' '));
      },
    });

    // Compile the code
    const script = await isolate.compileScript(code);
    
    // Execute with timeout
    await script.run(context, { timeout: timeout_ms });
    
    const result = {
      success: true,
      logs,
      errors,
      output: logs.join('\n'),
    };

    return {
      tool_call_id: toolCallId,
      result: JSON.stringify(result),
      success: true,
      content: JSON.stringify(result),
    };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    
    // Check for timeout
    if (errorMessage.includes('Script execution timed out')) {
      return {
        tool_call_id: toolCallId,
        result: JSON.stringify({ error: 'Code execution timed out', timeout_ms }),
        success: false,
        error: 'Code execution timed out',
        content: JSON.stringify({ error: 'Code execution timed out', timeout_ms }),
      };
    }
    
    return {
      tool_call_id: toolCallId,
      result: JSON.stringify({ error: errorMessage }),
      success: false,
      error: errorMessage,
      content: JSON.stringify({ error: errorMessage }),
    };
  } finally {
    // Clean up
    if (context) {
      context.release();
    }
    if (isolate) {
      isolate.dispose();
    }
  }
}