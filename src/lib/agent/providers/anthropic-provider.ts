// Anthropic AI provider adapter - matches hermes-agent architecture
import Anthropic from '@anthropic-ai/sdk';
import { AIProvider, Message, ModelConfig, StreamingChunk } from '../types';

export class AnthropicProvider implements AIProvider {
  name = 'anthropic';
  private client: Anthropic;

  constructor() {
    this.client = new Anthropic({
      apiKey: process.env.ANTHROPIC_API_KEY,
    });
  }

  async createCompletion(
    messages: Message[],
    config: ModelConfig
  ): Promise<string> {
    const response = await this.client.messages.create({
      model: config.model || 'claude-3-5-sonnet-20241022',
      max_tokens: config.max_tokens || 4096,
      temperature: config.temperature ?? 0.7,
      system: this.extractSystemMessage(messages),
      messages: this.formatMessages(messages),
    });

    return response.content[0].type === 'text' 
      ? response.content[0].text 
      : '';
  }

  async createStreamingCompletion(
    messages: Message[],
    config: ModelConfig,
    onChunk: (chunk: StreamingChunk) => void
  ): Promise<void> {
    const stream = await this.client.messages.stream({
      model: config.model || 'claude-3-5-sonnet-20241022',
      max_tokens: config.max_tokens || 4096,
      temperature: config.temperature ?? 0.7,
      system: this.extractSystemMessage(messages),
      messages: this.formatMessages(messages),
    });

    for await (const event of stream) {
      if (event.type === 'content_block_delta') {
        if (event.delta.type === 'text_delta') {
          onChunk({
            type: 'text',
            content: event.delta.text,
          });
        }
      }
    }

    onChunk({ type: 'done', content: '' });
  }

  async countTokens(text: string): Promise<number> {
    // Approximate tokens (4 chars per token average)
    return Math.ceil(text.length / 4);
  }

  private extractSystemMessage(messages: Message[]): string {
    const systemMsg = messages.find(m => m.role === 'system');
    return systemMsg?.content || '';
  }

  private formatMessages(messages: Message[]): Anthropic.MessageCreateParams.Message[] {
    return messages
      .filter(m => m.role !== 'system')
      .map(m => ({
        role: m.role as 'user' | 'assistant',
        content: m.content,
      }));
  }
}

export const anthropicProvider = new AnthropicProvider();