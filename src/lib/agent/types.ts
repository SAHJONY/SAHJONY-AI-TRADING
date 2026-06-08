export interface AIProvider {
  name: string
  createCompletion(messages: Message[], config: ModelConfig): Promise<string>
  createStreamingCompletion(messages: Message[], config: ModelConfig, onChunk: (chunk: StreamingChunk) => void): Promise<void>
  countTokens(text: string): Promise<number>
}

export interface Message {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export interface ModelConfig {
  model?: string
  temperature?: number
  max_tokens?: number
}

export interface StreamingChunk {
  type: 'text' | 'done'
  content: string
}
