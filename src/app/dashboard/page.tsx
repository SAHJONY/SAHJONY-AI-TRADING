// src/app/dashboard/page.tsx
import { useState } from 'react'
import Image from 'next/image'
import Link from 'next/link'

// Simple placeholder icons (replace with proper icons in production)
const Icon = ({name}: {name: string}) => (
  <span className="inline-block w-5 h-5 bg-primary/20 rounded-full mr-2" />
)

// === Header ===
function DashboardHeader() {
  return (
    <header className="h-16 flex items-center justify-between px-4 border-b border-white/5 bg-surface-elevated/30">
      <div className="flex items-center space-x-2">
        <Image src="/logo.svg" alt="Sahjony" width={32} height={32} className="object-contain" />
        <span className="text-lg font-medium text-white">Sahjony Capital</span>
      </div>
      <div className="flex items-center space-x-4">
        <span className="flex items-center gap-1 text-green-400 text-sm">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-green-400 shadow-green-400" />
          </span>
          Live
        </span>
        <button className="rounded-full bg-primary px-3 py-1 text-sm text-white hover:bg-primary/90">
          Account
        </button>
      </div>
    </header>
  )
}

// === Sidebar ===
function DashboardSidebar({selected, setSelected}: {selected: string, setSelected: (s:string)=>void}) {
  const items = [
    {id: 'overview', label: 'Overview', icon: 'home'},
    {id: 'market', label: 'Live Market', icon: 'chart'},
    {id: 'strategy', label: 'Strategy Engine', icon: 'brain'},
    {id: 'portfolio', label: 'Portfolio', icon: 'wallet'},
    {id: 'risk', label: 'Risk', icon: 'shield'},
    {id: 'settings', label: 'Settings', icon: 'settings'},
  ]
  return (
    <aside className="hidden md:flex flex-col w-60 border-r border-white/5 bg-surface-elevated/30">
      <nav className="flex-1 py-4 space-y-1">
        {items.map(i => (
          <button
            key={i.id}
            onClick={() => setSelected(i.id)}
            className={`w-full flex items-center px-4 py-2 text-left ${selected===i.id ? 'bg-primary/10 text-primary' : 'text-text-secondary hover:bg-white/5'}`}
          >
            <Icon name={i.icon} />
            <span>{i.label}</span>
          </button>
        ))}
      </nav>
    </aside>
  )
}

// === Tab Panels (very simple placeholders) ===
function OverviewPanel() {
  return (
    <div className="p-6">
      <h2 className="text-2xl font-semibold mb-4 text-white">Dashboard Overview</h2>
      <p className="text-text-secondary">Real‑time stats and quick actions will appear here.</p>
    </div>
  )
}

function LiveMarketPanel() {
  return (
    <div className="p-6 space-y-4">
      <h2 className="text-2xl font-semibold text-white mb-4">Live Market</h2>
      <div className="overflow-auto rounded-lg border border-white/5">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-surface-elevated/30">
            <tr>
              <th className="px-4 py-2">Symbol</th>
              <th className="px-4 py-2">Last</th>
              <th className="px-4 py-2">%Δ</th>
              <th className="px-4 py-2">Bid</th>
              <th className="px-4 py-2">Ask</th>
              <th className="px-4 py-2">Volume</th>
              <th className="px-4 py-2">Signal</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {[
              {sym: 'BTC/USD', last: 28750, change: '+1.2', bid: 28748, ask: 28752, vol: '1.3k', sig: 'buy'},
              {sym: 'AAPL', last: 184.3, change: '-0.4', bid: 184.2, ask: 184.4, vol: '2.1M', sig: 'hold'},
              {sym: 'EUR/USD', last: 1.0923, change: '+0.03', bid: 1.0922, ask: 1.0924, vol: '4.5M', sig: 'sell'},
            ].map((r,i)=>(
              <tr key={i} className="hover:bg-white/5">
                <td className="px-4 py-2 text-white">{r.sym}</td>
                <td className="px-4 py-2 text-white">{r.last}</td>
                <td className="px-4 py-2 text-green-400">{r.change}</td>
                <td className="px-4 py-2 text-white">{r.bid}</td>
                <td className="px-4 py-2 text-white">{r.ask}</td>
                <td className="px-4 py-2 text-white">{r.vol}</td>
                <td className="px-4 py-2">
                  <span className={
                    r.sig==='buy' ? 'bg-green-500/20 text-green-400 px-2 py-0.5 rounded' :
                    r.sig==='sell' ? 'bg-red-500/20 text-red-400 px-2 py-0.5 rounded' :
                    'bg-gray-500/20 text-gray-400 px-2 py-0.5 rounded'
                  }>{r.sig.toUpperCase()}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function StrategyEnginePanel() {
  return (
    <div className="p-6 space-y-4">
      <h2 className="text-2xl font-semibold text-white mb-4">Strategy Engine</h2>
      <p className="text-text-secondary">AI‑generated signals and execution queue will be displayed here.</p>
    </div>
  )
}

function PortfolioPanel() {
  return (
    <div className="p-6 space-y-4">
      <h2 className="text-2xl font-semibold text-white mb-4">Portfolio</h2>
      <p className="text-text-secondary">Current positions, P&L, and risk metrics go here.</p>
    </div>
  )
}

function SettingsPanel() {
  return (
    <div className="p-6 space-y-4">
      <h2 className="text-2xl font-semibold text-white mb-4">Settings</h2>
      <p className="text-text-secondary">API keys, theme, and user preferences.</p>
    </div>
  )
}

// === Main Dashboard Page ===
export default function DashboardPage() {
  const [selected, setSelected] = useState('overview')

  let Panel
  switch (selected) {
    case 'market':
      Panel = LiveMarketPanel
      break
    case 'strategy':
      Panel = StrategyEnginePanel
      break
    case 'portfolio':
      Panel = PortfolioPanel
      break
    case 'settings':
      Panel = SettingsPanel
      break
    default:
      Panel = OverviewPanel
  }

  return (
    <div className="grid grid-rows-[64px_1fr] md:grid-cols-[240px_1fr] h-screen bg-background/5">
      <DashboardHeader />
      <DashboardSidebar selected={selected} setSelected={setSelected} />
      <main className="overflow-auto">
        <Panel />
      </main>
    </div>
  )
}
