'use client'

import { useAuth } from '@/components/providers'
import { TopNav } from '@/components/layout/top-nav'
import { Brain, Cpu, Radio, Lock, Unlock, Activity, Zap, Shield, BarChart3, Globe, RefreshCw } from 'lucide-react'

const BRAIN_SYSTEMS = [
  { name: 'Reasoning Engine', status: 'OPERATIONAL', load: 34, icon: Brain, color: 'text-sky-400' },
  { name: 'Market Cognition', status: 'OPERATIONAL', load: 67, icon: BarChart3, color: 'text-green-400' },
  { name: 'Autonomous Executor', status: 'OPERATIONAL', load: 12, icon: Zap, color: 'text-amber-400' },
  { name: 'Signal Processor', status: 'OPERATIONAL', load: 89, icon: Radio, color: 'text-purple-400' },
  { name: 'Security Layer', status: 'OPERATIONAL', load: 5, icon: Shield, color: 'text-emerald-400' },
  { name: 'Global Connectivity', status: 'OPERATIONAL', load: 45, icon: Globe, color: 'text-blue-400' },
  { name: 'Core Inference', status: 'OPERATIONAL', load: 56, icon: Cpu, color: 'text-cyan-400' },
  { name: 'Memory & Context', status: 'OPERATIONAL', load: 23, icon: Activity, color: 'text-rose-400' },
]

export default function BrainStatusPage() {
  const { isOwner } = useAuth()

  return (
    <div className="min-h-screen bg-[#020408] text-white">
      <TopNav />
      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Owner Banner */}
        {isOwner && (
          <div className="mb-6 rounded-xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 to-amber-500/5 p-4 flex items-center gap-3">
            <Unlock className="w-6 h-6 text-amber-400" />
            <div>
              <p className="font-bold text-amber-400">OWNER — FULL BRAIN ACCESS</p>
              <p className="text-sm text-amber-300/70">All systems unlocked. Override controls. Direct execution paths.</p>
            </div>
          </div>
        )}

        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold mb-2"><span className="text-sky-400">Brain</span> Status</h1>
          <p className="text-slate-400">AI infrastructure health — all systems operational 24/7/365</p>
        </div>

        {/* Overall Status */}
        <div className="mb-6 rounded-xl border border-green-500/20 bg-green-500/5 p-6 text-center">
          <div className="inline-flex items-center gap-2 mb-2">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-green-400" />
            </span>
            <p className="text-xl font-bold text-green-400">ALL SYSTEMS OPERATIONAL</p>
          </div>
          <p className="text-sm text-slate-400">15 AI agents active across 80+ exchanges, 72 languages</p>
        </div>

        {/* Systems Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {BRAIN_SYSTEMS.map((sys, i) => {
            const Icon = sys.icon
            return (
              <div key={i} className="rounded-xl border border-slate-800 bg-[#060a12] p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Icon className={`w-5 h-5 ${sys.color}`} />
                    <p className="font-semibold text-white">{sys.name}</p>
                  </div>
                  <span className="text-xs font-bold text-green-400 bg-green-500/10 px-2 py-0.5 rounded">{sys.status}</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-2 rounded-full bg-slate-800 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        sys.load > 80 ? 'bg-red-500' : sys.load > 50 ? 'bg-amber-500' : 'bg-sky-500'
                      }`}
                      style={{ width: `${sys.load}%` }}
                    />
                  </div>
                  <span className="text-xs text-slate-400 w-10 text-right">{sys.load}%</span>
                </div>
              </div>
            )
          })}
        </div>
      </main>
    </div>
  )
}
