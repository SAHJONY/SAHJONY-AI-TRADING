// Hermes Bridge - Connects SAHJONY platform to Hermes Agent microservice
// Enables communication with the Python-based Hermes Agent runtime
import { Message, ModelConfig, StreamingChunk } from './types';

export interface HermesBridgeConfig {
  hermesUrl: string;
  apiKey?: string;
  timeoutMs?: number;
}

export interface HermesRequest {
  model: string;
  messages: Array<{ role: string; content: string }>;
  temperature?: number;
  max_tokens?: number;
  stream?: boolean;
  tools?: string[];
}

export interface HermesResponse {
  id: string;
  model: string;
  choices: Array<{
    message: {
      role: string;
      content: string;
      tool_calls?: Array<{
        id: string;
        function: { name: string; arguments: string };
      }>;
    };
    finish_reason: string;
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

/**
 * Hermes Bridge allows the SAHJONY platform to communicate with
 * a deployed Hermes Agent Python service. This enables:
 * - Use of Hermes Agent's advanced reasoning capabilities
 * - Access to Hermes's 200+ built-in skills
 * - Integration with Hermes's multi-agent delegation system
 * - Persistent memory and cross-session learning
 */
export class HermesBridge {
  private config: HermesBridgeConfig;
  private baseUrl: string;

  constructor(config: HermesBridgeConfig) {
    this.config = config;
    this.baseUrl = config.hermesUrl || process.env.HERMES_AGENT_URL || 'http://localhost:8000';
  }

  /**
   * Send a completion request to Hermes Agent
   */
  async complete(request: HermesRequest): Promise<string> {
    try {
      console.log(`[HermesBridge] Sending request to ${this.baseUrl}`);

      const response = await fetch(`${this.baseUrl}/v1/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.config.apiKey && { Authorization: `Bearer ${this.config.apiKey}` }),
        },
        body: JSON.stringify({
          model: request.model,
          messages: request.messages,
          temperature: request.temperature ?? 0.7,
          max_tokens: request.max_tokens ?? 4096,
          stream: false,
        }),
      });

      if (!response.ok) {
        throw new Error(`Hermes API error: ${response.status}`);
      }

      const data: HermesResponse = await response.json();
      return data.choices[0]?.message?.content || '';

    } catch (error) {
      console.error('[HermesBridge] Request failed:', error);
      throw error;
    }
  }

  /**
   * Send a streaming completion request to Hermes Agent
   */
  async *streamComplete(request: HermesRequest): AsyncGenerator<string> {
    try {
      const response = await fetch(`${this.baseUrl}/v1/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.config.apiKey && { Authorization: `Bearer ${this.config.apiKey}` }),
        },
        body: JSON.stringify({
          model: request.model,
          messages: request.messages,
          temperature: request.temperature ?? 0.7,
          max_tokens: request.max_tokens ?? 4096,
          stream: true,
        }),
      });

      if (!response.ok) {
        throw new Error(`Hermes API error: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            if (data !== '[DONE]') {
              try {
                const parsed = JSON.parse(data);
                const content = parsed.choices?.[0]?.delta?.content;
                if (content) yield content;
              } catch {
                // Skip malformed JSON
              }
            }
          }
        }
      }

    } catch (error) {
      console.error('[HermesBridge] Stream failed:', error);
      throw error;
    }
  }

  /**
   * Execute a tool via Hermes Agent
   */
  async executeTool(toolName: string, args: Record<string, unknown>): Promise<unknown> {
    try {
      const response = await fetch(`${this.baseUrl}/v1/tools/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(this.config.apiKey && { Authorization: `Bearer ${this.config.apiKey}` }),
        },
        body: JSON.stringify({ tool: toolName, arguments: args }),
      });

      if (!response.ok) {
        throw new Error(`Hermes tool execution error: ${response.status}`);
      }

      return response.json();

    } catch (error) {
      console.error('[HermesBridge] Tool execution failed:', error);
      throw error;
    }
  }

  /**
   * Get available skills from Hermes Agent
   */
  async getSkills(): Promise<Array<{ id: string; name: string; description: string }>> {
    try {
      const response = await fetch(`${this.baseUrl}/v1/skills`, {
        method: 'GET',
        headers: {
          ...(this.config.apiKey && { Authorization: `Bearer ${this.config.apiKey}` }),
        },
      });

      if (!response.ok) {
        throw new Error(`Hermes skills error: ${response.status}`);
      }

      return response.json();

    } catch (error) {
      console.error('[HermesBridge] Get skills failed:', error);
      return [];
    }
  }

  /**
   * Check if Hermes Agent is available
   */
  async healthCheck(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(5000),
      });
      return response.ok;
    } catch {
      return false;
    }
  }

  /**
   * Update configuration
   */
  updateConfig(config: Partial<HermesBridgeConfig>) {
    this.config = { ...this.config, ...config };
    if (config.hermesUrl) {
      this.baseUrl = config.hermesUrl;
    }
  }
}

// Default instance
export const hermesBridge = new HermesBridge({
  hermesUrl: process.env.HERMES_AGENT_URL || 'http://localhost:8000',
  apiKey: process.env.HERMES_AGENT_API_KEY,
  timeoutMs: 60000,
});