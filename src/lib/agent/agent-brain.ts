// AgentBrain - The main AI agent facade that ties together all components
// This is the primary entry point for the SAHJONY platform's AI capabilities
// Now using Unified Brain where Hermes Agent delegates to Freebuff as a single engine
import { 
  Message, 
  AgentContext, 
  AgentConfig, 
  ModelConfig,
  StreamingChunk,
  Skill 
} from './types';
import { unifiedBrain, UnifiedBrain } from './unified-brain';
import { conversationLoop } from './conversation-loop';
import { toolExecutor } from './tools';
import { contextEngine } from './memory';
import { anthropicProvider } from './providers/anthropic-provider';
import { openaiProvider } from './providers/openai-provider';
import { AIProvider } from './types';

export class AgentBrain {
  private config: AgentConfig;
  private provider: AIProvider;
  private unifiedBrain: UnifiedBrain;
  private useUnifiedBrain: boolean;

  constructor(config: AgentConfig) {
    this.config = config;
    this.provider = this.createProvider(config.model);
    this.unifiedBrain = unifiedBrain;
    
    // Use unified brain if Hermes URL is configured
    this.useUnifiedBrain = !!process.env.HERMES_AGENT_URL;
    console.log('[AgentBrain] Unified brain mode:', this.useUnifiedBrain);
  }

  /**
   * Create AI provider based on model config
   */
  private createProvider(modelConfig: ModelConfig): AIProvider {
    switch (modelConfig.provider) {
      case 'anthropic':
        return anthropicProvider;
      case 'openai':
        return openaiProvider;
      default:
        return anthropicProvider;
    }
  }

  /**
   * Process a message using the unified brain (Hermes + Freebuff as one)
   * 
   * The unified brain architecture:
   * - Hermes Agent is the main reasoning engine
   * - Freebuff is available as a delegatable tool for coding tasks
   * - Both work together as a single brain system
   */
  async process(
    userMessage: string,
    context: Omit<AgentContext, 'messages' | 'tools' | 'skills'>
  ): Promise<string> {
    // Get conversation history from context
    const historyMessages = context.messages || [];

    // Build full context for local fallback
    const fullContext: AgentContext = {
      ...context,
      messages: [
        ...historyMessages,
        {
          id: `user-${Date.now()}`,
          role: 'user',
          content: userMessage,
          timestamp: Date.now(),
        },
      ],
      tools: toolExecutor.getEnabledTools(),
      skills: this.config.skills,
      model: this.config.model,
      system_prompt: this.config.system_prompt,
    };

    // Use unified brain (Hermes + Freebuff) if available
    if (this.useUnifiedBrain) {
      console.log('[AgentBrain] Using unified brain (Hermes + Freebuff)');
      try {
        const response = await this.unifiedBrain.process(
          userMessage,
          historyMessages,
          this.config.model
        );
        return response;
      } catch (error) {
        console.log('[AgentBrain] Unified brain failed, falling back to local');
      }
    }

    // Fallback: Use local conversation loop
    console.log('[AgentBrain] Using local brain (unified brain unavailable)');
    const messages = [
      {
        id: `user-${Date.now()}`,
        role: 'user',
        content: userMessage,
        timestamp: Date.now(),
      },
    ];
    return conversationLoop.processMessage(messages, fullContext, this.provider);
  }

  /**
   * Process with streaming response
   */
  async processStream(
    userMessage: string,
    context: Omit<AgentContext, 'messages' | 'tools' | 'skills'>,
    onChunk: (chunk: StreamingChunk) => void
  ): Promise<string> {
    const historyMessages = context.messages || [];
    
    const fullContext: AgentContext = {
      ...context,
      messages: [
        ...historyMessages,
        {
          id: `user-${Date.now()}`,
          role: 'user',
          content: userMessage,
          timestamp: Date.now(),
        },
      ],
      tools: toolExecutor.getEnabledTools(),
      skills: this.config.skills,
      model: this.config.model,
      system_prompt: this.config.system_prompt,
    };

    // Use unified brain streaming if available
    if (this.useUnifiedBrain) {
      console.log('[AgentBrain] Using unified brain streaming');
      try {
        let fullResponse = '';
        for await (const chunk of this.unifiedBrain.streamProcess(
          userMessage,
          historyMessages,
          this.config.model
        )) {
          fullResponse += chunk;
          onChunk({ type: 'text', content: chunk });
        }
        onChunk({ type: 'done' });
        return fullResponse;
      } catch (error) {
        console.log('[AgentBrain] Unified brain streaming failed, falling back');
      }
    }

    // Fallback: Local streaming
    const messages = [
      {
        id: `user-${Date.now()}`,
        role: 'user',
        content: userMessage,
        timestamp: Date.now(),
      },
    ];
    return conversationLoop.processMessage(messages, fullContext, this.provider, onChunk);
  }

  /**
   * Update agent configuration
   */
  updateConfig(config: Partial<AgentConfig>) {
    this.config = { ...this.config, ...config };
  }

  /**
   * Get current configuration
   */
  getConfig(): AgentConfig {
    return { ...this.config };
  }

  /**
   * Enable/disable a tool
   */
  setToolEnabled(toolName: string, enabled: boolean) {
    toolExecutor.setToolEnabled(toolName, enabled);
  }

  /**
   * Enable/disable a skill
   */
  setSkillEnabled(skillId: string, enabled: boolean) {
    const skill = this.config.skills.find(s => s.id === skillId);
    if (skill) {
      skill.enabled = enabled;
    }
  }

  /**
   * Get available tools
   */
  getTools() {
    return toolExecutor.getEnabledTools();
  }

  /**
   * Get active skills
   */
  getSkills(): Skill[] {
    return this.config.skills.filter(s => s.enabled);
  }

  /**
   * Check if Hermes Agent is available
   */
  async isHermesAvailable(): Promise<boolean> {
    return this.unifiedBrain.isHermesAvailable();
  }

  /**
   * Check if Freebuff is available
   */
  async isFreebuffAvailable(): Promise<boolean> {
    return this.unifiedBrain.isFreebuffAvailable();
  }

  /**
   * Get brain status (which engines are active)
   */
  getBrainStatus(): { hermes: boolean; freebuff: boolean; unified: boolean } {
    return this.unifiedBrain.getStatus();
  }

  /**
   * Get the unified brain instance
   */
  getUnifiedBrain(): UnifiedBrain {
    return this.unifiedBrain;
  }
}

// Default agent instance with unified brain (Hermes + Freebuff)
export const createDefaultAgent = (): AgentBrain => {
  const config: AgentConfig = {
    name: 'SAHJONY Agent',
    description: 'AI agent powered by Unified Brain (Hermes Agent + Freebuff)',
    model: {
      provider: 'anthropic',
      model: process.env.ANTHROPIC_MODEL || 'claude-3-5-sonnet-20241022',
      temperature: 0.7,
      max_tokens: 4096,
      api_key: process.env.ANTHROPIC_API_KEY,
    },
    system_prompt: `You are SAHJONY, an advanced AI agent powered by a Unified Brain architecture.

Your brain consists of two integrated components:
1. Hermes Agent: Advanced reasoning and problem-solving
2. Freebuff: AI coding assistant for code generation and refactoring

These work together as a single unified brain - Hermes handles reasoning
and delegates coding tasks to Freebuff as needed.

You have access to tools that allow you to:
- Search the web for current information
- Execute code (Python/JavaScript) for calculations and automation
- Read and write files in your workspace
- Control a web browser for web automation
- Use Freebuff for coding tasks

Use these tools when helpful to provide accurate and comprehensive answers.
Always be helpful, accurate, and respectful.`,
    tools: toolExecutor.getEnabledTools(),
    skills: [],
    memory: {
      type: 'hybrid',
      max_messages: 50,
      compression_threshold: 40,
    },
    max_turns: 10,
    timeout_ms: 120000,
  };

  return new AgentBrain(config);
};

export const agentBrain = createDefaultAgent();