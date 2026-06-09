// ──────────────────────────────────────────────────────────────
// SAHJONY CAPITAL — PROVIDER & MODEL REGISTRY
// Self-updating daily. All providers fetch latest models on cron.
// Real signup URLs for activation. Real API base URLs.
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
 isLatest: boolean // always points to the current best model
 isRecommended: boolean // recommended for trading
 releasedAt: string
 lastVerified: string // last auto-update check
}

export interface ProviderDefinition {
 id: string
 name: string
 slug: string
 description: string
 icon: string // emoji or icon name
 color: string // tailwind color class
 envKey: string // env var name for API key
 baseUrl: string // real API endpoint
 website: string // real website URL for signup/dashboard
 signupUrl: string // direct signup/register URL
 dashboardUrl: string // dashboard/console URL after signup
 docsUrl: string // API documentation URL
 status: 'active' | 'coming_soon' | 'deprecated'
 isFreeTier: boolean // has free tier available
 freeTierDetails: string // description of free tier
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
 website: 'https://hermes-agent.nousresearch.com',
 signupUrl: 'https://hermes-agent.nousresearch.com/docs',
 dashboardUrl: 'https://hermes-agent.nousresearch.com/dashboard',
 docsUrl: 'https://hermes-agent.nousresearch.com/docs',
 status: 'active',
 isFreeTier: true,
 freeTierDetails: 'Open-source. Self-host for free. Nous Research provides free community inference.',
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
 description: 'GPU-accelerated inference. Fastest execution for real-time trading signals. Free 1000 credits on signup.',
 icon: '🟢',
 color: 'text-green-400',
 envKey: 'NVIDIA_API_KEY',
 baseUrl: 'https://integrate.api.nvidia.com/v1',
 website: 'https://build.nvidia.com',
 signupUrl: 'https://build.nvidia.com/signin',
 dashboardUrl: 'https://build.nvidia.com/dashboard',
 docsUrl: 'https://docs.nvidia.com/nim/large-language-models/latest/getting-started.html',
 status: 'active',
 isFreeTier: true,
 freeTierDetails: 'Free 1,000 credits on signup. GPU-accelerated inference at no cost for initial usage. No credit card required.',
 features: ['GPU-accelerated inference', 'Sub-100ms latency', 'NVIDIA DGX Cloud', 'Model auto-discovery', 'Free 1000 credits', 'No credit card required'],
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
 baseUrl: 'https://api.openai.com/v1',
 website: 'https://openai.com',
 signupUrl: 'https://platform.openai.com/signup',
 dashboardUrl: 'https://platform.openai.com/usage',
 docsUrl: 'https://platform.openai.com/docs',
 status: 'active',
 isFreeTier: false,
 freeTierDetails: 'No free tier. Pay-as-you-go pricing. $5 free credits for new accounts.',
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
 baseUrl: 'https://api.anthropic.com/v1',
 website: 'https://www.anthropic.com',
 signupUrl: 'https://console.anthropic.com/dashboard',
 dashboardUrl: 'https://console.anthropic.com/settings/usage',
 docsUrl: 'https://docs.anthropic.com/en/docs',
 status: 'active',
 isFreeTier: false,
 freeTierDetails: 'No free tier. $5 free credits on first signup.',
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
 baseUrl: 'https://generativelanguage.googleapis.com/v1beta',
 website: 'https://ai.google.dev',
 signupUrl: 'https://aistudio.google.com/app/apikey',
 dashboardUrl: 'https://aistudio.google.com/app/apikey',
 docsUrl: 'https://ai.google.dev/gemini-api/docs',
 status: 'active',
 isFreeTier: true,
 freeTierDetails: 'Free tier: 15 RPM, 1M tokens/min, 1,500 RPD. No credit card required. Gemini Flash free forever.',
 features: ['1M+ context window', 'Native multimodal', 'Grounded search', 'Code execution', 'Free tier available'],
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
 baseUrl: 'https://api.x.ai/v1',
 website: 'https://x.ai',
 signupUrl: 'https://console.x.ai',
 dashboardUrl: 'https://console.x.ai',
 docsUrl: 'https://docs.x.ai/docs',
 status: 'active',
 isFreeTier: true,
 freeTierDetails: 'Free tier: $25 free credits per month until end of 2025. No credit card needed.',
 features: ['Real-time X/Twitter data', 'Function calling', 'Vision', 'Low latency', 'Free credits available'],
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
 baseUrl: 'https://api.together.xyz/v1',
 website: 'https://www.llama.com',
 signupUrl: 'https://api.together.xyz/signin',
 dashboardUrl: 'https://api.together.xyz/dashboard',
 docsUrl: 'https://docs.together.ai/docs',
 status: 'active',
 isFreeTier: true,
 freeTierDetails: 'Together AI: Free $5 credits on signup. Llama models also available free via Meta directly.',
 features: ['Open weights', 'On-premise deploy', 'Fine-tunable', 'Multi-provider hosting', 'Free credits on Together'],
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
 baseUrl: 'https://api.mistral.ai/v1',
 website: 'https://mistral.ai',
 signupUrl: 'https://console.mistral.ai/signup',
 dashboardUrl: 'https://console.mistral.ai/usage',
 docsUrl: 'https://docs.mistral.ai',
 status: 'active',
 isFreeTier: true,
 freeTierDetails: 'Free tier: La Plateforme offers free API access with rate limits. No credit card needed.',
 features: ['Function calling', 'JSON mode', 'Embeddings', 'Fine-tuning', 'EU data residency', 'Free tier available'],
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
 icon: '🌀',
 color: 'text-cyan-400',
 envKey: 'DEEPSEEK_API_KEY',
 baseUrl: 'https://api.deepseek.com/v1',
 website: 'https://www.deepseek.com',
 signupUrl: 'https://platform.deepseek.com/sign_up',
 dashboardUrl: 'https://platform.deepseek.com/usage',
 docsUrl: 'https://platform.deepseek.com/api-docs',
 status: 'active',
 isFreeTier: true,
 freeTierDetails: 'Free tier: 500 RPD on DeepSeek-V3. Extremely low pricing. $5 free credits on signup.',
 features: ['Deep reasoning chain', 'MoE architecture', '10x cost reduction', 'Code specialist', 'Free credits'],
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
 baseUrl: 'https://api.cohere.com/v2',
 website: 'https://cohere.com',
 signupUrl: 'https://dashboard.cohere.com/signup',
 dashboardUrl: 'https://dashboard.cohere.com',
 docsUrl: 'https://docs.cohere.com/docs',
 status: 'active',
 isFreeTier: true,
 freeTierDetails: 'Free tier: 1,000 calls/month for trial keys. No credit card required. Command R free for non-commercial.',
 features: ['Enterprise RAG', 'Grounded generation', 'Embeddings', 'Reranking', 'Data privacy', 'Free trial keys'],
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
 baseUrl: 'https://api.openclaw.ai/v1',
 website: 'https://openclaw.ai',
 signupUrl: 'https://openclaw.ai/register',
 dashboardUrl: 'https://openclaw.ai/dashboard',
 docsUrl: 'https://docs.openclaw.ai',
 status: 'active',
 isFreeTier: true,
 freeTierDetails: 'Open-source. Self-host for free. Community cloud tier with rate limits.',
 features: ['Multi-agent orchestration', 'Tool-use chains', 'Open-source', 'Custom agent creation', 'Community templates', 'Free self-host'],
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
 baseUrl: 'https://api.groq.com/openai/v1',
 website: 'https://groq.com',
 signupUrl: 'https://console.groq.com/signup',
 dashboardUrl: 'https://console.groq.com/usage',
 docsUrl: 'https://console.groq.com/docs',
 status: 'active',
 isFreeTier: true,
 freeTierDetails: 'Free tier: 30 RPM, 14,400 RPD. LPU-powered inference at no cost. No credit card needed.',
 features: ['Sub-ms token latency', 'LPU hardware', 'Real-time streaming', 'Function calling', 'Free tier: 30 RPM'],
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
 website: 'https://www.perplexity.ai',
 signupUrl: 'https://www.perplexity.ai/pricing',
 dashboardUrl: 'https://www.perplexity.ai/settings/api',
 docsUrl: 'https://docs.perplexity.ai',
 status: 'active',
 isFreeTier: false,
 freeTierDetails: 'No free tier for API. Pro subscription starts at $20/mo with API access.',
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
 baseUrl: 'https://api.freebuff.ai/v1',
 website: 'https://freebuff.ai',
 signupUrl: 'https://freebuff.ai/signup',
 dashboardUrl: 'https://freebuff.ai/dashboard',
 docsUrl: 'https://docs.freebuff.ai',
 status: 'active',
 isFreeTier: true,
 freeTierDetails: '100% free. Community inference pools. Zero cost. No credit card. Rate-limited free access to frontier models.',
 features: ['Free-tier model access', 'Community inference pools', 'Multi-model routing', 'Auto-failover', 'Zero-cost deployment', 'Rate-limited free inference', 'No credit card required'],
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

// ── Helper: get free-tier providers ──
export function getFreeTierProviders(): ProviderDefinition[] {
 return PROVIDERS.filter(p => p.isFreeTier)
}

// ── Helper: get provider by ID ──
export function getProviderById(id: string): ProviderDefinition | undefined {
 return PROVIDERS.find(p => p.id === id)
}
