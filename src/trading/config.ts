/**
 * Layer 4 — Trading System Configuration
 *
 * Centralized configuration for the multi-agent trading workforce.
 * All values can be overridden via environment variables.
 */

import { TradingAgentConfig, AgentTradingRole } from './types'
import { Layer1IntegrationConfig } from './integration'

// ── Environment Helpers ──

const env = (key: string, fallback: string): string => process.env[key] || fallback
const envNum = (key: string, fallback: number): number => {
  const val = process.env[key]
  return val ? parseFloat(val) : fallback
}
const envBool = (key: string, fallback: boolean): boolean => {
  const val = process.env[key]
  return val !== undefined ? val === 'true' || val === '1' : fallback
}

// ── LLM Provider Config ──

export interface LLMDefaults {
  provider: 'openai' | 'anthropic'
  gptModel: string
  claudeModel: string
  temperature: number
  maxTokens: number
}

export const LLM_DEFAULTS: LLMDefaults = {
  provider: (env('LLM_PROVIDER', 'openai') as 'openai' | 'anthropic'),
  gptModel: env('LLM_GPT_MODEL', 'gpt-4o'),
  claudeModel: env('LLM_CLAUDE_MODEL', 'claude-sonnet-4-20250514'),
  temperature: envNum('LLM_TEMPERATURE', 0.3),
  maxTokens: envNum('LLM_MAX_TOKENS', 4096),
}

// ── Agent Configuration ──

export interface AgentRoleConfig {
  enabled: boolean
  provider: 'openai' | 'anthropic'
  model: string
  temperature: number
  /** Historical performance weight for consensus voting (0.0–1.0) */
  performanceWeight: number
}

export interface TradingSystemConfig {
  /** Debate loop settings */
  debate: {
    maxRounds: number
    consensusThreshold: number
    /** Require unanimous agreement from aligned agents? */
    requireRiskAgreement: boolean
    /** Timeout for entire debate (ms, 0 = no timeout) */
    timeoutMs: number
  }

  /** Agent role configurations */
  agents: Record<AgentTradingRole, AgentRoleConfig>

  /** Risk management thresholds (mirrors Layer 1 but for Layer 4 awareness) */
  riskThresholds: {
    /** Maximum position as % of portfolio */
    maxPositionSizePct: number
    /** Maximum daily loss before auto-stop */
    maxDailyLossPct: number
    /** Drawdown level that triggers human review */
    reviewDrawdownPct: number
    /** Minimum confidence for auto-execution (< this → human review) */
    minConfidenceForAuto: number
  }

  /** Layer 1 integration settings */
  layer1: Partial<Layer1IntegrationConfig>

  /** Session and logging */
  session: {
    /** Auto-persist debate transcripts */
    persistTranscripts: boolean
    /** Log level */
    logLevel: 'debug' | 'info' | 'warn' | 'error'
    /** Audit trail storage path */
    auditPath: string
  }
}

// ── Default Configuration ──

export const DEFAULT_TRADING_CONFIG: TradingSystemConfig = {
  debate: {
    maxRounds: envNum('DEBATE_MAX_ROUNDS', 3),
    consensusThreshold: envNum('DEBATE_CONSENSUS_THRESHOLD', 0.6),
    requireRiskAgreement: true,
    timeoutMs: envNum('DEBATE_TIMEOUT_MS', 120_000),
  },

  agents: {
    macro_strategist: {
      enabled: envBool('AGENT_MACRO_ENABLED', true),
      provider: LLM_DEFAULTS.provider,
      model: LLM_DEFAULTS.provider === 'openai' ? LLM_DEFAULTS.gptModel : LLM_DEFAULTS.claudeModel,
      temperature: 0.4,
      performanceWeight: 0.7,
    },
    sector_analyst: {
      enabled: envBool('AGENT_SECTOR_ENABLED', true),
      provider: LLM_DEFAULTS.provider,
      model: LLM_DEFAULTS.provider === 'openai' ? LLM_DEFAULTS.gptModel : LLM_DEFAULTS.claudeModel,
      temperature: 0.4,
      performanceWeight: 0.7,
    },
    sentiment_agent: {
      enabled: envBool('AGENT_SENTIMENT_ENABLED', true),
      provider: LLM_DEFAULTS.provider,
      model: LLM_DEFAULTS.provider === 'openai' ? LLM_DEFAULTS.gptModel : LLM_DEFAULTS.claudeModel,
      temperature: 0.5, // Slightly higher for creative sentiment interpretation
      performanceWeight: 0.6,
    },
    technical_analyst: {
      enabled: envBool('AGENT_TECHNICAL_ENABLED', true),
      provider: LLM_DEFAULTS.provider,
      model: LLM_DEFAULTS.provider === 'openai' ? LLM_DEFAULTS.gptModel : LLM_DEFAULTS.claudeModel,
      temperature: 0.3, // Lower → more systematic
      performanceWeight: 0.65,
    },
    risk_manager: {
      enabled: envBool('AGENT_RISK_ENABLED', true),
      provider: LLM_DEFAULTS.provider,
      model: LLM_DEFAULTS.provider === 'openai' ? LLM_DEFAULTS.gptModel : LLM_DEFAULTS.claudeModel,
      temperature: 0.1, // Very low — risk is conservative
      performanceWeight: 0.9, // Higher weight for veto power
    },
    execution_optimizer: {
      enabled: envBool('AGENT_EXECUTION_ENABLED', true),
      provider: LLM_DEFAULTS.provider,
      model: LLM_DEFAULTS.provider === 'openai' ? LLM_DEFAULTS.gptModel : LLM_DEFAULTS.claudeModel,
      temperature: 0.2,
      performanceWeight: 0.6,
    },
  },

  riskThresholds: {
    maxPositionSizePct: envNum('RISK_MAX_POSITION_PCT', 0.25),
    maxDailyLossPct: envNum('RISK_MAX_DAILY_LOSS_PCT', 0.05),
    reviewDrawdownPct: envNum('RISK_REVIEW_DRAWDOWN_PCT', 10),
    minConfidenceForAuto: envNum('RISK_MIN_CONFIDENCE_AUTO', 0.7),
  },

  layer1: {
    kafkaBroker: env('KAFKA_BROKER', 'localhost:19092'),
    simulationMode: envBool('LAYER1_SIMULATION', true),
    responseTimeoutMs: envNum('LAYER1_TIMEOUT_MS', 30_000),
  },

  session: {
    persistTranscripts: envBool('PERSIST_TRANSCRIPTS', true),
    logLevel: (env('LOG_LEVEL', 'info') as 'debug' | 'info' | 'warn' | 'error'),
    auditPath: env('AUDIT_PATH', './data/debates'),
  },
}

// ── Config Builder ──

/**
 * Build TradingAgentConfig objects from the system config.
 */
export function buildAgentConfigs(
  config: TradingSystemConfig
): Record<AgentTradingRole, TradingAgentConfig> {
  const roles: AgentTradingRole[] = [
    'macro_strategist',
    'sector_analyst',
    'sentiment_agent',
    'technical_analyst',
    'risk_manager',
    'execution_optimizer',
  ]

  const result = {} as Record<AgentTradingRole, TradingAgentConfig>

  for (const role of roles) {
    const roleConfig = config.agents[role]
    const roleNames: Record<AgentTradingRole, string> = {
      macro_strategist: 'Macro Strategist',
      sector_analyst: 'Sector Analyst',
      sentiment_agent: 'Sentiment Agent',
      technical_analyst: 'Technical Analyst',
      risk_manager: 'Risk Manager',
      execution_optimizer: 'Execution Optimizer',
    }

    result[role] = {
      id: `trading-agent-${role}`,
      name: roleNames[role],
      role,
      llmProvider: roleConfig.provider,
      llmModel: roleConfig.model,
      temperature: roleConfig.temperature,
      maxTokens: LLM_DEFAULTS.maxTokens,
      performanceWeight: roleConfig.performanceWeight,
      enabled: roleConfig.enabled,
    }
  }

  return result
}

/**
 * Build historical performance weights from the config.
 */
export function buildHistoricalWeights(
  config: TradingSystemConfig
): Record<string, number> {
  const weights: Record<string, number> = {}

  for (const [role, roleConfig] of Object.entries(config.agents)) {
    weights[role] = roleConfig.performanceWeight
  }

  return weights
}
