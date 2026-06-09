import { NextRequest, NextResponse } from 'next/server'

export async function POST(req: NextRequest) {
  try {
    const { agentId, message } = await req.json()

    if (!agentId || !message) {
      return NextResponse.json({ error: 'Missing agentId or message' }, { status: 400 })
    }

    // Forward to NVIDIA NIM API with primary model and fallback list
    const nvidiaApiKey = process.env.NVIDIA_API_KEY
    if (!nvidiaApiKey) {
      return NextResponse.json({ error: 'NVIDIA API key not configured' }, { status: 500 })
    }

    // Primary model from env, defaulting to a known model if not set
    const primaryModel = (process.env.NVIDIA_NIM_MODEL ?? 'meta-llama/llama-3.3-70b-instruct').trim()
    // Fallback models list (comma‑separated) from env
    const fallbackModels = (process.env.NVIDIA_NIM_FALLBACK_MODELS || '')
      .split(',')
      .map(m => m.trim())
      .filter(m => m.length > 0)
    const modelsToTry = [primaryModel, ...fallbackModels]

    let response
    for (const model of modelsToTry) {
      response = await fetch('https://integrate.api.nvidia.com/v1/chat/completions', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${nvidiaApiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model,
          messages: [
            {
              role: 'system',
              content: 'You are a financial AI assistant for Sahjony Capital. Provide concise, data‑driven insights on markets, trading strategies, and risk management. Be institutional‑grade and professional.',
            },
            { role: 'user', content: message },
          ],
          temperature: 0.7,
          max_tokens: 1024,
        }),
      })
      if (response.ok) break // success – exit loop
    }

    if (!response || !response.ok) {
      const errorText = response ? await response.text() : 'No response'
      console.error('NVIDIA API error after fallbacks:', errorText)
      return NextResponse.json({ error: 'AI provider error (all models failed)' }, { status: 502 })
    }

    const data = await response.json()
    const content = data.choices?.[0]?.message?.content || 'No response generated.'

    return NextResponse.json({ content })
  } catch (error) {
    console.error('Chat API error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
