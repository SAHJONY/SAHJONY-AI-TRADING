export const dynamic = 'force-dynamic'; // Force server-side rendering each request

export default async function BloombergTerminalPage() {
  // Fetch real-time financial data from our API route
  let financialData = null;
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_BASE_URL || ''}/api/financial-data`);
    if (res.ok) {
      financialData = await res.json();
    }
  } catch (e) {
    // ignore fetch errors – will show placeholder
  }

  // Placeholder provider statuses (replace with real health checks if available)
  const providers = {
    Hermes: 'online',
    OpenClaw: 'online',
    FreeBuff: 'online',
    NVIDIA: 'online',
  };

  return (
    <div className="min-h-screen bg-background text-white p-4">
      <h1 className="text-3xl font-bold mb-4">AI Agentic Trading Dashboard</h1>
      <h2 className="text-xl mb-2">Provider Status</h2>
      <div className="grid grid-cols-2 gap-4 mb-6">
        {Object.entries(providers).map(([name, status]) => (
          <div key={name} className="bg-gray-800 p-4 rounded">
            <strong>{name}:</strong> {status}
          </div>
        ))}
      </div>
      <h2 className="text-xl mb-2">Real-time Financial Data</h2>
      <pre className="bg-gray-900 p-4 rounded whitespace-pre-wrap">
{financialData ? JSON.stringify(financialData, null, 2) : 'Loading financial data...'}
      </pre>
    </div>
  );
}
