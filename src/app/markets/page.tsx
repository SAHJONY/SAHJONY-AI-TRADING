'use client'

import Link from 'next/link'
import { useState } from 'react'
import { useAuth } from '@/components/providers'
import { TopNav } from '@/components/layout/top-nav'
import { MARKETS, LANGUAGES, getAllRegions, getAllAssetTypes, get247Markets } from '@/lib/global/markets-languages'
import {
  Search, Globe, Clock, Zap, Share2, Download, Languages,
  TrendingUp, CircleDot, BadgeCheck, X, ChevronDown, Copy,
  Sun, Moon, Activity, Eye, RefreshCw, Gift, GiftIcon,
  MonitorSmartphone, QrCode, ExternalLink, Check
} from 'lucide-react'

const assetIcons: Record<string, string> = {
  equities: '📈', forex: '💱', crypto: '₿', futures: '🔮',
  options: '🔲', commodities: '🛢️', bonds: '📋', etfs: '🔄',
  indices: '📊', cfds: '📝',
}

export default function MarketsPage() {
  const { user } = useAuth()
  const [search, setSearch] = useState('')
  const [filterRegion, setFilterRegion] = useState<string>('all')
  const [filterAsset, setFilterAsset] = useState<string>('all')
  const [showShare, setShowShare] = useState(false)
  const [showLanguages, setShowLanguages] = useState(false)
  const [langSearch, setLangSearch] = useState('')
  const [copied, setCopied] = useState(false)

  const regions = getAllRegions()
  const assetTypes = getAllAssetTypes()
  const alwaysOpen = get247Markets()

  const filteredMarkets = MARKETS.filter(m => {
    if (!m.isActive) return false
    if (search && !m.name.toLowerCase().includes(search.toLowerCase()) && !m.country.toLowerCase().includes(search.toLowerCase()) && !m.exchangeCode.toLowerCase().includes(search.toLowerCase())) return false
    if (filterRegion !== 'all' && m.region !== filterRegion) return false
    if (filterAsset !== 'all' && !m.assetTypes.includes(filterAsset as any)) return false
    return true
  })

  const filteredLanguages = LANGUAGES.filter(l => {
    if (!l.isSupported) return false
    if (langSearch && !l.name.toLowerCase().includes(langSearch.toLowerCase()) && !l.nativeName.toLowerCase().includes(langSearch.toLowerCase())) return false
    return true
  })

  const shareUrl = typeof window !== 'undefined' ? window.location.origin : 'https://sahjonycapital.com'
  const shareText = `Join me on Sahjony Capital — the world's most advanced AI agentic trading platform. ${MARKETS.length}+ global markets, 24/7/365 trading, ${LANGUAGES.length} languages. No app store needed.`

  const handleCopyLink = () => {
    navigator.clipboard.writeText(`${shareUrl}?ref=share`)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleShareNative = () => {
    if (navigator.share) {
      navigator.share({ title: 'Sahjony Capital', text: shareText, url: `${shareUrl}?ref=share` })
    }
  }

  const handleInstallPWA = () => {
    // PWA install prompt — no app store needed
    const event = (window as any).deferredPrompt
    if (event) {
      event.prompt()
      event.userChoice.then((result: any) => {
        if (result.outcome === 'accepted') console.log('PWA installed')
      })
    }
  }

  return (
    <div className="min-h-screen bg-background noise-overlay grid-lines">
      <TopNav />
      <main className="container-custom py-8">

        {/* ═══ HEADER ═══ */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6 mb-10 animate-slide-up">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-[14px] bg-primary/[0.06] flex items-center justify-center border border-primary/10">
                <Globe className="h-5 w-5 text-primary" />
              </div>
              <h1 className="text-3xl font-display font-bold text-white tracking-tighter">Global Markets</h1>
            </div>
            <p className="text-text-secondary text-sm font-light ml-[52px]">
              {MARKETS.length} exchanges across {regions.length} regions. {LANGUAGES.length} languages. 24/7/365 trading. Zero app store — share directly.
            </p>
          </div>
          <div className="flex items-center gap-3 ml-[52px] lg:ml-0">
            <button onClick={() => setShowLanguages(true)} className="flex items-center gap-2 px-4 py-2.5 rounded-full glass border border-white/[0.06] text-sm font-medium text-text-secondary hover:text-white hover:bg-white/[0.03] transition-all duration-400">
              <Languages className="h-3.5 w-3.5" />
              {LANGUAGES.length} Languages
            </button>
            <button onClick={() => setShowShare(true)} className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-gradient-to-r from-primary-deep to-primary text-white text-sm font-medium shadow-primary hover:shadow-primary-lg transition-all duration-500">
              <Share2 className="h-3.5 w-3.5" />
              Share App
            </button>
          </div>
        </div>

        {/* ═══ 24/7 BANNER ═══ */}
        <div className="max-w-4xl mx-auto mb-8 p-5 rounded-2xl bg-accent/[0.03] border border-accent/10 animate-slide-up" style={{ animationDelay: '50ms' }}>
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 rounded-[14px] bg-accent/[0.06] flex items-center justify-center border border-accent/10 flex-shrink-0">
              <Zap className="h-5 w-5 text-accent" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">24/7/365 — Markets Never Sleep</p>
              <p className="text-[11px] text-text-dim mt-0.5">
                Crypto and Forex trade around the clock, every day of the year. Plus US pre-market (4:00 AM ET) and after-hours (until 8:00 PM ET).
                When one exchange closes, another opens — your agents trade non-stop across every timezone.
              </p>
            </div>
          </div>
        </div>

        {/* ═══ STATS BAR ═══ */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8 animate-slide-up" style={{ animationDelay: '80ms' }}>
          {[
            { label: 'Exchanges', value: MARKETS.length, icon: '🏦' },
            { label: 'Regions', value: regions.length, icon: '🌍' },
            { label: 'Asset Types', value: assetTypes.length, icon: '📊' },
            { label: 'Languages', value: LANGUAGES.length, icon: '🗣️' },
            { label: '24/7 Markets', value: alwaysOpen.length, icon: '♾️' },
          ].map((stat, i) => (
            <div key={stat.label} className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04] text-center">
              <span className="text-lg">{stat.icon}</span>
              <p className="text-2xl font-display font-bold text-white mt-1">{stat.value}</p>
              <p className="text-[10px] text-text-dim uppercase tracking-tesla">{stat.label}</p>
            </div>
          ))}
        </div>

        {/* ═══ SEARCH + FILTERS ═══ */}
        <div className="flex flex-col md:flex-row gap-4 mb-8 animate-slide-up" style={{ animationDelay: '100ms' }}>
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-text-dim" />
            <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search exchanges, countries..." className="input pl-11" />
          </div>
          <select value={filterRegion} onChange={(e) => setFilterRegion(e.target.value)} className="input w-auto min-w-[150px] appearance-none cursor-pointer">
            <option value="all">All Regions</option>
            {regions.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
          <select value={filterAsset} onChange={(e) => setFilterAsset(e.target.value)} className="input w-auto min-w-[150px] appearance-none cursor-pointer">
            <option value="all">All Assets</option>
            {assetTypes.map(a => <option key={a} value={a}>{assetIcons[a] || '📊'} {a.charAt(0).toUpperCase() + a.slice(1)}</option>)}
          </select>
        </div>

        {/* ═══ MARKET GRID ═══ */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-12">
          {filteredMarkets.map((market, idx) => (
                        <Link key={market.id} href={`/markets/${market.id}`} className="block">
                          <div className="card-tesla p-5 animate-slide-up" style={{ animationDelay: `${120 + idx * 25}ms` }}>
                            <div className="flex items-center justify-between mb-3">
                              <div className="flex items-center gap-3">
                                <span className="text-xl">{market.icon}</span>
                                <div>
                                  <h3 className="text-sm font-display font-semibold text-white tracking-tight">{market.exchange}</h3>
                                  <p className="text-[10px] text-text-dim">{market.country}</p>
                                </div>
                              </div>
                              {market.is247 && (
                                <span className="badge bg-accent/[0.06] border-accent/10 text-[9px] text-accent flex items-center gap-1">
                                  <Zap className="h-2.5 w-2.5" /> 24/7
                                </span>
                              )}
                            </div>

                            <div className="flex flex-wrap gap-1.5 mb-3">
                              {market.assetTypes.map(at => (
                                <span key={at} className="badge bg-white/[0.03] border-white/[0.06] text-[8px] text-text-muted">
                                  {assetIcons[at] || '📊'} {at}
                                </span>
                              ))}
                            </div>

                            <div className="grid grid-cols-3 gap-2 pt-3 border-t border-white/[0.04]">
                              <div>
                                <p className="text-[9px] text-text-dim uppercase">Currency</p>
                                <p className="text-[11px] font-medium text-text-secondary">{market.currency}</p>
                              </div>
                              <div>
                                <p className="text-[9px] text-text-dim uppercase">Open</p>
                                <p className="text-[11px] font-medium text-text-secondary">{market.open}</p>
                              </div>
                              <div>
                                <p className="text-[9px] text-text-dim uppercase">Close</p>
                                <p className="text-[11px] font-medium text-text-secondary">{market.close}</p>
                              </div>
                            </div>
                          </div>
                        </Link>
                      ))}
        </div>

        {/* ═══ SHARE APP MODAL ═══ */}
        {showShare && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setShowShare(false)}>
            <div className="w-full max-w-md card-tesla p-8 animate-slide-up" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-[14px] bg-primary/[0.06] flex items-center justify-center border border-primary/10">
                    <Share2 className="h-5 w-5 text-primary" />
                  </div>
                  <h2 className="text-xl font-display font-semibold text-white">Share Sahjony Capital</h2>
                </div>
                <button onClick={() => setShowShare(false)} className="text-text-dim hover:text-white transition-colors"><X className="h-5 w-5" /></button>
              </div>

              <p className="text-sm text-text-secondary font-light mb-6">
                Share the platform directly — no app store needed. Anyone can access it instantly from any device via the link below. Works as a PWA on mobile and desktop.
              </p>

              {/* Link Copy */}
              <div className="flex gap-3 mb-6">
                <input readOnly value={`${shareUrl}?ref=share`} className="input flex-1 font-mono text-[11px]" />
                <button onClick={handleCopyLink} className={`px-5 py-2.5 rounded-full text-sm font-medium transition-all duration-300 flex items-center gap-2 ${copied ? 'bg-emerald-500/[0.1] border border-emerald-500/20 text-emerald-400' : 'bg-gradient-to-r from-primary-deep to-primary text-white shadow-primary'}`}>
                  {copied ? <><Check className="h-3.5 w-3.5" /> Copied</> : <><Copy className="h-3.5 w-3.5" /> Copy</>}
                </button>
              </div>

              {/* Native Share */}
              {typeof navigator !== 'undefined' && typeof navigator.share === 'function' && (
                <button onClick={handleShareNative} className="w-full flex items-center justify-center gap-2 px-5 py-3 rounded-full glass border border-white/[0.06] text-sm font-medium text-text-secondary hover:text-white hover:bg-white/[0.03] transition-all duration-400 mb-4">
                  <ExternalLink className="h-3.5 w-3.5" /> Share via Device
                </button>
              )}

              {/* PWA Install */}
              <button onClick={handleInstallPWA} className="w-full flex items-center justify-center gap-2 px-5 py-3 rounded-full bg-gradient-to-r from-accent-deep to-accent text-[#1a0a00] text-sm font-semibold shadow-accent hover:shadow-[0_4px_30px_rgba(245,158,11,0.2)] transition-all duration-500 mb-6">
                <MonitorSmartphone className="h-4 w-4" /> Install as App (No App Store)
              </button>

              <p className="text-[10px] text-text-dim text-center">
                PWA install works on Chrome, Edge, and Safari. Users get a native-like app icon on their home screen — no app store, no approval process, instant access.
              </p>
            </div>
          </div>
        )}

        {/* ═══ LANGUAGES MODAL ═══ */}
        {showLanguages && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setShowLanguages(false)}>
            <div className="w-full max-w-2xl card-tesla p-8 animate-slide-up max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-[14px] bg-primary/[0.06] flex items-center justify-center border border-primary/10">
                    <Languages className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h2 className="text-xl font-display font-semibold text-white">{LANGUAGES.length} Languages</h2>
                    <p className="text-[11px] text-text-dim">Full trading interface in your language</p>
                  </div>
                </div>
                <button onClick={() => setShowLanguages(false)} className="text-text-dim hover:text-white transition-colors"><X className="h-5 w-5" /></button>
              </div>

              <div className="relative mb-6">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-4 w-4 text-text-dim" />
                <input type="text" value={langSearch} onChange={(e) => setLangSearch(e.target.value)} placeholder="Search languages..." className="input pl-11" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {filteredLanguages.map(lang => (
                  <div key={lang.code} className="flex items-center justify-between p-3 rounded-xl bg-white/[0.02] border border-white/[0.04] hover:border-white/[0.06] transition-all">
                    <div className="flex items-center gap-3">
                      <span className={`text-[10px] font-mono text-text-dim w-8 ${lang.direction === 'rtl' ? 'text-right' : ''}`}>{lang.code.toUpperCase()}</span>
                      <div>
                        <p className="text-sm font-medium text-white">{lang.name}</p>
                        <p className="text-[10px] text-text-dim">{lang.nativeName}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {lang.direction === 'rtl' && <span className="badge bg-accent/[0.06] border-accent/10 text-[8px] text-accent">RTL</span>}
                      <span className="text-[9px] text-text-dim">{lang.regions.length} regions</span>
                    </div>
                  </div>
                ))}
              </div>

              <p className="text-[10px] text-text-dim text-center mt-6">
                All languages are fully supported across the trading interface, agent conversations, market data, and customer support.
                RTL languages (Arabic, Hebrew, Urdu, Farsi) render correctly in all views.
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
