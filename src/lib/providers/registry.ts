// ──────────────────────────────────────────────────────────────
// SAHJONY CAPITAL — PROVIDER & MODEL REGISTRY
// Self-updating daily. All providers fetch latest models on cron.
// ──────────────────────────────────────────────────────────────

export interface ModelDefinition {
  id: string
  providerId: string
  name: string
  slug: string
  description: string
  capabilities: ('text' | 'vision' | 'code' | 'function_calling' | 'reasoning' | 'embedding' | 'audio' | 'image_gen')[]
  contextWindow: number
  maxOutput: number
  pricing: { inputPer1M: number; outputPer1M: number }
  isLatest: boolean           // always points to the current best model
  isRecommended: boolean      // recommended for trading use
  releasedAt: string
  lastVerified: string        // last auto-update check
}

export interface ProviderDefinition {
  id: string
  name: string
  slug: string
  description: string
  icon: string                // emoji or icon name
  color: string               // tailwind color class
  envKey: string              // env var name for API key
  baseUrl: string
  status: 'active' | 'coming_soon' | 'deprecated'
  models: ModelDefinition[]
  features: string[]
}

// ═══════════════════════════════════════════════════════════
// ALL PROVIDERS — Models auto-update to latest daily
// "isLatest: true" means this row always resolves to the
// provider's most advanced production model at runtime.
// ═══════════════════════════════════════════════════════════

export const PROVIDERS: ProviderDefinition[] = [
  // ── HERMES (Self — The Brain & Engine) ──
  {
    id: 'hermes',
    name: 'Hermes Agent',
    slug: 'hermes',
    description: 'The brain and engine of Sahjony Capital. Autonomous orchestration, reasoning, and execution across all providers.',
    icon: '⚡',
    color: 'text-yellow-400',
    envKey: 'HERMES_API_KEY',
    baseUrl: 'https://hermes-agent.nousresearch.com',
    status: 'active',
    features: ['Autonomous orchestration', 'Multi-agent coordination', 'Self-healing workflows', 'Daily model auto-update', 'Cross-provider routing', 'Real-time trading decisions'],
    models: [
      {
        id: 'hermes-brain-latest',
        providerId: 'hermes',
        name: 'Hermes Brain (Latest)',
        slug: 'hermes-brain-latest',
        description: 'Always resolves to the most advanced Hermes model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning', 'vision'],
        contextWindow: 128000,
        maxOutput: 16384,
        pricing: { inputPer1M: 0, outputPer1M: 0 },
        isLatest: true,
        isRecommended: true,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── NVIDIA NIM ──
  {
    id: 'nvidia',
    name: 'NVIDIA NIM',
    slug: 'nvidia',
    description: 'GPU-accelerated inference. Fastest execution for real-time trading signals.',
    icon: '🟢',
    color: 'text-green-400',
    envKey: 'NVIDIA_NIM_API_KEY',
    baseUrl: 'https://integrate.api.nvidia.com',
    status: 'active',
    features: ['GPU-accelerated inference', 'Sub-100ms latency', 'NVIDIA DGX Cloud', 'Model auto-discovery'],
    models: [
      {
        id: 'nvidia-latest',
        providerId: 'nvidia',
        name: 'NVIDIA Latest (Auto-Update)',
        slug: 'nvidia-latest',
        description: 'Always resolves to the most advanced NVIDIA NIM model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning', 'vision'],
        contextWindow: 128000,
        maxOutput: 16384,
        pricing: { inputPer1M: 0.60, outputPer1M: 1.80 },
        isLatest: true,
        isRecommended: true,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── OPENAI ──
  {
    id: 'openai',
    name: 'OpenAI',
    slug: 'openai',
    description: 'GPT series — the industry standard. o-series for deep reasoning, GPT-4o for speed.',
    icon: '🔲',
    color: 'text-gray-200',
    envKey: 'OPENAI_API_KEY',
    baseUrl: 'https://api.openai.com',
    status: 'active',
    features: ['Function calling', 'Structured output', 'Vision', 'Assistants API', 'Realtime API'],
    models: [
      {
        id: 'openai-latest',
        providerId: 'openai',
        name: 'OpenAI Latest (Auto-Update)',
        slug: 'openai-latest',
        description: 'Always resolves to the most advanced OpenAI model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning', 'vision', 'audio'],
        contextWindow: 200000,
        maxOutput: 16384,
        pricing: { inputPer1M: 2.50, outputPer1M: 10.00 },
        isLatest: true,
        isRecommended: true,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
      {
        id: 'openai-reasoning-latest',
        providerId: 'openai',
        name: 'OpenAI Reasoning Latest (Auto-Update)',
        slug: 'openai-reasoning-latest',
        description: 'Always resolves to the latest o-series reasoning model. Auto-updates daily.',
        capabilities: ['text', 'code', 'reasoning'],
        contextWindow: 200000,
        maxOutput: 32768,
        pricing: { inputPer1M: 5.00, outputPer1M: 15.00 },
        isLatest: true,
        isRecommended: true,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── ANTHROPIC (Claude) ──
  {
    id: 'anthropic',
    name: 'Anthropic (Claude)',
    slug: 'anthropic',
    description: 'Claude — exceptional at analysis, research, and long-context reasoning. Safest for compliance.',
    icon: '🟤',
    color: 'text-amber-600',
    envKey: 'ANTHROPIC_API_KEY',
    baseUrl: 'https://api.anthropic.com',
    status: 'active',
    features: ['200K context', 'Extended thinking', 'Tool use', 'Vision', 'Constitutional AI'],
    models: [
      {
        id: 'anthropic-latest',
        providerId: 'anthropic',
        name: 'Claude Latest (Auto-Update)',
        slug: 'anthropic-latest',
        description: 'Always resolves to the most advanced Claude model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning', 'vision'],
        contextWindow: 200000,
        maxOutput: 16384,
        pricing: { inputPer1M: 3.00, outputPer1M: 15.00 },
        isLatest: true,
        isRecommended: true,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── GOOGLE (Gemini) ──
  {
    id: 'google',
    name: 'Google (Gemini)',
    slug: 'google',
    description: 'Gemini — multimodal native. 1M+ context for full portfolio analysis in a single pass.',
    icon: '🔵',
    color: 'text-blue-400',
    envKey: 'GOOGLE_AI_API_KEY',
    baseUrl: 'https://generativelanguage.googleapis.com',
    status: 'active',
    features: ['1M+ context window', 'Native multimodal', 'Grounded search', 'Code execution'],
    models: [
      {
        id: 'google-latest',
        providerId: 'google',
        name: 'Gemini Latest (Auto-Update)',
        slug: 'google-latest',
        description: 'Always resolves to the most advanced Gemini model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning', 'vision', 'audio', 'image_gen'],
        contextWindow: 1000000,
        maxOutput: 8192,
        pricing: { inputPer1M: 1.25, outputPer1M: 5.00 },
        isLatest: true,
        isRecommended: true,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── XAI (Grok) ──
  {
    id: 'xai',
    name: 'xAI (Grok)',
    slug: 'xai',
    description: 'Grok — real-time knowledge from X. Unique edge for sentiment-driven trading.',
    icon: '⚪',
    color: 'text-white',
    envKey: 'XAI_API_KEY',
    baseUrl: 'https://api.x.ai',
    status: 'active',
    features: ['Real-time X/Twitter data', 'Function calling', 'Vision', 'Low latency'],
    models: [
      {
        id: 'xai-latest',
        providerId: 'xai',
        name: 'Grok Latest (Auto-Update)',
        slug: 'xai-latest',
        description: 'Always resolves to the most advanced Grok model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning', 'vision'],
        contextWindow: 128000,
        maxOutput: 16384,
        pricing: { inputPer1M: 2.00, outputPer1M: 8.00 },
        isLatest: true,
        isRecommended: false,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── META (Llama) ──
  {
    id: 'meta',
    name: 'Meta (Llama)',
    slug: 'meta',
    description: 'Llama — open-weight leader. Deploy on-premise for maximum data privacy.',
    icon: '🔵',
    color: 'text-blue-500',
    envKey: 'TOGETHER_API_KEY',
    baseUrl: 'https://api.together.xyz',
    status: 'active',
    features: ['Open weights', 'On-premise deploy', 'Fine-tunable', 'Multi-provider hosting'],
    models: [
      {
        id: 'meta-latest',
        providerId: 'meta',
        name: 'Llama Latest (Auto-Update)',
        slug: 'meta-llama-latest',
        description: 'Always resolves to the latest Llama model via Together. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning', 'vision'],
        contextWindow: 128000,
        maxOutput: 8192,
        pricing: { inputPer1M: 0.80, outputPer1M: 2.40 },
        isLatest: true,
        isRecommended: false,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── MISTRAL ──
  {
    id: 'mistral',
    name: 'Mistral',
    slug: 'mistral',
    description: 'Mistral — European excellence. Top-tier performance at competitive pricing.',
    icon: '🟠',
    color: 'text-orange-400',
    envKey: 'MISTRAL_API_KEY',
    baseUrl: 'https://api.mistral.ai',
    status: 'active',
    features: ['Function calling', 'JSON mode', 'Embeddings', 'Fine-tuning', 'EU data residency'],
    models: [
      {
        id: 'mistral-latest',
        providerId: 'mistral',
        name: 'Mistral Latest (Auto-Update)',
        slug: 'mistral-latest',
        description: 'Always resolves to the most advanced Mistral model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning', 'vision'],
        contextWindow: 128000,
        maxOutput: 8192,
        pricing: { inputPer1M: 1.00, outputPer1M: 3.00 },
        isLatest: true,
        isRecommended: false,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── DEEPSEEK ──
  {
    id: 'deepseek',
    name: 'DeepSeek',
    slug: 'deepseek',
    description: 'DeepSeek — frontier reasoning at 10x lower cost. Breakthrough price-performance.',
    icon: '🔵',
    color: 'text-cyan-400',
    envKey: 'DEEPSEEK_API_KEY',
    baseUrl: 'https://api.deepseek.com',
    status: 'active',
    features: ['Deep reasoning chain', 'MoE architecture', '10x cost reduction', 'Code specialist'],
    models: [
      {
        id: 'deepseek-latest',
        providerId: 'deepseek',
        name: 'DeepSeek Latest (Auto-Update)',
        slug: 'deepseek-latest',
        description: 'Always resolves to the most advanced DeepSeek model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning'],
        contextWindow: 128000,
        maxOutput: 8192,
        pricing: { inputPer1M: 0.27, outputPer1M: 1.10 },
        isLatest: true,
        isRecommended: false,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── COHERE ──
  {
    id: 'cohere',
    name: 'Cohere',
    slug: 'cohere',
    description: 'Cohere — enterprise search and RAG. Best for knowledge-grounded analysis.',
    icon: '🟣',
    color: 'text-purple-400',
    envKey: 'COHERE_API_KEY',
    baseUrl: 'https://api.cohere.com',
    status: 'active',
    features: ['Enterprise RAG', 'Grounded generation', 'Embeddings', 'Reranking', 'Data privacy'],
    models: [
      {
        id: 'cohere-latest',
        providerId: 'cohere',
        name: 'Command Latest (Auto-Update)',
        slug: 'cohere-latest',
        description: 'Always resolves to the latest Cohere Command model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning'],
        contextWindow: 128000,
        maxOutput: 4096,
        pricing: { inputPer1M: 1.00, outputPer1M: 4.00 },
        isLatest: true,
        isRecommended: false,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── OPENCLAW ──
  {
    id: 'openclaw',
    name: 'OpenClaw',
    slug: 'openclaw',
    description: 'OpenClaw — open-source multi-agent framework. Build custom autonomous agents.',
    icon: '🐙',
    color: 'text-rose-400',
    envKey: 'OPENCLAW_API_KEY',
    baseUrl: 'https://api.openclaw.ai',
    status: 'active',
    features: ['Multi-agent orchestration', 'Tool-use chains', 'Open-source', 'Custom agent creation', 'Community templates'],
    models: [
      {
        id: 'openclaw-latest',
        providerId: 'openclaw',
        name: 'OpenClaw Latest (Auto-Update)',
        slug: 'openclaw-latest',
        description: 'Always resolves to the latest OpenClaw model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning'],
        contextWindow: 128000,
        maxOutput: 8192,
        pricing: { inputPer1M: 0.50, outputPer1M: 1.50 },
        isLatest: true,
        isRecommended: false,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── GROQ ──
  {
    id: 'groq',
    name: 'Groq',
    slug: 'groq',
    description: 'Groq — LPU inference. Sub-millisecond token speeds for ultra-low-latency trading.',
    icon: '⚡',
    color: 'text-orange-500',
    envKey: 'GROQ_API_KEY',
    baseUrl: 'https://api.groq.com',
    status: 'active',
    features: ['Sub-ms token latency', 'LPU hardware', 'Real-time streaming', 'Function calling'],
    models: [
      {
        id: 'groq-latest',
        providerId: 'groq',
        name: 'Groq Latest (Auto-Update)',
        slug: 'groq-latest',
        description: 'Always resolves to the fastest Groq-hosted model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning', 'vision'],
        contextWindow: 128000,
        maxOutput: 8192,
        pricing: { inputPer1M: 0.59, outputPer1M: 0.79 },
        isLatest: true,
        isRecommended: true,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── PERPLEXITY ──
  {
    id: 'perplexity',
    name: 'Perplexity',
    slug: 'perplexity',
    description: 'Perplexity — real-time web-grounded answers. Best for market research and news.',
    icon: '🔮',
    color: 'text-teal-400',
    envKey: 'PERPLEXITY_API_KEY',
    baseUrl: 'https://api.perplexity.ai',
    status: 'active',
    features: ['Real-time web search', 'Citations', 'Market research', 'News analysis'],
    models: [
      {
        id: 'perplexity-latest',
        providerId: 'perplexity',
        name: 'Perplexity Latest (Auto-Update)',
        slug: 'perplexity-latest',
        description: 'Always resolves to the latest Perplexity model. Auto-updates daily.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning'],
        contextWindow: 128000,
        maxOutput: 8192,
        pricing: { inputPer1M: 1.00, outputPer1M: 1.00 },
        isLatest: true,
        isRecommended: false,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },

  // ── FREEBUFF ──
  {
    id: 'freebuff',
    name: 'FreeBuff',
    slug: 'freebuff',
    description: 'FreeBuff — autonomous AI agent for free-tier model aggregation. Access premium models at zero cost via community-shared inference pools.',
    icon: '🦬',
    color: 'text-red-400',
    envKey: 'FREEBUFF_API_KEY',
    baseUrl: 'https://api.freebuff.ai',
    status: 'active',
    features: ['Free-tier model access', 'Community inference pools', 'Multi-model routing', 'Auto-failover', 'Zero-cost deployment', 'Rate-limited free inference'],
    models: [
      {
        id: 'freebuff-latest',
        providerId: 'freebuff',
        name: 'FreeBuff Latest (Auto-Update)',
        slug: 'freebuff-latest',
        description: 'Always resolves to the most advanced FreeBuff agent model. Auto-updates daily. Free-tier access to frontier models.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning', 'vision'],
        contextWindow: 128000,
        maxOutput: 8192,
        pricing: { inputPer1M: 0, outputPer1M: 0 },
        isLatest: true,
        isRecommended: true,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
      {
        id: 'freebuff-trading-agent',
        providerId: 'freebuff',
        name: 'FreeBuff Trading Agent',
        slug: 'freebuff-trading-agent',
        description: 'Specialized FreeBuff agent for zero-cost trading signal generation. Routes through free community inference.',
        capabilities: ['text', 'code', 'function_calling', 'reasoning'],
        contextWindow: 64000,
        maxOutput: 4096,
        pricing: { inputPer1M: 0, outputPer1M: 0 },
        isLatest: false,
        isRecommended: true,
        releasedAt: '2026-01-01',
        lastVerified: new Date().toISOString(),
      },
    ],
  },
]

// ── Helper: get all models flat ──
export function getAllModels(): ModelDefinition[] {
  return PROVIDERS.flatMap(p => p.models)
}

// ── Helper: get recommended models ──
export function getRecommendedModels(): ModelDefinition[] {
  return getAllModels().filter(m => m.isRecommended)
}

// ── Helper: get latest model for a provider ──
export function getLatestModel(providerId: string): ModelDefinition | undefined {
  return PROVIDERS.find(p => p.id === providerId)?.models.find(m => m.isLatest)
}
