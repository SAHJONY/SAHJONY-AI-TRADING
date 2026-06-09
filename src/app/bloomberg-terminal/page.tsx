export const dynamic = 'force-dynamic'; // Force server‑side rendering each request

export default function BloombergTerminalPage() {
  return (
    <div className="min-h-screen bg-background text-white p-4">
      <h1 className="text-3xl font-bold mb-4">AI Agentic Bloomberg Terminal</h1>
      <div className="grid grid-cols-3 gap-4 mt-4">
        <div className="bg-gray-800 p-6 rounded text-center">Square 1</div>
        <div className="bg-gray-800 p-6 rounded text-center">Square 2</div>
        <div className="bg-gray-800 p-6 rounded text-center">Square 3</div>
      </div>
    </div>
  );
}
