'use client'

import { useState } from 'react'
import { useAuth } from '@/components/providers'
import { TopNav } from '@/components/layout/top-nav'
import { 
  Building2, CreditCard, ArrowRight, Shield, AlertTriangle, 
  DollarSign, Wallet, TrendingUp, Plus, Check, ChevronRight,
  Landmark, PiggyBank, ArrowUpRight, ArrowDownRight, Lock,
  CircleDot, Zap, Info
} from 'lucide-react'

const bankAccounts = [
  // Will be populated from Supabase / Plaid
]

const fundingHistory = [
  { id: '1', type: 'deposit', amount: 50000, date: '2026-06-01', status: 'completed', bank: 'Chase Checking ****4821' },
  { id: '2', type: 'allocation', amount: 25000, date: '2026-06-02', status: 'active', agent: 'Alpha Scaler v2' },
  { id: '3', type: 'allocation', amount: 15000, date: '2026-06-02', status: 'active', agent: 'Momentum Hunter' },
  { id: '4', type: 'withdrawal', amount: 3200, date: '2026-06-05', status: 'completed', bank: 'Chase Checking ****4821' },
]

export default function FundingPage() {
  const { user } = useAuth()
  const [activeTab, setActiveTab] = useState<'overview' | 'deposit' | 'allocate' | 'withdraw'>('overview')
  const [depositAmount, setDepositAmount] = useState('')
  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [allocateAmount, setAllocateAmount] = useState('')
  const [selectedAgent, setSelectedAgent] = useState('')
  const [linkedBanks] = useState<{id: string; name: string; last4: string; type: string}[]>([])

  const totalBalance = 100000
  const allocatedFunds = 40000
  const availableFunds = totalBalance - allocatedFunds

  return (
    <div className="min-h-screen bg-background noise-overlay grid-lines">
      <TopNav />
      <main className="container-custom py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-10 animate-slide-up">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 rounded-[14px] bg-primary/[0.06] flex items-center justify-center border border-primary/10">
                <Wallet className="h-5 w-5 text-primary" />
              </div>
              <h1 className="text-3xl font-display font-bold text-white tracking-tighter">Funding</h1>
            </div>
            <p className="text-text-secondary text-sm font-light ml-[52px]">Manage capital flow from your bank to your AI agents.</p>
          </div>
        </div>

        {/* Tesla Tab Navigation */}
        <div className="flex items-center gap-1 p-1 rounded-full glass border border-white/[0.04] mb-8 w-fit animate-slide-up" style={{ animationDelay: '50ms' }}>
          {[
            { key: 'overview', label: 'Overview', icon: DollarSign },
            { key: 'deposit', label: 'Deposit', icon: ArrowDownRight },
            { key: 'allocate', label: 'Allocate to Agents', icon: TrendingUp },
            { key: 'withdraw', label: 'Withdraw', icon: ArrowUpRight },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-medium transition-all duration-400 ${
                activeTab === tab.key
                  ? 'bg-white/[0.06] text-white border border-white/[0.08]'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              <tab.icon className="h-3.5 w-3.5" />
              {tab.label}
            </button>
          ))}
        </div>

        {/* ═══ OVERVIEW TAB ═══ */}
        {activeTab === 'overview' && (
          <div className="space-y-6 animate-fade-in">
            {/* Balance Cards — Tesla Monumental */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <div className="card-tesla p-7 animate-slide-up">
                <p className="text-[11px] text-text-dim tracking-tesla uppercase mb-3">Total Capital</p>
                <p className="text-4xl font-display font-bold text-white tracking-tight">
                  ${totalBalance.toLocaleString()}
                </p>
                <div className="flex items-center gap-2 mt-3">
                  <span className="badge badge-success">Active</span>
                  <span className="text-[11px] text-text-dim">Across all agents</span>
                </div>
              </div>

              <div className="card-tesla card-tesla-premium p-7 animate-slide-up" style={{ animationDelay: '80ms' }}>
                <p className="text-[11px] text-text-dim tracking-tesla uppercase mb-3">Allocated to Agents</p>
                <p className="text-4xl font-display font-bold text-white tracking-tight">
                  ${allocatedFunds.toLocaleString()}
                </p>
                <div className="mt-4">
                  <div className="h-1.5 rounded-full bg-white/[0.04]">
                    <div className="h-full rounded-full bg-gradient-to-r from-accent-deep to-accent" style={{ width: `${(allocatedFunds / totalBalance) * 100}%` }} />
                  </div>
                  <p className="text-[11px] text-text-dim mt-1.5">{Math.round((allocatedFunds / totalBalance) * 100)}% of total capital</p>
                </div>
              </div>

              <div className="card-tesla p-7 animate-slide-up" style={{ animationDelay: '160ms' }}>
                <p className="text-[11px] text-text-dim tracking-tesla uppercase mb-3">Available to Allocate</p>
                <p className="text-4xl font-display font-bold gradient-text tracking-tight">
                  ${availableFunds.toLocaleString()}
                </p>
                <button
                  onClick={() => setActiveTab('allocate')}
                  className="mt-4 flex items-center gap-1.5 text-[11px] text-primary hover:text-primary-hover transition-colors duration-400"
                >
                  Allocate now
                  <ChevronRight className="h-3 w-3" />
                </button>
              </div>
            </div>

            {/* Linked Bank Accounts */}
            <div className="card-tesla p-7 animate-slide-up" style={{ animationDelay: '200ms' }}>
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-display font-semibold text-white tracking-tight">Linked Bank Accounts</h3>
                <button
                  onClick={() => setActiveTab('deposit')}
                  className="flex items-center gap-2 px-4 py-2 rounded-full bg-white/[0.03] border border-white/[0.06] text-text-secondary text-sm hover:text-white hover:border-white/[0.12] transition-all duration-400"
                >
                  <Plus className="h-3.5 w-3.5" />
                  Link Bank
                </button>
              </div>

              {linkedBanks.length > 0 ? (
                <div className="space-y-3">
                  {linkedBanks.map((bank) => (
                    <div key={bank.id} className="flex items-center justify-between p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
                      <div className="flex items-center gap-4">
                        <div className="w-11 h-11 rounded-[14px] bg-primary/[0.06] flex items-center justify-center border border-primary/10">
                          <Landmark className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                          <p className="text-sm font-medium text-white">{bank.name}</p>
                          <p className="text-[11px] text-text-dim">****{bank.last4} · {bank.type}</p>
                        </div>
                      </div>
                      <span className="badge badge-success">Verified</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-16">
                  <div className="w-16 h-16 rounded-[20px] bg-surface mx-auto mb-5 flex items-center justify-center border border-white/[0.04]">
                    <Building2 className="h-7 w-7 text-text-dim" />
                  </div>
                  <p className="text-text-secondary text-sm mb-2">No bank accounts linked</p>
                  <p className="text-[11px] text-text-dim mb-6 max-w-sm mx-auto">
                    Link your bank via Plaid to deposit capital for your AI agents to trade.
                  </p>
                  <button
                    onClick={() => setActiveTab('deposit')}
                    className="inline-flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-primary-deep to-primary text-white rounded-full font-medium text-sm shadow-primary hover:shadow-primary-lg transition-all duration-500"
                  >
                    <Plus className="h-4 w-4" />
                    Link Your Bank Account
                  </button>
                </div>
              )}
            </div>

            {/* Funding History */}
            <div className="card-tesla p-7 animate-slide-up" style={{ animationDelay: '250ms' }}>
              <h3 className="text-lg font-display font-semibold text-white tracking-tight mb-6">Funding History</h3>
              <div className="space-y-2">
                {fundingHistory.map((item) => (
                  <div key={item.id} className="flex items-center justify-between p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-[14px] flex items-center justify-center border ${
                        item.type === 'deposit' ? 'bg-emerald-500/[0.06] border-emerald-500/10' :
                        item.type === 'allocation' ? 'bg-primary/[0.06] border-primary/10' :
                        'bg-accent/[0.06] border-accent/10'
                      }`}>
                        {item.type === 'deposit' && <ArrowDownRight className="h-4.5 w-4.5 text-emerald-400" />}
                        {item.type === 'allocation' && <TrendingUp className="h-4.5 w-4.5 text-primary" />}
                        {item.type === 'withdrawal' && <ArrowUpRight className="h-4.5 w-4.5 text-accent" />}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-white capitalize">{item.type}</p>
                        <p className="text-[11px] text-text-dim">{item.bank || item.agent} · {item.date}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className={`text-sm font-display font-semibold ${
                        item.type === 'withdrawal' ? 'text-accent' : 'text-white'
                      }`}>
                        {item.type === 'withdrawal' ? '-' : item.type === 'deposit' ? '+' : ''}${item.amount.toLocaleString()}
                      </p>
                      <span className={`badge ${item.status === 'completed' ? 'badge-success' : item.status === 'active' ? 'badge-primary' : 'badge-warning'} text-[9px]`}>
                        {item.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ═══ DEPOSIT TAB ═══ */}
        {activeTab === 'deposit' && (
          <div className="max-w-2xl animate-fade-in">
            <div className="card-tesla p-8">
              <div className="flex items-center gap-4 mb-8">
                <div className="w-12 h-12 rounded-[16px] bg-primary/[0.06] flex items-center justify-center border border-primary/10">
                  <Landmark className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h2 className="text-xl font-display font-semibold text-white tracking-tight">Deposit Capital</h2>
                  <p className="text-sm text-text-secondary font-light">Transfer funds from your bank to your trading account.</p>
                </div>
              </div>

              {/* Plaid Link Integration */}
              <div className="p-6 rounded-2xl bg-white/[0.02] border border-white/[0.04] mb-8">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 rounded-[14px] bg-primary/[0.06] flex items-center justify-center border border-primary/10 flex-shrink-0">
                    <Shield className="h-4.5 w-4.5 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-white mb-1">Secure Bank Link via Plaid</p>
                    <p className="text-[11px] text-text-dim leading-relaxed">
                      Your bank credentials are never stored. Plaid uses end-to-end encryption and SOC 2 Type II compliance. 
                      We only receive a secure token for ACH transfers.
                    </p>
                  </div>
                </div>
              </div>

              {/* Link Bank Button — triggers Plaid Link */}
              <button
                className="w-full flex items-center justify-center gap-2.5 px-6 py-4 bg-gradient-to-r from-primary-deep to-primary text-white rounded-full font-medium text-sm shadow-primary hover:from-primary hover:to-primary-hover hover:shadow-primary-lg transition-all duration-500 mb-8"
              >
                <Landmark className="h-4 w-4" />
                Link Bank Account with Plaid
                <ArrowRight className="h-4 w-4" />
              </button>

              <div className="tesla-divider mb-8" />

              {/* Deposit Amount */}
              <div className="mb-6">
                <label className="block text-[11px] text-text-dim tracking-tesla uppercase font-medium mb-3">Deposit Amount (USD)</label>
                <div className="relative">
                  <span className="absolute left-5 top-1/2 -translate-y-1/2 text-text-muted text-lg font-display font-bold">$</span>
                  <input
                    type="number"
                    value={depositAmount}
                    onChange={(e) => setDepositAmount(e.target.value)}
                    placeholder="0"
                    className="input pl-10 text-2xl font-display font-bold py-5 tracking-tight"
                    min={1000}
                    step={1000}
                  />
                </div>
                <p className="text-[11px] text-text-dim mt-2">Minimum deposit: $1,000 · ACH transfer takes 1-3 business days</p>
              </div>

              {/* Quick amounts */}
              <div className="grid grid-cols-4 gap-3 mb-8">
                {['$10K', '$25K', '$50K', '$100K'].map((amt) => {
                  const val = parseInt(amt.replace(/\D/g, '')) * 1000
                  return (
                    <button
                      key={amt}
                      onClick={() => setDepositAmount(String(val))}
                      className={`py-3 rounded-full text-sm font-medium border transition-all duration-400 ${
                        depositAmount === String(val)
                          ? 'bg-primary/[0.08] border-primary/20 text-primary'
                          : 'bg-white/[0.02] border-white/[0.04] text-text-muted hover:text-white hover:border-white/[0.08]'
                      }`}
                    >
                      {amt}
                    </button>
                  )
                })}
              </div>

              <button
                disabled={!depositAmount || Number(depositAmount) < 1000}
                className="w-full flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r from-accent-deep to-accent text-[#1a0a00] rounded-full font-semibold text-sm shadow-accent hover:shadow-[0_4px_30px_rgba(245,158,11,0.2)] transition-all duration-500 disabled:opacity-20 disabled:pointer-events-none"
              >
                <DollarSign className="h-4 w-4" />
                Initiate Deposit
              </button>

              <div className="flex items-center gap-2 mt-5 justify-center">
                <Lock className="h-3 w-3 text-text-dim" />
                <p className="text-[10px] text-text-dim tracking-wide">Bank-level encryption · FDIC insured · SOC 2 compliant</p>
              </div>
            </div>
          </div>
        )}

        {/* ═══ ALLOCATE TAB ═══ */}
        {activeTab === 'allocate' && (
          <div className="max-w-2xl animate-fade-in">
            <div className="card-tesla p-8">
              <div className="flex items-center gap-4 mb-8">
                <div className="w-12 h-12 rounded-[16px] bg-accent/[0.06] flex items-center justify-center border border-accent/10">
                  <TrendingUp className="h-5 w-5 text-accent" />
                </div>
                <div>
                  <h2 className="text-xl font-display font-semibold text-white tracking-tight">Allocate to Agent</h2>
                  <p className="text-sm text-text-secondary font-light">Assign trading capital to a specific AI agent.</p>
                </div>
              </div>

              {/* Available Balance */}
              <div className="p-5 rounded-2xl bg-white/[0.02] border border-white/[0.04] mb-8">
                <p className="text-[11px] text-text-dim tracking-tesla uppercase mb-1">Available to Allocate</p>
                <p className="text-2xl font-display font-bold gradient-text">${availableFunds.toLocaleString()}</p>
              </div>

              {/* Agent Selection */}
              <div className="mb-6">
                <label className="block text-[11px] text-text-dim tracking-tesla uppercase font-medium mb-3">Select Agent</label>
                <select
                  value={selectedAgent}
                  onChange={(e) => setSelectedAgent(e.target.value)}
                  className="input appearance-none cursor-pointer"
                >
                  <option value="">Choose an agent...</option>
                  <option value="alpha-scaler">Alpha Scaler v2 — Momentum Strategy</option>
                  <option value="momentum-hunter">Momentum Hunter — Swing Trading</option>
                  <option value="sentinel">Sentinel — Risk Management</option>
                </select>
              </div>

              {/* Allocation Amount */}
              <div className="mb-6">
                <label className="block text-[11px] text-text-dim tracking-tesla uppercase font-medium mb-3">Allocation Amount (USD)</label>
                <div className="relative">
                  <span className="absolute left-5 top-1/2 -translate-y-1/2 text-text-muted text-lg font-display font-bold">$</span>
                  <input
                    type="number"
                    value={allocateAmount}
                    onChange={(e) => setAllocateAmount(e.target.value)}
                    placeholder="0"
                    className="input pl-10 text-2xl font-display font-bold py-5 tracking-tight"
                    min={1000}
                    step={1000}
                  />
                </div>
                <p className="text-[11px] text-text-dim mt-2">Minimum allocation: $1,000 per agent</p>
              </div>

              {/* Risk Acknowledgment */}
              <div className="p-5 rounded-2xl bg-accent/[0.03] border border-accent/10 mb-8">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="h-4 w-4 text-accent flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-accent mb-1">Risk Acknowledgment</p>
                    <p className="text-[11px] text-text-dim leading-relaxed">
                      Allocated capital will be actively traded by the selected AI agent. Trading involves substantial risk of loss. 
                      Past performance does not guarantee future results. Only allocate capital you can afford to lose.
                    </p>
                  </div>
                </div>
              </div>

              <button
                disabled={!selectedAgent || !allocateAmount || Number(allocateAmount) < 1000}
                className="w-full flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r from-accent-deep to-accent text-[#1a0a00] rounded-full font-semibold text-sm shadow-accent hover:shadow-[0_4px_30px_rgba(245,158,11,0.2)] transition-all duration-500 disabled:opacity-20 disabled:pointer-events-none"
              >
                <Zap className="h-4 w-4" />
                Allocate & Activate Agent
              </button>
            </div>
          </div>
        )}

        {/* ═══ WITHDRAW TAB ═══ */}
        {activeTab === 'withdraw' && (
          <div className="max-w-2xl animate-fade-in">
            <div className="card-tesla p-8">
              <div className="flex items-center gap-4 mb-8">
                <div className="w-12 h-12 rounded-[16px] bg-white/[0.04] flex items-center justify-center border border-white/[0.06]">
                  <PiggyBank className="h-5 w-5 text-text-muted" />
                </div>
                <div>
                  <h2 className="text-xl font-display font-semibold text-white tracking-tight">Withdraw Funds</h2>
                  <p className="text-sm text-text-secondary font-light">Transfer capital back to your bank account.</p>
                </div>
              </div>

              {/* Available Balance */}
              <div className="p-5 rounded-2xl bg-white/[0.02] border border-white/[0.04] mb-8">
                <p className="text-[11px] text-text-dim tracking-tesla uppercase mb-1">Withdrawable Balance</p>
                <p className="text-2xl font-display font-bold text-white">${availableFunds.toLocaleString()}</p>
                <p className="text-[11px] text-text-dim mt-1">Unallocated funds only. Agent-allocated funds must be de-allocated first.</p>
              </div>

              {/* Withdraw Amount */}
              <div className="mb-6">
                <label className="block text-[11px] text-text-dim tracking-tesla uppercase font-medium mb-3">Withdraw Amount (USD)</label>
                <div className="relative">
                  <span className="absolute left-5 top-1/2 -translate-y-1/2 text-text-muted text-lg font-display font-bold">$</span>
                  <input
                    type="number"
                    value={withdrawAmount}
                    onChange={(e) => setWithdrawAmount(e.target.value)}
                    placeholder="0"
                    className="input pl-10 text-2xl font-display font-bold py-5 tracking-tight"
                    min={100}
                    step={100}
                  />
                </div>
                <p className="text-[11px] text-text-dim mt-2">ACH withdrawal takes 1-3 business days</p>
              </div>

              <button
                disabled={!withdrawAmount || Number(withdrawAmount) < 100}
                className="w-full flex items-center justify-center gap-2 px-6 py-4 glass border border-white/[0.06] text-white rounded-full font-medium text-sm hover:border-white/[0.12] hover:bg-white/[0.03] transition-all duration-500 disabled:opacity-20 disabled:pointer-events-none"
              >
                <ArrowUpRight className="h-4 w-4" />
                Initiate Withdrawal
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
