// Unified Brain - Hermes Agent delegates to Freebuff for coding tasks
// This is the single brain architecture where Hermes is the main reasoning engine
// and Freebuff is available as a delegatable tool for coding tasks
import { Message, ModelConfig, ToolCall } from './types';
import { HermesBridge } from './hermes-bridge';
import { freebuffAgent, FreebuffAgent } from './freebuff-integration';
import { contextEngine } from './memory';
import { toolExecutor } from './tools';
import { isCodingTask } from './utils';

// Hermes Bridge singleton instance - created directly to avoid module resolution issues
const hermesBridge = new HermesBridge({
  hermesUrl: process.env.HERMES_AGENT_URL || 'http://localhost:8000',
  apiKey: process.env.HERMES_AGENT_API_KEY || '',
  timeoutMs: 60000,
});

export interface UnifiedBrainConfig {
  hermesUrl?: string;
  hermesApiKey?: string;
  freebuffUrl?: string;
  enableFreebuff?: boolean;
  enableHermes?: boolean;
}

interface ToolExecutionResult {
  success: boolean;
  result: string;
  error?: string;
}

/**
 * Unified Brain Architecture:
 * 
 * User Message → Unified Brain
 *                      ↓
 *              [Check if Hermes available]
 *                      ↓
 *         ┌─────────────────────────────┐
 *         ↓                             ↓
 *    [Hermes available]            [Hermes unavailable]
 *         ↓                             ↓
 *    Call Hermes Agent            Use local fallback
 *         ↓
 *    [Parse tool calls in response]
 *         ↓
 *    [Execute tool (e.g., Freebuff)]
 *         ↓
 *    [Add result to context, get final response]
 *         ↓
 *    Return to user
 */
export class UnifiedBrain {
  private config: UnifiedBrainConfig;
  private freebuffAgent: FreebuffAgent;
  private useHermes: boolean;
  private useFreebuff: boolean;

  constructor(config: UnifiedBrainConfig = {}) {
    this.config = {
      hermesUrl: config.hermesUrl || process.env.HERMES_AGENT_URL,
      hermesApiKey: config.hermesApiKey || process.env.HERMES_AGENT_API_KEY,
      freebuffUrl: config.freebuffUrl || process.env.FREEBUFF_API_URL,
      enableFreebuff: config.enableFreebuff !== false,
      enableHermes: config.enableHermes !== false,
    };
    
    this.freebuffAgent = freebuffAgent;
    this.useHermes = !!this.config.hermesUrl;
    this.useFreebuff = Boolean(this.config.enableFreebuff) && Boolean(this.config.enableHermes);
    
    console.log('[UnifiedBrain] Initialized with config:', {
      useHermes: this.useHermes,
      useFreebuff: this.useFreebuff,
      hermesUrl: this.config.hermesUrl,
    });
  }

  /**
   * Process a message through the unified brain
   * Handles tool calls from Hermes and delegates to appropriate handlers
   */
  async process(
    userMessage: string,
    messages: Message[] = [],
    modelConfig?: ModelConfig
  ): Promise<string> {
    console.log('[UnifiedBrain] Processing message, history length:', messages.length);

    if (this.useHermes) {
      return this.processWithHermes(userMessage, messages, modelConfig);
    }

    return this.processWithoutHermes(userMessage, messages, modelConfig);
  }

  /**
   * Process with Hermes as the main brain
   * Parse and execute tool calls (including Freebuff)
   */
  private async processWithHermes(
    userMessage: string,
    messages: Message[],
    modelConfig?: ModelConfig
  ): Promise<string> {
    console.log('[UnifiedBrain] Using Hermes as main brain');

    const conversationMessages = [
      ...messages,
      { id: `user-${Date.now()}`, role: 'user' as const, content: userMessage, timestamp: Date.now() }
    ];

    const recentMessages = contextEngine.getRecentMessages(conversationMessages, 50);
    const hermesMessages = recentMessages.map(m => ({
      role: m.role,
      content: m.content,
    }));

    try {
      const response = await hermesBridge.complete({
        model: 'hermes-3',
        messages: hermesMessages,
        temperature: modelConfig?.temperature ?? 0.7,
        max_tokens: modelConfig?.max_tokens ?? 4096,
      });

      // Check if response contains tool calls
      const toolCalls = this.extractToolCalls(response);
      
      if (toolCalls.length === 0) {
        return response;
      }

      console.log('[UnifiedBrain] Found', toolCalls.length, 'tool calls in response');
      
      // Execute tool calls and collect results
      const toolResults: Array<{ role: string; content: string; tool_call_id?: string }> = [];
      
      for (const toolCall of toolCalls) {
        const result = await this.executeToolCall(toolCall);
        toolResults.push({
          role: 'tool',
          content: result.success ? result.result : `Error: ${result.error}`,
          tool_call_id: toolCall.id,
        });
      }

      // Add tool results to conversation and get final response
      const messagesWithResults = [
        ...hermesMessages,
        { role: 'assistant', content: response },
        ...toolResults,
      ];

      try {
        const finalResponse = await hermesBridge.complete({
          model: 'hermes-3',
          messages: messagesWithResults,
          temperature: modelConfig?.temperature ?? 0.7,
          max_tokens: modelConfig?.max_tokens ?? 4096,
        });

        return finalResponse;
      } catch (error) {
        // Second call failed, return original with tool results
        console.error('[UnifiedBrain] Failed to get final response:', error);
        return `${response}\n\n[Tool Results]:\n${toolResults.map(r => r.content).join('\n')}`;
      }
    } catch (error) {
      console.error('[UnifiedBrain] Hermes request failed:', error);
      return this.processWithoutHermes(userMessage, messages, modelConfig);
    }
  }

  /**
   * Extract tool calls from Hermes response using JSON parsing
   */
  private extractToolCalls(response: string): ToolCall[] {
    const toolCalls: ToolCall[] = [];

    // Try to find and parse JSON blocks containing tool_calls
    const jsonBlockRegex = /```(?:json)?\n?([\r\n]*[\\[\\{][\r\n]*"tool_calls"[\r\n]*:[\r\n]*[\r\n\na-zA-Z0-9_\u2018\u2019""\u201c\u201d'\/\/\/\n\/\n\\\n\/\n\/\n\/\n\/\n\/\n\/\n\\\n]*?[\r\n]*\\][\r\n]*})/gi;
    
    let match;
    while ((match = jsonBlockRegex.exec(response)) !== null) {
      try {
        const parsed = JSON.parse(match[1]);
        const calls = parsed.tool_calls || [];
        for (const call of calls) {
          toolCalls.push({
            id: call.id || `tc-${Date.now()}-${Math.random()}`,
            name: call.name || call.function?.name,
            arguments: typeof call.arguments === 'string' ? JSON.parse(call.arguments) : (call.arguments || {}),
          });
        }
      } catch {
        // Skip malformed JSON
      }
    }

    // Also check for text format with XML-like tags
    const toolCallRegex = /<tool_call>\n?<name>(.*?)<\/name>\n?<args>(.*?)<\/args>\n?<\/tool_call>/gi;
    while ((match = toolCallRegex.exec(response)) !== null) {
      try {
        const args = JSON.parse(match[2]);
        toolCalls.push({
          id: `tc-${Date.now()}-${Math.random()}`,
          name: match[1],
          arguments: args,
        });
      } catch {
        // Skip malformed
      }
    }

    return toolCalls;
  }

  /**
   * Execute a tool call and return the result
   */
  private async executeToolCall(toolCall: ToolCall): Promise<ToolExecutionResult> {
    console.log('[UnifiedBrain] Executing tool:', toolCall.name);

    switch (toolCall.name) {
      case 'freebuff_coding':
        return this.executeFreebuffCoding(toolCall.arguments as unknown as Record<string, unknown>);
      
      default:
        try {
          const results = await toolExecutor.executeToolCalls([toolCall], {});
          if (results.length > 0 && results[0].success) {
            return {
              success: true,
              result: results[0].result || 'Tool executed successfully',
            };
          }
          return {
            success: false,
            result: '',
            error: results[0]?.error || 'Tool execution failed',
          };
        } catch (error) {
          return {
            success: false,
            result: '',
            error: error instanceof Error ? error.message : String(error),
          };
        }
    }
  }

  /**
   * Execute Freebuff coding tool
   */
  private async executeFreebuffCoding(args: Record<string, unknown>): Promise<ToolExecutionResult> {
    const instruction = args.instruction as string;
    const context = args.context as string | undefined;
    const files = args.files as string[] | undefined;

    if (!instruction) {
      return {
        success: false,
        result: '',
        error: 'Missing required parameter: instruction',
      };
    }

    console.log('[UnifiedBrain] Delegating coding task to Freebuff');

    try {
      const result = await (this.freebuffAgent as any).executeTask({
        id: `freebuff-${Date.now()}`,
        instruction,
        files,
        context,
      });

      if (result.success) {
        const changesSummary = result.changes && result.changes.length > 0
          ? `\n\nProposed changes:\n${result.changes.map((c: any) => `\u2022 ${c.action}: ${c.file_path}`).join('\n')}`
          : '';
        
        return {
          success: true,
          result: `[Freebuff Coding Agent]\n\nTask: ${instruction}\n\nStatus: ${result.success ? 'Completed' : 'Failed'}${changesSummary}\n\nLogs:\n${result.logs?.join('\n') || 'No logs available.'}`,
        };
      } else {
        return {
          success: false,
          result: '',
          error: result.error || 'Freebuff task failed',
        };
      }
    } catch (error) {
      return {
        success: false,
        result: '',
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }

  /**
   * Process without Hermes - local fallback
   */
  private async processWithoutHermes(
    userMessage: string,
    messages: Message[],
    modelConfig?: ModelConfig
  ): Promise<string> {
    console.log('[UnifiedBrain] Processing without Hermes (fallback mode)');

    if (isCodingTask(userMessage) && this.useFreebuff) {
      try {
        const result = await this.freebuffAgent.processCodeRequest(
          userMessage,
          undefined
        );
        
        if (result.success) {
          return `[Freebuff Coding Agent]\n\nI've analyzed your coding request:\n\n"${userMessage}"\n\nStatus: ${result.success ? 'Completed' : 'Failed'}\n\n${result.logs?.join('\n') || 'Freebuff processed this request.'}\n\nNote: Connect to Hermes Agent microservice for full integration.`;
        }
      } catch (error) {
        console.log('[UnifiedBrain] Freebuff failed:', error);
      }
    }

    return `I understand you want help with: "${userMessage.substring(0, 100)}..."\n\nFor full functionality, please deploy the Hermes Agent microservice.\nSee hermes-deployment/README.md for deployment instructions.`;
  }

  /**
   * Streaming processing - for real-time responses
   */
  async *streamProcess(
    userMessage: string,
    messages: Message[] = [],
    modelConfig?: ModelConfig
  ): AsyncGenerator<string> {
    if (this.useHermes) {
      try {
        for await (const chunk of hermesBridge.streamComplete({
          model: 'hermes-3',
          messages: [
            ...messages.map(m => ({ role: m.role, content: m.content })),
            { role: 'user', content: userMessage },
          ],
          temperature: modelConfig?.temperature ?? 0.7,
          max_tokens: modelConfig?.max_tokens ?? 4096,
          stream: true,
        })) {
          yield chunk;
        }
      } catch (error) {
        console.error('[UnifiedBrain] Hermes streaming failed:', error);
        yield `[Error: Hermes streaming failed. Please try again or deploy Hermes Agent.]`;
      }
    } else {
      const response = await this.processWithoutHermes(userMessage, messages, modelConfig);
      yield response;
    }
  }

  /**
   * Get brain status
   */
  getStatus(): { hermes: boolean; freebuff: boolean; unified: boolean } {
    return {
      hermes: this.useHermes,
      freebuff: this.useFreebuff,
      unified: this.useHermes && this.useFreebuff,
    };
  }

  /**
   * Check if Hermes is available
   */
  async isHermesAvailable(): Promise<boolean> {
    return hermesBridge.healthCheck();
  }

  /**
   * Check if Freebuff is available
   */
  async isFreebuffAvailable(): Promise<boolean> {
    return (this.freebuffAgent as any).healthCheck();
  }

  /**
   * Update configuration
   */
  updateConfig(config: Partial<UnifiedBrainConfig>) {
    this.config = { ...this.config, ...config };
    this.useHermes = !!this.config.hermesUrl;
    this.useFreebuff = Boolean(this.config.enableFreebuff) && Boolean(this.config.enableHermes);
  }
}

// Singleton instance
export const unifiedBrain = new UnifiedBrain();