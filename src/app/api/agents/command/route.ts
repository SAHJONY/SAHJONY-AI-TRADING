import { NextResponse } from 'next/server';

export async function POST(req: any) {
  const { command } = await req.json();
  // Placeholder: integrate with Hermes agents in future.
  const result = `Agent processed command: ${command}`;
  return NextResponse.json({ result });
}
