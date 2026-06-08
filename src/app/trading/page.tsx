import Link from 'next/link'
import { TrendingUp, TrendingDown, BarChart3, Activity, Clock, ArrowUpRight, ArrowDownRight } from 'lucide-react'
import { TopNav } from '@/components/layout/top-nav'
import { createClient } from '@/lib/supabase/server'

export const dynamic = 'force-dynamic'

const mockPositions = [
  { symbol: 'SPY', side: 'Long', pnl: '+2.4%', delta: 0.65, size: '$50K', status: 'open' },
  { symbol: 'QQQ', side: 'Short', pnl: '-0.8%', delta: -0.42, size: '$30K', status: 'open' },
  { symbol: 'TLT', side: 'Long', pnl: '+1.1%', delta: 0.28, size: '$20K', status: 'closed' },
  { symbol: 'GLD', side: 'Long', pnl: '+3.2%', delta: 0.55, size: '$40K', status: 'open' },
]

const mockSignals = [
  { agent: 'Alpha Scout', signal: 'Bullish divergence on SPY 4H', confidence: 87, time: '2m ago' },
  { agent: 'Risk Monitor', signal: 'VIX spike above 25 threshold', confidence: 92, time: '8m ago' },
  { agent: 'Sentiment Engine', signal: 'Fed dovish shift detected in FOMC minutes', confidence: 78, time: '15m ago' },
  { agent: 'Alpha Scout', signal: 'Earnings surprise AAPL +4.2%', confidence: 81, time: '22m ago' },
]

export default async function TradingPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    return (
      <div className="min-h-screen bg-background noise-overlay">
        <TopNav />
        <main className="container-custom py-20">
          <div className="max-w-lg mx-auto text-center">
            <h1 className="text-3xl font-display font-bold text-white mb-4">Trading Floor</h1>
            <p className="text-text-secondary mb-8">Sign in to access live trading data and signals.</p>
            <Link href="/login" className="btn btn-primary px-8 py-3">Sign In</Link>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background noise-overlay">
      <TopNav />
      <main className="container-custom py-8">
        <div className="mb-8 animate-slide-up">
          <h1 className="text-3xl font-display font-bold text-white tracking-tighter">Trading Floor</h1>
          <p className="text-text-secondary mt-1 text-sm font-light">Live positions, signals, and market intelligence</p>
        </div>

        {/* Market Overview */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Portfolio Value', value: '$142.5K', change: '+3.2%', positive: true },
            { label: "Today's P&L", value: '+$4,520', change: '+1.03%', positive: true },
            { label: 'Open Positions', value: '3', change: '', positive: true },
            { label: 'Active Signals', value: '4', change: '', positive: true },
          ].map((stat, i) => (
            <div key={i} className="card-tesla p-5 animate-slide-up" style={{ animationDelay: `${i * 50}ms` }}>
              <p className="text-xs text-text-muted uppercase tracking-wider mb-2">{stat.label}</p>
              <p className="text-2xl font-display font-bold text-white tracking-tight">{stat.value}</p>
              {stat.change && (
                <div className={`flex items-center gap-1 mt-1 text-xs ${stat.positive ? 'text-emerald-400' : 'text-red-400'}`}>
                  {stat.positive ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
                  {stat.change}
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Positions */}
          <div className="lg:col-span-2 animate-slide-up" style={{ animationDelay: '200ms' }}>
            <h2 className="text-lg font-display font-semibold text-white mb-4 tracking-tight">Positions</h2>
            <div className="card-tesla overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left px-5 py-3 text-xs text-text-muted uppercase tracking-wider font-medium">Symbol</th>
                    <th className="text-left px-5 py-3 text-xs text-text-muted uppercase tracking-wider font-medium">Side</th>
                    <th className="text-left px-5 py-3 text-xs text-text-muted uppercase tracking-wider font-medium">Size</th>
                    <th className="text-left px-5 py-3 text-xs text-text-muted uppercase tracking-wider font-medium">Delta</th>
                    <th className="text-left px-5 py-3 text-xs text-text-muted uppercase tracking-wider font-medium">P&L</th>
                    <th className="text-left px-5 py-3 text-xs text-text-muted uppercase tracking-wider font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {mockPositions.map((pos, i) => (
                    <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-white/[0.01] transition-colors">
                      <td className="px-5 py-3.5 text-sm font-medium text-white">{pos.symbol}</td>
                      <td className="px-5 py-3.5 text-sm text-text-secondary">{pos.side}</td>
                      <td className="px-5 py-3.5 text-sm text-text-secondary">{pos.size}</td>
                      <td className="px-5 py-3.5 text-sm text-text-secondary">{pos.delta}</td>
                      <td className={`px-5 py-3.5 text-sm font-medium ${pos.pnl.startsWith('+') ? 'text-emerald-400' : 'text-red-400'}`}>{pos.pnl}</td>
                      <td className="px-5 py-3.5">
                        <span className={`badge ${pos.status === 'open' ? 'badge-success' : 'bg-white/[0.04] text-text-muted border border-border'}`}>
                          {pos.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Signals */}
          <div className="animate-slide-up" style={{ animationDelay: '300ms' }}>
            <h2 className="text-lg font-display font-semibold text-white mb-4 tracking-tight">Live Signals</h2>
            <div className="space-y-3">
              {mockSignals.map((signal, i) => (
                <div key={i} className="card-tesla p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-primary">{signal.agent}</span>
                    <div className="flex items-center gap-1.5 text-xs text-text-dim">
                      <Clock className="h-3 w-3" />
                      {signal.time}
                    </div>
                  </div>
                  <p className="text-sm text-text-secondary leading-relaxed">{signal.signal}</p>
                  <div className="mt-2 flex items-center gap-2">
                    <div className="flex-1 h-1 rounded-full bg-white/[0.04] overflow-hidden">
                      <div
                        className="h-full rounded-full bg-primary transition-all duration-500"
                        style={{ width: `${signal.confidence}%` }}
                      />
                    </div>
                    <span className="text-xs text-text-muted">{signal.confidence}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
