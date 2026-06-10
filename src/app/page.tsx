// src/app/page.tsx
import TopNav from '@/components/topnav'
import CinematicBackground from '@/components/CinematicBackground'
import Image from 'next/image'
import Link from 'next/link'
import { createClient } from '@/app/supabase-server'

// Live metrics (placeholders)
const stats = [
  { value: '120+', label: 'Markets Monitored' },
  { value: '3.5k+', label: 'Signals Generated' },
  { value: '12', label: 'Active Strategies' },
  { value: '12‑mo ROI 18%', label: 'Historical Performance' },
  { value: 'Max Drawdown 4%', label: 'Risk Metric' },
]

export default async function HomePage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  // Unauthenticated visitors see the landing page
  if (!user) {
    return (
      <div className="min-h-screen bg-background noise-overlay grid-lines">
        <TopNav />
        <div className="bg-yellow-200 text-black text-center py-2 font-medium">
          Currently in Development — Private Alpha scheduled Q4 2026
        </div>
        <main className="relative">
          <CinematicBackground />

          {/* ===== HERO ===== */}
          <section className="relative overflow-hidden min-h-[92vh] flex items-center">
            <div className="absolute inset-0 tesla-hero-gradient" />
            <div className="container-custom relative z-10 py-32 lg:py-44 mx-auto text-center">
              {/* Status Tag */}
              <div className="inline-flex items-center gap-3 px-5 py-2 rounded-full glass border border-white/[0.04] mb-8 animate-slide-up">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-primary shadow-primary" />
                </span>
                <span className="text-[11px] text-text-secondary font-medium tracking-tesla uppercase">
                  Pre‑Launch Phase — Private Alpha Under Development
                </span>
              </div>

              <h1 className="text-5xl md:text-7xl lg:text-[5.5rem] font-display font-bold text-white mb-7 leading-[0.88] tracking-tight animate-slide-up" style={{ animationDelay: '80ms' }}>
                Autonomous AI Trading Platform
              </h1>

              <p className="text-lg md:text-xl text-text-secondary mb-12 max-w-xl mx-auto leading-relaxed font-light animate-slide-up" style={{ animationDelay: '200ms' }}>
                A multi‑agent intelligence system designed to analyze global markets, simulate probabilistic outcomes, and optimize trading strategies through automated decision execution.
              </p>

              {/* Primary & Secondary CTAs */}
              <div className="flex flex-col sm:flex-row gap-4 justify-center animate-slide-up" style={{ animationDelay: '240ms' }}>
                <Link
                  href="#waitlist"
                  className="rounded-full bg-primary px-6 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/90"
                >
                  Join Early Access Waitlist
                </Link>
                <Link
                  href="#architecture"
                  className="rounded-full bg-surface-elevated px-6 py-2 text-sm font-medium text-primary/80 border border-primary/20 transition-colors hover:bg-surface-elevated/90"
                >
                  View System Architecture
                </Link>
              </div>

              {/* Live Metrics */}
              <ul className="grid grid-cols-2 md:grid-cols-3 gap-6 text-center mt-16 animate-slide-up" style={{ animationDelay: '300ms' }}>
                {stats.map((s) => (
                  <li key={s.label} className="flex flex-col items-center">
                    <span className="text-3xl font-bold text-white">{s.value}</span>
                    <span className="text-sm text-text-secondary">{s.label}</span>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          {/* ===== SECTION 1 – WHAT THIS IS ===== */}
          <section className="py-24 bg-background/5 text-center">
            <h2 className="text-3xl font-semibold mb-6">Next‑Generation Autonomous Trading Intelligence</h2>
            <p className="max-w-3xl mx-auto text-text-secondary leading-relaxed">
              This platform operates as an end‑to‑end trading intelligence system that combines multi‑agent AI market analysis, reinforcement‑learning strategy optimization, risk‑aware capital allocation, and automated execution.
            </p>
          </section>

          {/* ===== SECTION 2 – SYSTEM ARCHITECTURE OVERVIEW ===== */}
          <section id="architecture" className="py-24 bg-surface-elevated text-center">
            <h2 className="text-3xl font-semibold mb-8">System Architecture Overview</h2>
            <div className="max-w-5xl mx-auto space-y-8">
              {/* Layer 1 – Data Intelligence Layer */}
              <div>
                <h3 className="text-xl font-medium mb-2">Data Intelligence Layer</h3>
                <p className="text-text-secondary">Real‑time market data ingestion across crypto, equities, forex, futures.</p>
              </div>
              {/* Layer 2 – AI Decision Layer */}
              <div>
                <h3 className="text-xl font-medium mb-2">AI Decision Layer</h3>
                <p className="text-text-secondary">Multi‑agent strategy generation, pattern recognition, sentiment & macro signal integration.</p>
              </div>
              {/* Layer 3 – Simulation Engine */}
              <div>
                <h3 className="text-xl font-medium mb-2">Simulation Engine</h3>
                <p className="text-text-secondary">Scenario modeling, probabilistic outcome mapping, stress testing of strategies.</p>
              </div>
              {/* Layer 4 – Risk Engine */}
              <div>
                <h3 className="text-xl font-medium mb-2">Risk Engine</h3>
                <p className="text-text-secondary">Drawdown control, exposure balancing, volatility adaptation.</p>
              </div>
              {/* Layer 5 – Execution Layer */}
              <div>
                <h3 className="text-xl font-medium mb-2">Execution Layer</h3>
                <p className="text-text-secondary">Trade routing logic, automated order execution (broker integration – Phase 4).</p>
              </div>
            </div>
            {/* Placeholder architecture diagram */}
            <Image src="/architecture.png" alt="System Architecture Diagram" width={800} height={450} className="mx-auto rounded-xl shadow-lg mt-8" />
          </section>

          {/* ===== SECTION 3 – WHY IT MATTERS ===== */}
          <section className="py-24 bg-background/5 text-center">
            <h2 className="text-3xl font-semibold mb-6">From Reactive Trading to Autonomous Execution Systems</h2>
            <p className="max-w-4xl mx-auto text-text-secondary leading-relaxed">
              Traditional trading suffers from human decision latency, emotional bias, and limited data processing capacity. Our autonomous system removes emotional loops, operates 24/7, optimizes across multiple strategies simultaneously, and adapts dynamically to market conditions.
            </p>
          </section>

          {/* ===== SECTION 4 – DEVELOPMENT STATUS ===== */}
          <section className="py-24 bg-surface-elevated text-center">
            <h2 className="text-3xl font-semibold mb-6">Current Development Phase</h2>
            <ul className="list-disc list-inside max-w-2xl mx-auto text-left space-y-2">
              <li>System architecture design – Completed</li>
              <li>AI agent framework – In progress</li>
              <li>Backtesting environment – In development</li>
              <li>Live trading deployment – Not active</li>
              <li>Security & compliance layer – Planned</li>
            </ul>
          </section>

          {/* ===== SECTION 5 – ROADMAP ===== */}
          <section className="py-24 bg-background/5 text-center">
            <h2 className="text-3xl font-semibold mb-6">Development Roadmap</h2>
            <ul className="list-disc list-inside max-w-3xl mx-auto text-left space-y-2">
              <li><strong>Phase 1 – Foundation</strong>: Data infrastructure, AI agent framework.</li>
              <li><strong>Phase 2 – Simulation</strong>: Backtesting engine, strategy modeling.</li>
              <li><strong>Phase 3 – Private Alpha</strong>: Paper‑trading system, closed‑user testing.</li>
              <li><strong>Phase 4 – Live Deployment</strong>: Broker integration, controlled‑capital execution.</li>
            </ul>
          </section>

          {/* ===== SECTION 6 – WAITLIST ===== */}
          <section id="waitlist" className="py-24 bg-surface-elevated text-center">
            <h2 className="text-3xl font-semibold mb-6">Early Access Program</h2>
            <p className="max-w-2xl mx-auto text-text-secondary mb-6">
              Join early access to test autonomous trading modules, receive development updates, and participate in the private alpha rollout.
            </p>
            <form className="max-w-md mx-auto space-y-4" method="POST" action="/api/waitlist">
              <input type="text" name="name" placeholder="Name" required className="w-full px-4 py-2 border rounded" />
              <input type="email" name="email" placeholder="Email" required className="w-full px-4 py-2 border rounded" />
              <input type="text" name="experience" placeholder="Experience level (optional)" className="w-full px-4 py-2 border rounded" />
              <input type="text" name="capital" placeholder="Capital range (optional)" className="w-full px-4 py-2 border rounded" />
              <button type="submit" className="w-full rounded-full bg-primary px-6 py-2 text-white font-medium transition-colors hover:bg-primary/90">
                Join Waitlist
              </button>
            </form>
          </section>

          {/* ===== SECTION 7 – TRUST LAYER / DISCLAIMER ===== */}
          <section className="py-24 bg-background/5 text-center">
            <h2 className="text-3xl font-semibold mb-4">Important Disclaimer</h2>
            <p className="max-w-3xl mx-auto text-text-secondary">
              This system is currently in pre‑production development and does not execute live trades. All modeling and simulations are under active testing and refinement.
            </p>
          </section>

          {/* ===== FUTURE CTA (optional) ===== */}
          <section className="py-12 bg-primary text-center">
            <h2 className="text-2xl font-semibold text-white mb-4">Ready to see the future of autonomous trading?</h2>
            <Link href="#waitlist" className="rounded-full bg-white px-6 py-2 text-primary font-medium transition-colors hover:bg-gray-100">
              Join Early Access
            </Link>
          </section>
        </main>
      </div>
    )
  }

  // Authenticated users see the standard app layout (placeholder)
  return (
    <div className="min-h-screen bg-background noise-overlay grid-lines">
      <TopNav />
      <main className="p-8 text-center">
        <h1 className="text-2xl font-bold">Welcome back!</h1>
        <p className="mt-4">Your dashboard will appear here.</p>
      </main>
    </div>
  )
}
