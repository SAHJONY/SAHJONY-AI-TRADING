// Types for the SAHJONY Agent Engine (inspired by Hermes Agent architecture)

// Basic types first - no circular refs
export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  timestamp: number;
  tool_calls?: ToolCall[];
  tool_result?: ToolResult;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ToolResult {
  tool_call_id: string;
  result: string;
  success: boolean;
  error?: string;
  content?: string;
}

// Renamed to avoid conflict with AI SDK's ToolResult
export type AgentToolResult = ToolResult;

export type ToolCategory = 
  | 'web_search' 
  | 'code_execution' 
  | 'file_operations' 
  | 'browser' 
  | 'api_calls' 
  | 'data_processing'
  | 'custom';

export interface ModelConfig {
  provider: 'openai' | 'anthropic' | 'gemini' | 'local';
  model: string;
  temperature?: number;
  max_tokens?: number;
  api_key?: string;
  base_url?: string;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  instructions: string;
  tools: string[]; // tool names this skill uses
  enabled: boolean;
}

// Minimal Tool interface - avoid any complex type references
export interface Tool {
  name: string;
  description: string;
}

// AgentContext - uses Tool[]
export interface AgentContext {
  conversation_id: string;
  user_id: string;
  workspace_id?: string;
  messages: Message[];
  skills: Skill[];
  tools: Tool[];
  model: ModelConfig;
  system_prompt?: string;
}

export interface AgentConfig {
  name: string;
  description: string;
  model: ModelConfig;
  system_prompt?: string;
  tools: Tool[];
  skills: Skill[];
  memory?: MemoryConfig;
  max_turns?: number;
  timeout_ms?: number;
}

export interface MemoryConfig {
  type: 'short_term' | 'long_term' | 'hybrid';
  max_messages?: number;
  compression_threshold?: number;
}

export interface ConversationState {
  id: string;
  messages: Message[];
  context_window: Message[];
  skills_active: string[];
  tools_enabled: string[];
  turns_count: number;
  last_activity: number;
}

export interface StreamingChunk {
  type: 'text' | 'tool_call' | 'tool_result' | 'error' | 'done';
  content: string;
  tool_call?: ToolCall;
}

// Agent provider interface (similar to hermes-agent adapters)
export interface AIProvider {
  name: string;
  createCompletion(
    messages: Message[],
    config: ModelConfig
  ): Promise<string>;
  createStreamingCompletion(
    messages: Message[],
    config: ModelConfig,
    onChunk: (chunk: StreamingChunk) => void
  ): Promise<void>;
  countTokens(text: string): Promise<number>;
}

// Note: FreebuffConfig and HermesBridgeConfig are defined in their respective
// integration files (freebuff-integration.ts and hermes-bridge.ts) to avoid
// declaration merging issues when both modules are imported together.