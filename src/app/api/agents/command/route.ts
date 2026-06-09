export async function POST(req) {
  const { command } = await req.json();
  // Placeholder: integrate with Hermes agents in future.
  const result = `Agent processed command: ${command}`;
  return new Response(JSON.stringify({ result }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}
