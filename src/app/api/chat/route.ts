import { NextRequest, NextResponse } from 'next/server'

export async function POST(req: NextRequest) {
  try {
    const { agentId, message } = await req.json()

    if (!agentId || !message) {
      return NextResponse.json({ error: 'Missing agentId or message' }, { status: 400 })
    }

    // Forward to NVIDIA NIM API
    const nvidiaApiKey = process.env.NVIDIA_API_KEY
    if (!nvidiaApiKey) {
      return NextResponse.json({ error: 'NVIDIA API key not configured' }, { status: 500 })
    }

    const response = await fetch('https://integrate.api.nvidia/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${nvidiaApiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        model: 'meta-llama/llama-3.3-70b-instruct',
        messages: [
          {
            role: 'system',
            content: 'You are a financial AI assistant for Sahjony Capital. Provide concise, data-driven insights on markets, trading strategies, and risk management. Be institutional-grade and professional.',
          },
          { role: 'user', content: message },
        ],
        temperature: 0.7,
        max_tokens: 1024,
      }),
    })

    if (!response.ok) {
      const errorText = await response.text()
      console.error('NVIDIA API error:', errorText)
      return NextResponse.json({ error: 'AI provider error' }, { status: 502 })
    }

    const data = await response.json()
    const content = data.choices?.[0]?.message?.content || 'No response generated.'

    return NextResponse.json({ content })
  } catch (error) {
    console.error('Chat API error:', error)
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 })
  }
}
