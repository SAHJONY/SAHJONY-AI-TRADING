// OpenAI AI provider adapter - matches hermes-agent architecture
import OpenAI from 'openai';
import { AIProvider, Message, ModelConfig, StreamingChunk } from '../types';

export class OpenAIProvider implements AIProvider {
  name = 'openai';
  private client: OpenAI;

  constructor() {
    this.client = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY,
    });
  }

  async createCompletion(
    messages: Message[],
    config: ModelConfig
  ): Promise<string> {
    const response = await this.client.chat.completions.create({
      model: config.model || 'gpt-4-turbo',
      temperature: config.temperature ?? 0.7,
      max_tokens: config.max_tokens || 4096,
      messages: messages.map(m => ({
        role: m.role,
        content: m.content,
      })),
    });

    return response.choices[0]?.message?.content || '';
  }

  async createStreamingCompletion(
    messages: Message[],
    config: ModelConfig,
    onChunk: (chunk: StreamingChunk) => void
  ): Promise<void> {
    const stream = await this.client.chat.completions.create({
      model: config.model || 'gpt-4-turbo',
      temperature: config.temperature ?? 0.7,
      max_tokens: config.max_tokens || 4096,
      stream: true,
      messages: messages.map(m => ({
        role: m.role,
        content: m.content,
      })),
    });

    for await (const chunk of stream) {
      const content = chunk.choices[0]?.delta?.content;
      if (content) {
        onChunk({ type: 'text', content });
      }
    }

    onChunk({ type: 'done', content: '' });
  }

  async countTokens(text: string): Promise<number> {
    // Approximate tokens (4 chars per token average)
    return Math.ceil(text.length / 4);
  }
}

export const openaiProvider = new OpenAIProvider();