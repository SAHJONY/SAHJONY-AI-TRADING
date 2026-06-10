import { promises as fs } from 'fs'
import * as path from 'path'
import { NextResponse } from 'next/server'

export async function POST(request: Request) {
  try {
    const vars: { key: string; value: string }[] = await request.json()
    const lines = vars.map(v => `${v.key.trim()}=${v.value.trim()}`)
    const envPath = path.resolve(process.cwd(), '.env')
    await fs.appendFile(envPath, '\n' + lines.join('\n'))
    return NextResponse.json({ ok: true })
  } catch (err) {
    console.error('Env write error', err)
    return new NextResponse('Failed to write env', { status: 500 })
  }
}
