'use client'

import { useState } from 'react'
import { useAuth, useTheme } from '@/components/providers'
import { createClient } from '@/lib/supabase/client'
import { TopNav } from '@/components/layout/top-nav'
import { TRADING_AGENTS } from '@/lib/agents/registry'
import { PROVIDERS } from '@/lib/providers/registry'
import { MARKETS, LANGUAGES } from '@/lib/global/markets-languages'
import {
  User, Shield, Bell, Palette, Key, Trash2, AlertTriangle,
  CreditCard, DollarSign, Building2, Wallet, Activity,
  Cpu, Globe, Languages, Bot, Sparkles, Check, X,
  Settings, Zap, Lock, Eye, EyeOff, RefreshCw, Gift
} from 'lucide-react'

const paymentMethods = [
  { id: 'stripe', name: 'Stripe', icon: '💳', desc: 'Credit/debit card' },
  { id: 'paypal', name: 'PayPal', icon: '🅿️', desc: 'PayPal balance or card' },
  { id: 'square', name: 'Square', icon: '◾', desc: 'Square card processing' },
  { id: 'cashapp', name: 'Cash App', icon: '💲', desc: 'Cash App Pay via Square' },
]

export default function SettingsPage() {
  const { user, signOut } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [passwordSuccess, setPasswordSuccess] = useState('')
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [activeTab, setActiveTab] = useState('profile')
  const [selectedLang, setSelectedLang] = useState('en')
  const [showPassword, setShowPassword] = useState(false)

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setPasswordError('')
    setPasswordSuccess('')
    if (newPassword !== confirmPassword) { setPasswordError('Passwords do not match'); return }
    if (newPassword.length < 8) { setPasswordError('Password must be at least 8 characters'); return }
    const supabase = createClient()
    const { error } = await supabase.auth.updateUser({ password: newPassword })
    if (error) { setPasswordError(error.message) }
    else { setPasswordSuccess('Password updated successfully'); setCurrentPassword(''); setNewPassword(''); setConfirmPassword('') }
  }

  if (!user) {
    if (typeof window !== 'undefined') window.location.href = '/login'
    return null
  }

  const tabs = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'funding', label: 'Funding & Payments', icon: DollarSign },
    { id: 'agents', label: 'My Agents', icon: Bot },
    { id: 'providers', label: 'Provider Keys', icon: Cpu },
    { id: 'markets', label: 'Markets & Language', icon: Globe },
    { id: 'security', label: 'Security', icon: Shield },
  ]

  return (
    <div className="min-h-screen bg-background noise-overlay grid-lines">
      <TopNav />
      <main className="container-custom py-8">
        <h1 className="text-3xl font-display font-bold text-white tracking-tighter mb-8 animate-slide-up">Settings</h1>

        <div className="flex flex-col lg:flex-row gap-6">
          {/* Sidebar Tabs */}
          <div className="lg:w-56 flex-shrink-0 animate-slide-up" style={{ animationDelay: '50ms' }}>
            <nav className="space-y-1">
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 ${
                    activeTab === tab.id
                      ? 'text-white bg-white/[0.06] border border-white/[0.08]'
                      : 'text-text-secondary hover:text-white hover:bg-white/[0.03]'
                  }`}
                >
                  <tab.icon className="h-4 w-4" />
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>

          {/* Content */}
          <div className="flex-1 max-w-2xl">
            {/* ═══ PROFILE ═══ */}
            {activeTab === 'profile' && (
              <div className="animate-slide-up">
                <section className="card-tesla p-6 mb-4">
                  <div className="flex items-center gap-3 mb-5">
                    <User className="h-5 w-5 text-primary" />
                    <h2 className="text-lg font-display font-semibold text-white">Profile</h2>
                  </div>
                  <div className="space-y-4">
                    <div>
                      <label className="block text-[10px] text-text-dim mb-1 uppercase tracking-tesla">Email</label>
                      <p className="text-sm text-white">{user.email}</p>
                    </div>
                    <div>
                      <label className="block text-[10px] text-text-dim mb-1 uppercase tracking-tesla">Account ID</label>
                      <p className="text-[11px] text-text-dim font-mono">{user.id}</p>
                    </div>
                    <div>
                      <label className="block text-[10px] text-text-dim mb-1 uppercase tracking-tesla">Plan</label>
                      <span className="badge badge-primary">Pro — 7-Day Trial Active</span>
                    </div>
                  </div>
                </section>

                <section className="card-tesla p-6 mb-4">
                  <div className="flex items-center gap-3 mb-5">
                    <Palette className="h-5 w-5 text-primary" />
                    <h2 className="text-lg font-display font-semibold text-white">Appearance</h2>
                  </div>
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-white">Theme</p>
                      <p className="text-[11px] text-text-dim mt-0.5">{theme === 'dark' ? 'Dark mode' : 'Light mode'}</p>
                    </div>
                    <button onClick={toggleTheme} className="relative w-12 h-6 rounded-full bg-white/[0.06] border border-white/[0.08] transition-colors duration-300">
                      <div className={`absolute top-0.5 w-5 h-5 rounded-full bg-primary transition-all duration-300 ${theme === 'dark' ? 'left-0.5' : 'left-6'}`} />
                    </button>
                  </div>
                </section>

                <section className="card-tesla p-6">
                  <button onClick={signOut} className="w-full flex items-center justify-center gap-2 py-3 text-sm text-text-secondary hover:text-white border border-white/[0.06] rounded-xl hover:border-white/[0.1] transition-all duration-300">
                    Sign out
                  </button>
                </section>
              </div>
            )}

            {/* ═══ FUNDING & PAYMENTS ═══ */}
            {activeTab === 'funding' && (
              <div className="animate-slide-up">
                <section className="card-tesla p-6 mb-4">
                  <div className="flex items-center gap-3 mb-5">
                    <DollarSign className="h-5 w-5 text-primary" />
                    <h2 className="text-lg font-display font-semibold text-white">Funding & Payments</h2>
                  </div>

                  {/* Linked Bank */}
                  <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04] mb-4">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <Building2 className="h-4 w-4 text-text-dim" />
                        <div>
                          <p className="text-sm font-medium text-white">Linked Bank Account</p>
                          <p className="text-[10px] text-text-dim">Plaid-powered ACH deposits & withdrawals</p>
                        </div>
                      </div>
                      <button className="px-4 py-1.5 rounded-full bg-primary/[0.06] border border-primary/10 text-primary text-[11px] font-medium hover:bg-primary/[0.1] transition-all">
                        Link Bank
                      </button>
                    </div>
                    <p className="text-[10px] text-text-dim">No bank account linked yet. Link via Plaid for real-money trading deposits.</p>
                  </div>

                  {/* Payment Methods */}
                  <p className="text-[10px] text-text-dim uppercase tracking-tesla mb-3">Subscription Payment Methods</p>
                  <div className="grid grid-cols-2 gap-3 mb-4">
                    {paymentMethods.map(pm => (
                      <div key={pm.id} className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04] hover:border-primary/10 transition-all cursor-pointer">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-lg">{pm.icon}</span>
                          <p className="text-sm font-medium text-white">{pm.name}</p>
                        </div>
                        <p className="text-[10px] text-text-dim">{pm.desc}</p>
                      </div>
                    ))}
                  </div>

                  {/* Trial Status */}
                  <div className="p-4 rounded-2xl bg-accent/[0.03] border border-accent/10">
                    <div className="flex items-center gap-3">
                      <Gift className="h-4 w-4 text-accent" />
                      <div>
                        <p className="text-sm font-medium text-white">7-Day Free Trial</p>
                        <p className="text-[10px] text-text-dim">All subscriptions include a 7-day free trial. Cancel anytime before trial ends — no charge.</p>
                      </div>
                    </div>
                  </div>
                </section>
              </div>
            )}

            {/* ═══ MY AGENTS ═══ */}
            {activeTab === 'agents' && (
              <div className="animate-slide-up">
                <section className="card-tesla p-6 mb-4">
                  <div className="flex items-center gap-3 mb-5">
                    <Bot className="h-5 w-5 text-primary" />
                    <h2 className="text-lg font-display font-semibold text-white">My Trading Agents</h2>
                  </div>
                  <p className="text-[11px] text-text-dim mb-4">Manage your active agents. All models auto-update to the latest version daily.</p>
                  <div className="space-y-2">
                    {TRADING_AGENTS.map(agent => (
                      <div key={agent.id} className="flex items-center justify-between p-3 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                        <div className="flex items-center gap-3">
                          <span className="text-lg">{agent.icon}</span>
                          <div>
                            <p className="text-sm font-medium text-white">{agent.name}</p>
                            <p className="text-[10px] text-text-dim">{agent.specialty}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="badge bg-primary/[0.06] border-primary/10 text-[9px] text-primary flex items-center gap-1">
                            <Sparkles className="h-2.5 w-2.5" /> Auto-Update
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {/* ═══ PROVIDER KEYS ═══ */}
            {activeTab === 'providers' && (
              <div className="animate-slide-up">
                <section className="card-tesla p-6 mb-4">
                  <div className="flex items-center gap-3 mb-5">
                    <Cpu className="h-5 w-5 text-primary" />
                    <h2 className="text-lg font-display font-semibold text-white">Provider API Keys</h2>
                  </div>
                  <p className="text-[11px] text-text-dim mb-4">Add your own API keys to use your quota and rate limits. Without a key, the platform uses shared defaults. Keys are encrypted at rest.</p>
                  <div className="space-y-3">
                    {PROVIDERS.filter(p => p.status === 'active').map(provider => (
                      <div key={provider.id} className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
                        <div className="flex items-center gap-3 mb-3">
                          <span className="text-lg">{provider.icon}</span>
                          <div className="flex-1">
                            <p className="text-sm font-medium text-white">{provider.name}</p>
                            <p className="text-[9px] text-text-dim font-mono">{provider.envKey}</p>
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <input
                            type="password"
                            placeholder={`Enter ${provider.envKey}...`}
                            className="input flex-1 text-[11px]"
                          />
                          <button className="px-4 py-2 rounded-full bg-primary/[0.06] border border-primary/10 text-primary text-[11px] font-medium hover:bg-primary/[0.1] transition-all">
                            Save
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}

            {/* ═══ MARKETS & LANGUAGE ═══ */}
            {activeTab === 'markets' && (
              <div className="animate-slide-up">
                <section className="card-tesla p-6 mb-4">
                  <div className="flex items-center gap-3 mb-5">
                    <Globe className="h-5 w-5 text-primary" />
                    <h2 className="text-lg font-display font-semibold text-white">Markets & Language</h2>
                  </div>

                  <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04] mb-4">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm font-medium text-white">Trading Markets</p>
                      <span className="badge badge-primary">{MARKETS.length} exchanges</span>
                    </div>
                    <p className="text-[11px] text-text-dim mb-2">{MARKETS.filter(m => m.is247).length} markets trade 24/7/365 (Crypto + Forex). All regions: North America, South America, Europe, Asia-Pacific, Middle East, Africa.</p>
                    <a href="/markets" className="text-[11px] text-primary font-medium hover:underline">View all markets →</a>
                  </div>

                  <div className="p-4 rounded-2xl bg-white/[0.02] border border-white/[0.04]">
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm font-medium text-white">Interface Language</p>
                      <span className="badge badge-primary">{LANGUAGES.length} available</span>
                    </div>
                    <select
                      value={selectedLang}
                      onChange={(e) => setSelectedLang(e.target.value)}
                      className="input w-full appearance-none cursor-pointer mt-2"
                    >
                      {LANGUAGES.filter(l => l.isSupported).map(l => (
                        <option key={l.code} value={l.code}>
                          {l.nativeName} — {l.name} ({l.code.toUpperCase()})
                        </option>
                      ))}
                    </select>
                    <p className="text-[10px] text-text-dim mt-2">Full interface translation including agent conversations, market data, and support. RTL languages supported.</p>
                  </div>
                </section>
              </div>
            )}

            {/* ═══ SECURITY ═══ */}
            {activeTab === 'security' && (
              <div className="animate-slide-up">
                <section className="card-tesla p-6 mb-4">
                  <div className="flex items-center gap-3 mb-5">
                    <Key className="h-5 w-5 text-primary" />
                    <h2 className="text-lg font-display font-semibold text-white">Change Password</h2>
                  </div>
                  <form onSubmit={handleChangePassword} className="space-y-4">
                    <div>
                      <label className="block text-[10px] text-text-dim mb-1.5 uppercase tracking-tesla">New Password</label>
                      <div className="relative">
                        <input
                          type={showPassword ? 'text' : 'password'}
                          value={newPassword}
                          onChange={(e) => setNewPassword(e.target.value)}
                          className="input pr-10"
                          placeholder="••••••••"
                          required
                        />
                        <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-text-dim hover:text-white transition-colors">
                          {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="block text-[10px] text-text-dim mb-1.5 uppercase tracking-tesla">Confirm Password</label>
                      <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} className="input" placeholder="••••••••" required />
                    </div>
                    {passwordError && <p className="text-sm text-error">{passwordError}</p>}
                    {passwordSuccess && <p className="text-sm text-emerald-400">{passwordSuccess}</p>}
                    <button type="submit" className="btn btn-secondary px-6 py-2.5 text-sm">Update Password</button>
                  </form>
                </section>

                <section className="card-tesla p-6 border-red-900/20">
                  <div className="flex items-center gap-3 mb-5">
                    <AlertTriangle className="h-5 w-5 text-red-400" />
                    <h2 className="text-lg font-display font-semibold text-white">Danger Zone</h2>
                  </div>
                  {!deleteConfirm ? (
                    <button onClick={() => setDeleteConfirm(true)} className="flex items-center gap-2 px-4 py-2.5 text-sm text-red-400 border border-red-900/30 rounded-xl hover:bg-red-500/5 transition-colors">
                      <Trash2 className="h-4 w-4" /> Delete Account
                    </button>
                  ) : (
                    <div className="space-y-3">
                      <p className="text-sm text-red-400">This action is permanent and cannot be undone.</p>
                      <div className="flex gap-3">
                        <button onClick={() => setDeleteConfirm(false)} className="btn btn-secondary px-4 py-2 text-sm">Cancel</button>
                        <button className="flex items-center gap-2 px-4 py-2 text-sm bg-red-500/10 text-red-400 border border-red-900/30 rounded-xl hover:bg-red-500/20 transition-colors">
                          <Trash2 className="h-4 w-4" /> Confirm Delete
                        </button>
                      </div>
                    </div>
                  )}
                </section>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
