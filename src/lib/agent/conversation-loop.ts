// Conversation Loop - The core agent brain that orchestrates message flow
// Inspired by hermes-agent's conversation_loop.py
// Integrated with Hermes Bridge and Freebuff coding agent
import { 
  Message, 
  AgentContext, 
  ModelConfig, 
  StreamingChunk,
  ToolCall,
  AIProvider 
} from './types';
import { contextEngine } from './memory';
import { toolExecutor } from './tools';
import { hermesBridge } from './hermes-bridge';
import { freebuffAgent } from './freebuff-integration';
import { isCodingTask, truncate, formatTimestamp } from './utils';

export class ConversationLoop {
  private maxTurns: number;
  private timeoutMs: number;
  private useHermes: boolean;
  private useFreebuff: boolean;

  constructor(maxTurns = 10, timeoutMs = 120000) {
    this.maxTurns = maxTurns;
    this.timeoutMs = timeoutMs;
    this.useHermes = !!process.env.HERMES_AGENT_URL;
    this.useFreebuff = true;
  }



  /**
   * Process a user message and return the agent's response
   * This is the main entry point for the agent brain
   * 
   * Routing priority:
   * 1. Coding tasks → Freebuff
   * 2. Complex reasoning → Hermes Agent (if available)
   * 3. Everything else → Local AI providers
   */
  async processMessage(
    messages: Message[],
    context: AgentContext,
    provider: AIProvider,
    onStream?: (chunk: StreamingChunk) => void
  ): Promise<string> {
    let currentMessages = [...messages];
    const userMessage = messages[messages.length - 1]?.content || '';
    
    // Priority 1: Route coding tasks to Freebuff
    if (this.useFreebuff && this.isCodingTask(userMessage)) {
      console.log('[ConversationLoop] Routing to Freebuff for coding task');
      try {
        const result = await freebuffAgent.processCodeRequest(userMessage, context.workspaceId);
        if (result.success) {
          if (result.changes && result.changes.length > 0) {
            return this.formatFreebuffResponse(result);
          }
          return `[Freebuff Coding Agent]\n\nI've analyzed your request:\n\n"${userMessage}"\n\n${result.logs?.join('\n') || 'Freebuff processed this request successfully.'}\n\nNote: Connect to a running Freebuff instance for actual code execution.`;
        }
      } catch (error) {
        console.log('[ConversationLoop] Freebuff failed, falling back to local');
      }
    }

    // Priority 2: Use Hermes Agent for complex reasoning if available
    if (this.useHermes) {
      console.log('[ConversationLoop] Using Hermes Agent as brain');
      return this.processWithHermes(currentMessages, context, onStream);
    }

    // Priority 3: Fallback to local providers
    console.log('[ConversationLoop] Using local brain');
    return this.processLocally(currentMessages, context, provider, onStream);
  }

  /**
   * Process using Hermes Agent
   */
  private async processWithHermes(
    messages: Message[],
    context: AgentContext,
    onStream?: (chunk: StreamingChunk) => void
  ): Promise<string> {
    const recentMessages = contextEngine.getRecentMessages(messages, 50);
    
    if (onStream) {
      // Streaming mode
      let fullResponse = '';
      try {
        for await (const chunk of hermesBridge.streamComplete({
          model: 'hermes-3',
          messages: recentMessages.map(m => ({ role: m.role, content: m.content })),
          temperature: context.model.temperature ?? 0.7,
          max_tokens: context.model.max_tokens ?? 4096,
        })) {
          fullResponse += chunk;
          onStream({ type: 'text', content: chunk });
        }
        onStream({ type: 'done' });
        return fullResponse;
      } catch (error) {
        console.error('[ConversationLoop] Hermes streaming failed:', error);
        // Fall back to local processing
        return this.processLocally(messages, context, null, onStream);
      }
    } else {
      // Non-streaming mode
      try {
        return await hermesBridge.complete({
          model: 'hermes-3',
          messages: recentMessages.map(m => ({ role: m.role, content: m.content })),
          temperature: context.model.temperature ?? 0.7,
          max_tokens: context.model.max_tokens ?? 4096,
        });
      } catch (error) {
        console.error('[ConversationLoop] Hermes request failed:', error);
        // Create a default provider for fallback
        const provider = context.model.provider === 'openai' 
          ? await import('./providers/openai-provider').then(m => m.openaiProvider)
          : await import('./providers/anthropic-provider').then(m => m.anthropicProvider);
        return this.processLocally(messages, context, provider, undefined);
      }
    }
  }

  /**
   * Process using local AI providers (Anthropic/OpenAI)
   */
  private async processLocally(
    messages: Message[],
    context: AgentContext,
    provider: AIProvider | null,
    onStream?: (chunk: StreamingChunk) => void
  ): Promise<string> {
    if (!provider) {
      // Create a default provider
      provider = context.model.provider === 'openai' 
        ? await import('./providers/openai-provider').then(m => m.openaiProvider)
        : await import('./providers/anthropic-provider').then(m => m.anthropicProvider);
    }

    let currentMessages = [...messages];
    let turnsCount = 0;
    let finalResponse = '';

    // Build initial context
    const systemPrompt = this.buildSystemPrompt(context);
    let contextMessages = contextEngine.buildContext(currentMessages, systemPrompt);

    // Main conversation loop
    while (turnsCount < this.maxTurns) {
      turnsCount++;
      console.log(`[ConversationLoop] Turn ${turnsCount}/${this.maxTurns}`);

      // Get AI completion
      let assistantMessage: string;
      
      if (onStream) {
        let fullResponse = '';
        await provider.createStreamingCompletion(contextMessages, context.model, (chunk) => {
          if (chunk.type === 'text') {
            fullResponse += chunk.content;
            onStream(chunk);
          } else if (chunk.type === 'done') {
            onStream(chunk);
          }
        });
        assistantMessage = fullResponse;
      } else {
        assistantMessage = await provider.createCompletion(contextMessages, context.model);
      }

      // Check for tool calls in the response
      const toolCalls = this.extractToolCalls(assistantMessage);

      if (toolCalls.length === 0) {
        // No tools called, this is the final response
        finalResponse = assistantMessage;
        break;
      }

      // Add assistant message with tool calls to context
      const assistantMsg: Message = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: assistantMessage,
        timestamp: Date.now(),
        tool_calls: toolCalls,
      };
      contextMessages.push(assistantMsg);

      // Execute tools
      const toolResults = await toolExecutor.executeToolCalls(toolCalls, context);

      // Add tool results to context
      for (const result of toolResults) {
        const toolMsg: Message = {
          id: `tool-${Date.now()}-${Math.random()}`,
          role: 'tool',
          content: result.result || result.error || 'Tool execution failed',
          timestamp: Date.now(),
          tool_result: result,
        };
        contextMessages.push(toolMsg);

        if (onStream) {
          onStream({
            type: 'tool_result',
            content: result.result || result.error || '',
          });
        }
      }

      // Check if we should continue looping
      const allFailed = toolResults.every(r => !r.success);
      if (allFailed) {
        finalResponse = "I encountered errors while trying to use tools.";
        break;
      }
    }

    return finalResponse || "I'm sorry, I couldn't complete the request.";
  }

  /**
   * Format Freebuff response nicely
   */
  private formatFreebuffResponse(result: { changes?: Array<{file_path: string; action: string; diff?: string}>; logs?: string[] }): string {
    const parts: string[] = ['[Freebuff Coding Agent]\n'];
    
    if (result.changes && result.changes.length > 0) {
      parts.push('\n📝 **Proposed Changes:**\n');
      result.changes.forEach((change, i) => {
        parts.push(`${i + 1}. **${change.action}** \\`${change.file_path}\\`\n`);
        if (change.diff) {
          parts.push(`   \n   \\`${change.diff.substring(0, 200)}...\n   \n`);
        }
      });
    }
    
    if (result.logs && result.logs.length > 0) {
      parts.push('\n📋 **Logs:**\n');
      result.logs.forEach(log => parts.push(`• ${log}\n`));
    }
    
    parts.push('\n_Connect to a running Freebuff instance for actual code execution._');
    return parts.join('');
  }

  /**
   * Build system prompt with agent configuration
   */
  private buildSystemPrompt(context: AgentContext): string {
    const parts: string[] = [];

    if (context.system_prompt) {
      parts.push(context.system_prompt);
    }

    parts.push(`You are ${context.model.provider === 'anthropic' ? 'Claude' : 'an AI assistant'} powered by the SAHJONY Agent Engine.`);
    parts.push(`You have access to various tools to help users accomplish tasks.`);

    // Add enabled tools info
    const enabledTools = toolExecutor.getEnabledTools();
    if (enabledTools.length > 0) {
      const toolNames = enabledTools.map(t => t.name).join(', ');
      parts.push(`Available tools: ${toolNames}`);
    }

    // Add skill context if any
    const activeSkills = context.skills.filter(s => s.enabled);
    if (activeSkills.length > 0) {
      parts.push('\nActive skills:');
      activeSkills.forEach(skill => {
        parts.push(`- ${skill.name}: ${skill.description}`);
      });
    }

    return parts.join('\n');
  }

  /**
   * Extract tool calls from assistant message
   */
  private extractToolCalls(message: string): ToolCall[] {
    const toolCalls: ToolCall[] = [];

    // Try to parse JSON tool calls
    try {
      const jsonMatch = message.match(/```(?:json)?\n([\r\n]*tool_calls[\r\n]*:[\r\n]*\n.*?)\n```/i);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[1]);
        const calls = Array.isArray(parsed) ? parsed : parsed.tool_calls || [];
        for (const call of calls) {
          toolCalls.push({
            id: call.id || `tc-${Date.now()}-${Math.random()}`,
            name: call.name,
            arguments: call.arguments || {},
          });
        }
      }
    } catch {
      // Not JSON, try other patterns
    }

    // Look for <tool_call> XML-like tags
    const toolCallRegex = /<tool_call>\n*<name>(.*?)<\/name>\n*<args>(.*?)<\/args>\n*<\/tool_call>/gi;
    let match;
    while ((match = toolCallRegex.exec(message)) !== null) {
      try {
        const args = JSON.parse(match[2]);
        toolCalls.push({
          id: `tc-${Date.now()}-${Math.random()}`,
          name: match[1],
          arguments: args,
        });
      } catch {
        // Skip malformed tool calls
      }
    }

    return toolCalls;
  }

  /**
   * Reset conversation state
   */
  reset() {
    // Could reset any cached state here
  }
}

export const conversationLoop = new ConversationLoop();