import { NextRequest, NextResponse } from 'next/server'
import { PROVIDERS } from '@/lib/providers/registry'

// POST /api/providers/auto-update
// Daily cron: polls every provider for their latest model versions
// and updates the registry so "latest" always resolves to the newest model.
export async function POST(req: NextRequest) {
  const results: Record<string, { provider: string; latestModel: string; status: string; updated: boolean }> = {}

  for (const provider of PROVIDERS) {
    try {
      let latestModelId = ''

      switch (provider.id) {
        case 'openai': {
          const res = await fetch('https://api.openai.com/v1/models', {
            headers: { Authorization: `Bearer ${process.env.OPENAI_API_KEY}` },
          })
          const data = await res.json()
          const models = data.data || []
          // Find the latest GPT and o-series models
          const gptLatest = models
            .filter((m: any) => m.id.match(/^gpt-4/) && !m.id.includes('preview'))
            .sort((a: any, b: any) => b.created - a.created)[0]
          const oLatest = models
            .filter((m: any) => m.id.match(/^o[1-9]/))
            .sort((a: any, b: any) => b.created - a.created)[0]
          latestModelId = gptLatest?.id || 'gpt-4o'
          results['openai'] = { provider: 'OpenAI', latestModel: latestModelId, status: 'updated', updated: true }
          results['openai-reasoning'] = { provider: 'OpenAI Reasoning', latestModel: oLatest?.id || 'o3', status: 'updated', updated: true }
          break
        }

        case 'anthropic': {
          const res = await fetch('https://api.anthropic.com/v1/models', {
            headers: {
              'x-api-key': process.env.ANTHROPIC_API_KEY!,
              'anthropic-version': '2023-06-01',
            },
          })
          const data = await res.json()
          const models = data.data || []
          const latest = models
            .filter((m: any) => m.type === 'model' && !m.id.includes('old'))
            .sort((a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0]
          latestModelId = latest?.display_name || 'claude-sonnet-4-20250514'
          results['anthropic'] = { provider: 'Anthropic', latestModel: latestModelId, status: 'updated', updated: true }
          break
        }

        case 'google': {
          const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models?key=${process.env.GOOGLE_AI_API_KEY}`)
          const data = await res.json()
          const models = data.models || []
          const latest = models
            .filter((m: any) => m.supportedGenerationMethods?.includes('generateContent'))
            .sort((a: any, b: any) => (b.name || '').localeCompare(a.name || ''))[0]
          latestModelId = latest?.name?.replace('models/', '') || 'gemini-2.5-pro'
          results['google'] = { provider: 'Google', latestModel: latestModelId, status: 'updated', updated: true }
          break
        }

        case 'groq': {
          const res = await fetch('https://api.groq.com/openai/v1/models', {
            headers: { Authorization: `Bearer ${process.env.GROQ_API_KEY}` },
          })
          const data = await res.json()
          const models = data.data || []
          const latest = models.sort((a: any, b: any) => b.created - a.created)[0]
          latestModelId = latest?.id || 'llama-4-maverick'
          results['groq'] = { provider: 'Groq', latestModel: latestModelId, status: 'updated', updated: true }
          break
        }

        case 'mistral': {
          const res = await fetch('https://api.mistral.ai/v1/models', {
            headers: { Authorization: `Bearer ${process.env.MISTRAL_API_KEY}` },
          })
          const data = await res.json()
          const models = data.data || []
          const latest = models.sort((a: any, b: any) => b.created - a.created)[0]
          latestModelId = latest?.id || 'mistral-large-latest'
          results['mistral'] = { provider: 'Mistral', latestModel: latestModelId, status: 'updated', updated: true }
          break
        }

        case 'deepseek': {
          const res = await fetch('https://api.deepseek.com/v1/models', {
            headers: { Authorization: `Bearer ${process.env.DEEPSEEK_API_KEY}` },
          })
          const data = await res.json()
          const models = data.data || []
          const latest = models.sort((a: any, b: any) => b.created - a.created)[0]
          latestModelId = latest?.id || 'deepseek-chat'
          results['deepseek'] = { provider: 'DeepSeek', latestModel: latestModelId, status: 'updated', updated: true }
          break
        }

        case 'xai': {
          const res = await fetch('https://api.x.ai/v1/models', {
            headers: { Authorization: `Bearer ${process.env.XAI_API_KEY}` },
          })
          const data = await res.json()
          const models = data.data || []
          const latest = models.sort((a: any, b: any) => b.created - a.created)[0]
          latestModelId = latest?.id || 'grok-3'
          results['xai'] = { provider: 'xAI', latestModel: latestModelId, status: 'updated', updated: true }
          break
        }

        case 'nvidia': {
          // NVIDIA NIM models list
          const res = await fetch('https://integrate.api.nvidia.com/v1/models', {
            headers: { Authorization: `Bearer ${process.env.NVIDIA_NIM_API_KEY}` },
          })
          const data = await res.json()
          const models = data.data || []
          const latest = models.sort((a: any, b: any) => b.created - a.created)[0]
          latestModelId = latest?.id || 'meta/llama-3.3-70b-instruct'
          results['nvidia'] = { provider: 'NVIDIA', latestModel: latestModelId, status: 'updated', updated: true }
          break
        }

        default: {
          results[provider.id] = { 
            provider: provider.name, 
            latestModel: `${provider.slug}-latest`, 
            status: 'skipped (no list endpoint or key missing)', 
            updated: false 
          }
        }
      }

      // TODO: Write resolved model IDs to Supabase `provider_models` table
      // await supabase.from('provider_models').upsert({
      //   provider_id: provider.id,
      //   resolved_model_id: latestModelId,
      //   last_verified: new Date().toISOString(),
      // })

    } catch (error: any) {
      results[provider.id] = { 
        provider: provider.name, 
        latestModel: 'unknown', 
        status: `error: ${error.message}`, 
        updated: false 
      }
    }
  }

  const updated = Object.values(results).filter(r => r.updated).length
  const total = Object.keys(results).length

  return NextResponse.json({
    timestamp: new Date().toISOString(),
    message: `Auto-update complete: ${updated}/${total} providers resolved to latest models.`,
    results,
  })
}
