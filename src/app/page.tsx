// src/app/page.tsx
// Professional landing page for Sahjony Capital

export default async function LandingPage() {
  // Placeholder supabase client – real implementation will be added later
  const supabase = await (async () => ({ auth: { getUser: async () => ({ data: { user: null } }) } }))();
  const { data: { user } } = await supabase.auth.getUser();

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex flex-col">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700">
        <div className="container mx-auto flex items-center justify-between py-4 px-6">
          <h1 className="text-2xl font-bold text-indigo-400">Sahjony Capital</h1>
          <nav className="space-x-4">
            <a href="/dashboard" className="text-gray-300 hover:text-white transition">Dashboard</a>
            <a href="#waitlist" className="text-gray-300 hover:text-white transition">Waitlist</a>
            <a href="/contact" className="text-gray-300 hover:text-white transition">Contact</a>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="flex-1 bg-gradient-to-br from-gray-800 to-gray-700 flex items-center justify-center">
        <div className="container mx-auto text-center px-6 py-20">
          <h2 className="text-5xl md:text-6xl font-extrabold text-white mb-6">
            AI‑Powered Autonomous Trading
          </h2>
          <p className="text-xl md:text-2xl text-gray-300 max-w-2xl mx-auto mb-8">
            Harness cutting‑edge large language models, real‑time market data, and automated execution to generate alpha across 60+ exchanges.
          </p>
          <div className="flex flex-col md:flex-row justify-center gap-4">
            <a href="/dashboard" className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 px-8 rounded transition">
              Go to Dashboard
            </a>
            <a href="#waitlist" className="bg-gray-700 hover:bg-gray-600 text-white font-medium py-3 px-8 rounded transition">
              Join Waitlist
            </a>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="bg-gray-800 py-16">
        <div className="container mx-auto px-6 grid md:grid-cols-3 gap-8">
          <div className="bg-gray-700 rounded-lg p-6 text-center">
            <h3 className="text-2xl font-semibold text-indigo-400 mb-3">Strategy Engine</h3>
            <p className="text-gray-300">AI agents generate multi‑frequency signals, back‑tested across historic data.</p>
          </div>
          <div className="bg-gray-700 rounded-lg p-6 text-center">
            <h3 className="text-2xl font-semibold text-indigo-400 mb-3">Risk Management</h3>
            <p className="text-gray-300">Dynamic VaR, drawdown controls, and capital allocation protect assets.</p>
          </div>
          <div className="bg-gray-700 rounded-lg p-6 text-center">
            <h3 className="text-2xl font-semibold text-indigo-400 mb-3">Execution Layer</h3>
            <p className="text-gray-300">Low‑latency order routing, multi‑exchange support, and auto‑rebalance.</p>
          </div>
        </div>
      </section>

      {/* Waitlist CTA */}
      <section id="waitlist" className="bg-gray-900 py-12">
        <div className="container mx-auto text-center px-6">
          <h4 className="text-3xl font-semibold text-indigo-400 mb-4">Early Access Program</h4>
          <p className="text-gray-400 mb-6 max-w-xl mx-auto">
            Join our private alpha to test the platform, receive updates, and shape the product roadmap.
          </p>
          <form className="max-w-md mx-auto space-y-4" method="POST" action="/api/waitlist">
            <input type="text" name="name" placeholder="Name" required className="w-full px-4 py-2 bg-gray-800 border border-gray-600 rounded text-gray-100" />
            <input type="email" name="email" placeholder="Email" required className="w-full px-4 py-2 bg-gray-800 border border-gray-600 rounded text-gray-100" />
            <button type="submit" className="w-full bg-indigo-600 hover:bg-indigo-700 text-white py-3 rounded font-medium transition">
              Join Waitlist
            </button>
          </form>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-gray-800 py-4">
        <div className="container mx-auto text-center text-gray-500 text-sm">
          © {new Date().getFullYear()} Sahjony Capital • All rights reserved.
        </div>
      </footer>
    </div>
  );
}
