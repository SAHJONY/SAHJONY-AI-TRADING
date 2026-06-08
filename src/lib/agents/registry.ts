// ──────────────────────────────────────────────────────────────
// SAHJONY CAPITAL — TRADING AGENTS REGISTRY
// One specialized trading agent per provider. Each agent uses
// its provider's latest model and auto-updates daily.
// ──────────────────────────────────────────────────────────────

export interface TradingAgent {
  id: string
  name: string
  providerId: string
  modelId: string              // resolves to latest model via registry
  specialty: string            // trading strategy specialty
  description: string
  riskLevel: 'conservative' | 'moderate' | 'aggressive'
  timeHorizon: 'scalp' | 'intraday' | 'swing' | 'position'
  icon: string
  color: string
  isDefault: boolean           // included by default on new accounts
  isPremium: boolean           // requires paid plan
}

export const TRADING_AGENTS: TradingAgent[] = [
  // ── HERMES (The Brain & Engine — Orchestrator) ──
  {
    id: 'agent-hermes-oracle',
    name: 'Hermes Oracle',
    providerId: 'hermes',
    modelId: 'hermes-brain-latest',
    specialty: 'Multi-Agent Orchestration',
    description: 'The master brain. Coordinates all other agents, resolves conflicts, and makes final portfolio allocation decisions. Self-healing and autonomous.',
    riskLevel: 'moderate',
    timeHorizon: 'intraday',
    icon: '⚡',
    color: 'text-yellow-400',
    isDefault: true,
    isPremium: false,
  },

  // ── NVIDIA ──
  {
    id: 'agent-nvidia-blitz',
    name: 'NVIDIA Blitz',
    providerId: 'nvidia',
    modelId: 'nvidia-latest',
    specialty: 'GPU-Accelerated Scalping',
    description: 'Sub-100ms signal execution. GPU-accelerated pattern recognition for high-frequency scalping on liquid markets. Pure speed.',
    riskLevel: 'aggressive',
    timeHorizon: 'scalp',
    icon: '🟢',
    color: 'text-green-400',
    isDefault: false,
    isPremium: false,
  },

  // ── OPENAI ──
  {
    id: 'agent-openai-atlas',
    name: 'OpenAI Atlas',
    providerId: 'openai',
    modelId: 'openai-latest',
    specialty: 'Global Macro Analysis',
    description: 'Deep macro-economic analysis across global markets. Identifies cross-asset opportunities using GPT-level reasoning and real-time data synthesis.',
    riskLevel: 'conservative',
    timeHorizon: 'position',
    icon: '🔲',
    color: 'text-gray-200',
    isDefault: true,
    isPremium: false,
  },

  // ── OPENAI REASONING ──
  {
    id: 'agent-openai-quantum',
    name: 'OpenAI Quantum',
    providerId: 'openai',
    modelId: 'openai-reasoning-latest',
    specialty: 'Deep Reasoning — Options & Derivatives',
    description: 'Extended chain-of-thought for complex options pricing, Greeks analysis, and multi-leg derivatives strategies. The deepest thinker.',
    riskLevel: 'moderate',
    timeHorizon: 'swing',
    icon: '🧠',
    color: 'text-purple-300',
    isDefault: false,
    isPremium: true,
  },

  // ── ANTHROPIC ──
  {
    id: 'agent-anthropic-sentinel',
    name: 'Claude Sentinel',
    providerId: 'anthropic',
    modelId: 'anthropic-latest',
    specialty: 'Risk Management & Compliance',
    description: 'Constitutional AI for risk guardrails. Monitors all positions, enforces stop-losses, and ensures regulatory compliance. The safety net.',
    riskLevel: 'conservative',
    timeHorizon: 'swing',
    icon: '🛡️',
    color: 'text-amber-600',
    isDefault: true,
    isPremium: false,
  },

  // ── GOOGLE ──
  {
    id: 'agent-google-nexus',
    name: 'Gemini Nexus',
    providerId: 'google',
    modelId: 'google-latest',
    specialty: '1M-Context Portfolio Analysis',
    description: 'Ingests entire portfolio histories, 10-K filings, and market reports in a single pass. Identifies long-tail correlations no human can see.',
    riskLevel: 'moderate',
    timeHorizon: 'position',
    icon: '🔵',
    color: 'text-blue-400',
    isDefault: false,
    isPremium: false,
  },

  // ── XAI ──
  {
    id: 'agent-xai-pulse',
    name: 'Grok Pulse',
    providerId: 'xai',
    modelId: 'xai-latest',
    specialty: 'Social Sentiment Trading',
    description: 'Real-time X/Twitter sentiment analysis. Tracks influencer signals, viral narratives, and crowd psychology for momentum plays.',
    riskLevel: 'aggressive',
    timeHorizon: 'intraday',
    icon: '⚪',
    color: 'text-white',
    isDefault: false,
    isPremium: false,
  },

  // ── META ──
  {
    id: 'agent-meta-maverick',
    name: 'Llama Maverick',
    providerId: 'meta',
    modelId: 'meta-latest',
    specialty: 'On-Premise Private Quant',
    description: 'Open-weight model for fully private, on-premise quantitative analysis. Zero data leaves your infrastructure. Fine-tunable on proprietary data.',
    riskLevel: 'moderate',
    timeHorizon: 'swing',
    icon: '🔵',
    color: 'text-blue-500',
    isDefault: false,
    isPremium: true,
  },

  // ── MISTRAL ──
  {
    id: 'agent-mistral-euro',
    name: 'Mistral Euro',
    providerId: 'mistral',
    modelId: 'mistral-latest',
    specialty: 'European Markets & EU Compliance',
    description: 'Specialist in European equities, FX pairs, and MiFID II compliance. EU data residency. Top-tier performance at competitive pricing.',
    riskLevel: 'moderate',
    timeHorizon: 'swing',
    icon: '🟠',
    color: 'text-orange-400',
    isDefault: false,
    isPremium: false,
  },

  // ── DEEPSEEK ──
  {
    id: 'agent-deepseek-vortex',
    name: 'DeepSeek Vortex',
    providerId: 'deepseek',
    modelId: 'deepseek-latest',
    specialty: 'High-Volume Pattern Mining',
    description: 'MoE architecture for massive parallel pattern discovery across thousands of assets simultaneously. 10x cheaper than comparable agents.',
    riskLevel: 'aggressive',
    timeHorizon: 'intraday',
    icon: '🌀',
    color: 'text-cyan-400',
    isDefault: false,
    isPremium: false,
  },

  // ── COHERE ──
  {
    id: 'agent-cohere-arc',
    name: 'Cohere Arc',
    providerId: 'cohere',
    modelId: 'cohere-latest',
    specialty: 'RAG-Grounded Research Trading',
    description: 'Knowledge-grounded analysis using real-time document retrieval. Reads SEC filings, earnings calls, and research papers before every trade decision.',
    riskLevel: 'conservative',
    timeHorizon: 'position',
    icon: '🟣',
    color: 'text-purple-400',
    isDefault: false,
    isPremium: false,
  },

  // ── OPENCLAW ──
  {
    id: 'agent-openclaw-swarm',
    name: 'OpenClaw Swarm',
    providerId: 'openclaw',
    modelId: 'openclaw-latest',
    specialty: 'Multi-Agent Swarm Trading',
    description: 'Deploys autonomous sub-agent swarms that fan out across markets, each specializing in a micro-strategy, then converges on consensus signals.',
    riskLevel: 'aggressive',
    timeHorizon: 'scalp',
    icon: '🐙',
    color: 'text-rose-400',
    isDefault: false,
    isPremium: true,
  },

  // ── GROQ ──
  {
    id: 'agent-groq-flash',
    name: 'Groq Flash',
    providerId: 'groq',
    modelId: 'groq-latest',
    specialty: 'Ultra-Low-Latency Execution',
    description: 'LPU-powered sub-millisecond inference for time-critical trade execution. When every microsecond counts — news reactions, open/close trades.',
    riskLevel: 'aggressive',
    timeHorizon: 'scalp',
    icon: '⚡',
    color: 'text-orange-500',
    isDefault: true,
    isPremium: false,
  },

  // ── PERPLEXITY ──
  {
    id: 'agent-perplexity-scout',
    name: 'Perplexity Scout',
    providerId: 'perplexity',
    modelId: 'perplexity-latest',
    specialty: 'Real-Time News & Event Trading',
    description: 'Web-grounded research agent that monitors breaking news, Fed announcements, and geopolitical events. Turns information edge into alpha.',
    riskLevel: 'moderate',
    timeHorizon: 'intraday',
    icon: '🔮',
    color: 'text-teal-400',
    isDefault: false,
    isPremium: false,
  },

  // ── FREEBUFF ──
  {
    id: 'agent-freebuff-zero',
    name: 'FreeBuff Zero',
    providerId: 'freebuff',
    modelId: 'freebuff-latest',
    specialty: 'Zero-Cost Signal Generation',
    description: 'Free-tier agent that routes through community inference pools. Perfect for paper trading, backtesting, and getting started at zero cost.',
    riskLevel: 'conservative',
    timeHorizon: 'swing',
    icon: '🦬',
    color: 'text-red-400',
    isDefault: true,
    isPremium: false,
  },
]

// ── Helpers ──
export function getAgentsByProvider(providerId: string): TradingAgent[] {
  return TRADING_AGENTS.filter(a => a.providerId === providerId)
}

export function getAgentsByRisk(riskLevel: TradingAgent['riskLevel']): TradingAgent[] {
  return TRADING_AGENTS.filter(a => a.riskLevel === riskLevel)
}

export function getAgentsByTimeHorizon(horizon: TradingAgent['timeHorizon']): TradingAgent[] {
  return TRADING_AGENTS.filter(a => a.timeHorizon === horizon)
}

export function getDefaultAgents(): TradingAgent[] {
  return TRADING_AGENTS.filter(a => a.isDefault)
}

export function getPremiumAgents(): TradingAgent[] {
  return TRADING_AGENTS.filter(a => a.isPremium)
}
