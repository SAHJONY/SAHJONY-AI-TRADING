// src/app/page.tsx
// Landing page for Sahjony Capital

export default function HomePage() {
  return (
    <main className="min-h-screen bg-black text-white flex flex-col items-center justify-center px-4">
      <h1 className="text-5xl md:text-6xl font-bold text-blue-400 mb-6">
        Sahjony Capital
      </h1>
      <h2 className="text-xl md:text-2xl text-gray-300 text-center max-w-2xl mb-8">
        AI‑powered autonomous trading platform delivering real‑time market intelligence and automated execution.
      </h2>
      <div className="flex space-x-4 mb-12">
        <a href="/dashboard" className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-6 rounded">
          Go to Dashboard
        </a>
        <a href="#waitlist" className="bg-gray-800 hover:bg-gray-700 text-white font-semibold py-3 px-6 rounded">
          Join Waitlist
        </a>
      </div>
      {/* Three static squares */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl">
        <div className="bg-gray-800 p-8 rounded text-center">
          <h3 className="text-2xl font-semibold mb-2">Strategy</h3>
          <p className="text-gray-400">AI agents generate high‑frequency signals.</p>
        </div>
        <div className="bg-gray-800 p-8 rounded text-center">
          <h3 className="text-2xl font-semibold mb-2">Risk</h3>
          <p className="text-gray-400">Dynamic risk management protects capital.</p>
        </div>
        <div className="bg-gray-800 p-8 rounded text-center">
          <h3 className="text-2xl font-semibold mb-2">Execution</h3>
          <p className="text-gray-400">Low‑latency order routing across exchanges.</p>
        </div>
      </div>
    </main>
  );
}
