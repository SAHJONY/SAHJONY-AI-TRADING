// Context Engine - manages conversation memory and context compression
// Inspired by hermes-agent's context_engine.py
import { Message, AgentContext, MemoryConfig } from '../types';

export class ContextEngine {
  private maxMessages: number;
  private compressionThreshold: number;

  constructor(config?: MemoryConfig) {
    this.maxMessages = config?.max_messages || 50;
    this.compressionThreshold = config?.compression_threshold || 40;
  }

  /**
   * Build context window for AI completion
   * Includes recent messages and system prompt
   */
  buildContext(messages: Message[], systemPrompt?: string): Message[] {
    const contextMessages: Message[] = [];

    // Add system prompt first
    if (systemPrompt) {
      contextMessages.push({
        id: 'system',
        role: 'system',
        content: systemPrompt,
        timestamp: Date.now(),
      });
    }

    // Add recent messages within context window
    const recentMessages = this.getRecentMessages(messages, this.maxMessages);
    contextMessages.push(...recentMessages);

    return contextMessages;
  }

  /**
   * Get recent messages up to max limit
   */
  getRecentMessages(messages: Message[], limit: number): Message[] {
    // Filter out tool results (they're already embedded in tool calls)
    const nonToolResults = messages.filter(m => m.role !== 'tool' || m.tool_calls);
    
    // Get last N messages
    return nonToolResults.slice(-limit);
  }

  /**
   * Check if context needs compression
   */
  needsCompression(messages: Message[]): boolean {
    return messages.length >= this.compressionThreshold;
  }

  /**
   * Compress context by summarizing older messages
   * This maintains context while reducing token usage
   */
  async compressContext(
    messages: Message[],
    provider: { countTokens: (text: string) => Promise<number> }
  ): Promise<{ compressed: Message[]; summary: string }> {
    if (messages.length <= 10) {
      return { compressed: messages, summary: '' };
    }

    // Keep recent messages and summarize older ones
    const recentCount = Math.min(15, Math.floor(messages.length / 2));
    const recentMessages = messages.slice(-recentCount);
    const olderMessages = messages.slice(0, -recentCount);

    // Create summary of older messages
    const olderContent = olderMessages
      .map(m => `${m.role}: ${m.content.substring(0, 200)}`)
      .join('\n');

    const summary = `Previous conversation summary:\n${olderContent.substring(0, 1000)}...`;

    const compressed: Message[] = [
      {
        id: 'summary',
        role: 'system',
        content: summary,
        timestamp: Date.now(),
      },
      ...recentMessages,
    ];

    return { compressed, summary };
  }

  /**
   * Estimate context size in tokens
   */
  async estimateContextSize(
    messages: Message[],
    provider: { countTokens: (text: string) => Promise<number> }
  ): Promise<number> {
    const totalContent = messages.map(m => m.content).join('\n');
    return provider.countTokens(totalContent);
  }

  /**
   * Prune old messages to stay within token limits
   */
  pruneContext(
    messages: Message[],
    maxTokens: number,
    provider: { countTokens: (text: string) => Promise<number> }
  ): Message[] {
    if (messages.length <= 5) return messages;

    let currentTokens = 0;
    const pruned: Message[] = [];

    // Start from most recent and work backwards
    for (let i = messages.length - 1; i >= 0; i--) {
      const msgTokens = Math.ceil(messages[i].content.length / 4);
      
      if (currentTokens + msgTokens <= maxTokens) {
        pruned.unshift(messages[i]);
        currentTokens += msgTokens;
      } else {
        break;
      }
    }

    return pruned;
  }
}

export const contextEngine = new ContextEngine();