// NVIDIA NIM AI provider adapter — OpenAI-compatible endpoint
// Uses integrate.api.nvidia.com/v1 for LLM-powered trading agent analysis
import OpenAI from 'openai'
import { AIProvider, Message, ModelConfig, StreamingChunk } from '../types'

export class NVIDIAProvider implements AIProvider {
  name = 'nvidia'
  private client: OpenAI
  private defaultModel: string

  constructor() {
    const apiKey = process.env.NVIDIA_API_KEY
    const baseURL = process.env.NVIDIA_BASE_URL || 'https://integrate.api.nvidia.com/v1'

    this.client = new OpenAI({
      apiKey: apiKey || 'placeholder',
      baseURL,
    })

    this.defaultModel = process.env.NVIDIA_DEFAULT_MODEL || 'nvidia/llama-3.1-nemotron-70b-instruct'
  }

  async createCompletion(
    messages: Message[],
    config: ModelConfig
  ): Promise<string> {
    const model = config.model || this.defaultModel

    const response = await this.client.chat.completions.create({
      model,
      temperature: config.temperature ?? 0.7,
      max_tokens: config.max_tokens || 1024,
      messages: messages.map(m => ({
        role: m.role as 'system' | 'user' | 'assistant',
        content: m.content,
      })),
    })

    return response.choices[0]?.message?.content || ''
  }

  async createStreamingCompletion(
    messages: Message[],
    config: ModelConfig,
    onChunk: (chunk: StreamingChunk) => void
  ): Promise<void> {
    const model = config.model || this.defaultModel

    const stream = await this.client.chat.completions.create({
      model,
      temperature: config.temperature ?? 0.7,
      max_tokens: config.max_tokens || 1024,
      stream: true,
      messages: messages.map(m => ({
        role: m.role as 'system' | 'user' | 'assistant',
        content: m.content,
      })),
    })

    for await (const chunk of stream) {
      const content = chunk.choices[0]?.delta?.content
      if (content) {
        onChunk({ type: 'text', content })
      }
    }

    onChunk({ type: 'done', content: '' })
  }

  async countTokens(text: string): Promise<number> {
    return Math.ceil(text.length / 4)
  }
}

export const nvidiaProvider = new NVIDIAProvider()
