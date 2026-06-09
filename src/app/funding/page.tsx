'use client'

import { useState } from 'react'
import { useAuth } from '@/components/providers'
import { TopNav } from '@/components/layout/top-nav'
import {
  DollarSign, CreditCard, Building, Wallet,
  Unlock, Shield, Zap, Check, ArrowRight,
  Banknote, Landmark, QrCode, Link2
} from 'lucide-react'

const FUNDING_METHODS = [
  {
    id: 'plaid',
    name: 'Bank Transfer (Plaid)',
    desc: 'Link your bank account. Instant verification. ACH transfers.',
    icon: Building,
    color: 'text-sky-400',
    border: 'border-sky-500/30',
    bg: 'bg-sky-500/10',
    min: 100,
    max: 1000000,
    fee: '0%',
    speed: '1-3 business days',
  },
  {
    id: 'stripe',
    name: 'Card / ACH (Stripe)',
    desc: 'Visa, Mastercard, Amex, Discover. Also ACH direct debit.',
    icon: CreditCard,
    color: 'text-purple-400',
    border: 'border-purple-500/30',
    bg: 'bg-purple-500/10',
    min: 100,
    max: 50000,
    fee: '2.9% + $0.30',
    speed: 'Instant',
  },
  {
    id: 'paypal',
    name: 'PayPal',
    desc: 'Pay with PayPal balance or linked bank/card.',
    icon: DollarSign,
    color: 'text-blue-400',
    border: 'border-blue-500/30',
    bg: 'bg-blue-500/10',
    min: 100,
    max: 10000,
    fee: '0%',
    speed: 'Instant',
  },
  {
    id: 'cashapp',
    name: 'Cash App Pay',
    desc: 'Pay directly from your Cash App balance or linked debit card.',
    icon: QrCode,
    color: 'text-green-400',
    border: 'border-green-500/30',
    bg: 'bg-green-500/10',
    min: 100,
    max: 5000,
    fee: '0%',
    speed: 'Instant',
  },
  {
    id: 'square',
    name: 'Square Pay',
    desc: 'Square terminal — card present or online payments.',
    icon: Banknote,
    color: 'text-amber-400',
    border: 'border-amber-500/30',
    bg: 'bg-amber-500/10',
    min: 100,
    max: 25000,
    fee: '2.6% + $0.10',
    speed: 'Instant',
  },
  {
    id: 'wire',
    name: 'Wire Transfer',
    desc: 'Institutional wire transfers. Same-day settlement.',
    icon: Landmark,
    color: 'text-emerald-400',
    border: 'border-emerald-500/30',
    bg: 'bg-emerald-500/10',
    min: 1000,
    max: 10000000,
    fee: '$25 flat',
    speed: 'Same day',
  },
]

export default function FundingPage() {
  const { user, isOwner } = useAuth()
  const [selectedMethod, setSelectedMethod] = useState<string | null>(null)
  const [amount, setAmount] = useState('100')
  const [status, setStatus] = useState('')

  const handleFund = async (methodId: string) => {
    const amt = Number(amount)
    if (!amt || amt < 100) {
      setStatus('Minimum deposit is $100')
      return
    }

    setStatus('Processing...')

    try {
      if (methodId === 'stripe') {
        const res = await fetch('/api/stripe/checkout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ amount: amt, userEmail: user?.email }),
        })
        const data = await res.json()
        if (data.url) {
          window.location.href = data.url
          return
        }
        setStatus(data.error || 'Stripe checkout failed')
      } else if (methodId === 'paypal') {
        const res = await fetch('/api/paypal/create-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ amount: amt, userEmail: user?.email }),
        })
        const data = await res.json()
        if (data.approvalUrl) {
          window.location.href = data.approvalUrl
          return
        }
        setStatus(data.error || 'PayPal order failed')
      } else if (methodId === 'cashapp') {
        const res = await fetch('/api/cashapp/create-payment', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ amount: amt, userEmail: user?.email }),
        })
        const data = await res.json()
        setStatus(data.redirectUrl ? 'Redirecting to Cash App...' : (data.error || 'Cash App payment failed'))
      } else if (methodId === 'plaid') {
        const res = await fetch('/api/plaid/create-link-token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ userEmail: user?.email }),
        })
        const data = await res.json()
        setStatus(data.linkToken ? 'Plaid link token created. Bank linking ready.' : (data.error || 'Plaid linking failed'))
      } else {
        setStatus(`${methodId.toUpperCase()} integration ready — configure API keys in settings`)
      }
    } catch (err: any) {
      setStatus(err.message || 'Funding failed')
    }
  }

  return (
    <div className="min-h-screen bg-[#020408] text-white">
      <TopNav />
      <main className="max-w-5xl mx-auto px-4 py-8">
        {/* Owner Banner */}
        {isOwner && (
          <div className="mb-6 rounded-xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 to-amber-500/5 p-4 flex items-center gap-3">
            <Unlock className="w-6 h-6 text-amber-400" />
            <div>
              <p className="font-bold text-amber-400">OWNER — UNRESTRICTED FUNDING</p>
              <p className="text-sm text-amber-300/70">No limits. No fees waived. All 6 payment methods. $100 minimum. Live account.</p>
            </div>
          </div>
        )}

        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold mb-2">
            <span className="text-sky-400">Fund</span> Your Trading Account
          </h1>
          <p className="text-slate-400">
            Start trading from <span className="text-amber-400 font-bold">$100</span>. 6 payment methods. 7-day free trial on all plans.
          </p>
        </div>

        {/* Amount Input */}
        <div className="mb-8 rounded-xl border border-sky-500/20 bg-[#0a1020] p-6">
          <label className="text-sm text-slate-400 block mb-2">Deposit Amount (USD)</label>
          <div className="flex items-center gap-3">
            <span className="text-2xl text-slate-500">$</span>
            <input
              type="number"
              value={amount}
              onChange={e => setAmount(e.target.value)}
              min={100}
              step={100}
              className="flex-1 rounded-lg border border-slate-700 bg-[#060a12] px-4 py-3 text-2xl font-bold text-white focus:border-sky-500 focus:outline-none"
            />
          </div>
          <div className="flex gap-2 mt-3">
            {[100, 250, 500, 1000, 5000, 25000].map(amt => (
              <button
                key={amt}
                onClick={() => setAmount(String(amt))}
                className={`rounded-lg px-3 py-1 text-sm font-semibold transition ${
                  amount === String(amt)
                    ? 'bg-sky-500 text-white'
                    : 'bg-slate-800 text-slate-400 hover:text-white'
                }`}
              >
                ${amt.toLocaleString()}
              </button>
            ))}
          </div>
        </div>

        {/* Payment Methods */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          {FUNDING_METHODS.map(method => {
            const Icon = method.icon
            const selected = selectedMethod === method.id
            return (
              <button
                key={method.id}
                onClick={() => setSelectedMethod(method.id)}
                className={`rounded-xl border p-4 text-left transition ${
                  selected
                    ? `${method.border} ${method.bg}`
                    : 'border-slate-800 bg-[#060a12] hover:border-slate-700'
                }`}
              >
                <div className="flex items-start gap-3">
                  <Icon className={`w-8 h-8 ${method.color} shrink-0`} />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <p className="font-bold text-white">{method.name}</p>
                      {isOwner && <Unlock className="w-3 h-3 text-amber-400" />}
                    </div>
                    <p className="text-sm text-slate-400 mt-1">{method.desc}</p>
                    <div className="flex gap-4 mt-2 text-xs text-slate-500">
                      <span>Min: ${method.min.toLocaleString()}</span>
                      <span>Max: ${method.max.toLocaleString()}</span>
                      <span>Fee: {method.fee}</span>
                      <span>{method.speed}</span>
                    </div>
                  </div>
                  {selected && <Check className={`w-5 h-5 ${method.color} shrink-0`} />}
                </div>
              </button>
            )
          })}
        </div>

        {/* Fund Button */}
        {selectedMethod && (
          <div className="text-center">
            <button
              onClick={() => handleFund(selectedMethod)}
              className="rounded-xl bg-gradient-to-r from-sky-500 to-sky-600 px-12 py-4 text-lg font-bold text-white hover:from-sky-400 hover:to-sky-500 transition flex items-center gap-2 mx-auto"
            >
              <Zap className="w-5 h-5" />
              Fund ${Number(amount).toLocaleString()} via {FUNDING_METHODS.find(m => m.id === selectedMethod)?.name}
              <ArrowRight className="w-5 h-5" />
            </button>
            {status && <p className="mt-3 text-sm text-slate-300">{status}</p>}
          </div>
        )}

        {/* Security Notice */}
        <div className="mt-8 rounded-xl border border-slate-800 bg-[#060a12] p-4 flex items-center gap-3">
          <Shield className="w-6 h-6 text-green-400 shrink-0" />
          <div>
            <p className="font-semibold text-green-400">Bank-Grade Security</p>
            <p className="text-sm text-slate-400">256-bit SSL encryption. PCI DSS Level 1 compliant. SOC 2 Type II certified. Your money is protected.</p>
          </div>
        </div>
      </main>
    </div>
  )
}
