'use client'

import { useParams } from 'next/navigation'
import Link from 'next/link'
import { MARKETS } from '@/lib/global/markets-languages'
import { TopNav } from '@/components/layout/top-nav'
import { ChevronLeft, Zap } from 'lucide-react'

const assetIcons: Record<string, string> = {
  equities: '📈', forex: '💱', crypto: '₿', futures: '🔮',
  options: '🔲', commodities: '🛢️', bonds: '📋', etfs: '🔄',
  indices: '📊', cfds: '📝',
}

export default function MarketDetail() {
  const { id } = useParams() as { id: string }
  const market = MARKETS.find(m => m.id === id)

  if (!market) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-text-secondary">Market not found.</p>
        <Link href="/markets" className="ml-4 text-primary underline">Back to list</Link>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background noise-overlay grid-lines">
      <TopNav />
      <main className="container-custom py-8">
        <div className="flex items-center mb-6">
          <Link href="/markets" className="mr-4 text-text-dim hover:text-white"><ChevronLeft className="h-5 w-5" /></Link>
          <h1 className="text-3xl font-display font-bold text-white">{market.exchange} – {market.country}</h1>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="card-tesla p-6">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-3xl">{market.icon}</span>
              <h2 className="text-xl font-display font-semibold text-white">{market.name}</h2>
            </div>
            {market.is247 && (
              <span className="badge bg-accent/[0.06] border-accent/10 text-sm text-accent flex items-center gap-2 mb-4">
                <Zap className="h-4 w-4" /> 24/7 Market
              </span>
            )}
            <p className="text-text-secondary mb-4">Region: <span className="text-white">{market.region}</span></p>
            <p className="text-text-secondary mb-4">Timezone: <span className="text-white">{market.timezone}</span></p>
            <p className="text-text-secondary mb-4">Trading hours: <span className="text-white">{market.open} – {market.close}</span></p>
            <p className="text-text-secondary mb-4">Currency: <span className="text-white">{market.currency}</span></p>
            <div className="flex flex-wrap gap-2 mt-4">
              {market.assetTypes.map(at => (
                <span key={at} className="badge bg-white/[0.03] border-white/[0.06] text-sm text-text-muted">
                  {assetIcons[at] || '📊'} {at}
                </span>
              ))}
            </div>
          </div>

          {/* Placeholder for live market chart / stats */}
          <div className="card-tesla p-6 flex items-center justify-center text-text-dim">
            <p>Live market data / chart will appear here.</p>
          </div>
        </div>
      </main>
    </div>
  )
}
