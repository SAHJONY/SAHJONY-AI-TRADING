'use client'

import { useState } from 'react'
import { useAuth } from '@/components/providers'
import { TopNav } from '@/components/layout/top-nav'
import {
  Check, Zap, Shield, TrendingUp, Crown, ArrowRight,
  CreditCard, Landmark, Wallet, CircleDot, BadgeCheck,
  Clock, Star, Gift, ChevronDown, Sparkles, Building2,
  Banknote, QrCode
} from 'lucide-react'

const plans = [
  {
    id: 'analyst',
    name: 'Analyst',
    price: '$999',
    period: '/month',
    description: 'Professional AI-powered trading signals and single-agent deployment.',
    features: [
      '1 AI Trading Agent',
      'Real-time market signals',
      'Basic risk management',
      'Email & in-app alerts',
      'Daily performance reports',
      'Paper trading sandbox',
    ],
    highlight: false,
    cta: 'Start 7-Day Free Trial',
  },
  {
    id: 'fund',
    name: 'Fund',
    price: '$2,999',
    period: '/month',
    description: 'Multi-agent portfolio with institutional-grade risk controls.',
    features: [
      '5 AI Trading Agents',
      'Portfolio-level risk management',
      'Cross-agent correlation analysis',
      'Priority signal execution',
      'Custom agent configurations',
      'Real-money trading enabled',
      'Dedicated account manager',
      'API access',
    ],
    highlight: true,
    cta: 'Start 7-Day Free Trial',
  },
  {
    id: 'enterprise',
    name: 'Enterprise',
    price: 'Custom',
    period: '',
    description: 'White-label AI trading infrastructure with unlimited agents and full control.',
    features: [
      'Unlimited AI Trading Agents',
      'Custom model training',
      'White-label deployment',
      'On-premise option',
      '24/7 dedicated support',
      'Regulatory compliance suite',
      'Custom integrations',
      'SLA guarantees',
    ],
    highlight: false,
    cta: 'Contact Sales',
  },
]

const paymentMethods = [
  { id: 'stripe', name: 'Card / ACH', icon: CreditCard, description: 'Visa, Mastercard, Amex, ACH Direct Debit', color: 'text-violet-400', bg: 'bg-violet-500/[0.06]', border: 'border-violet-500/10' },
  { id: 'paypal', name: 'PayPal', icon: Wallet, description: 'PayPal balance or linked bank', color: 'text-blue-400', bg: 'bg-blue-500/[0.06]', border: 'border-blue-500/10' },
  { id: 'cashapp', name: 'Cash App Pay', icon: QrCode, description: 'Cash App balance or linked debit', color: 'text-emerald-400', bg: 'bg-emerald-500/[0.06]', border: 'border-emerald-500/10' },
  { id: 'square', name: 'Square Pay', icon: Banknote, description: 'Square balance or card on file', color: 'text-orange-400', bg: 'bg-orange-500/[0.06]', border: 'border-orange-500/10' },
]

export default function PricingPage() {
  const { user } = useAuth()
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null)
  const [selectedPayment, setSelectedPayment] = useState<string>('stripe')
  const [showPaymentSheet, setShowPaymentSheet] = useState(false)
  const [processing, setProcessing] = useState(false)

  const handleSelectPlan = (planId: string) => {
    if (planId === 'enterprise') {
      window.location.href = '/contact'
      return
    }
    setSelectedPlan(planId)
    setShowPaymentSheet(true)
  }

  const handleCheckout = async () => {
    if (!selectedPlan || !user) return
    setProcessing(true)

    try {
      const endpoints: Record<string, string> = {
        stripe: '/api/stripe/checkout',
        paypal: '/api/paypal/create-order',
        cashapp: '/api/cashapp/create-payment',
        square: '/api/cashapp/create-payment', // Square handles Cash App + Square Pay
      }

      const res = await fetch(endpoints[selectedPayment], {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          planId: selectedPlan,
          userId: user.id,
          email: user.email,
        }),
      })

      const data = await res.json()

      if (data.url) {
        window.location.href = data.url
      } else if (data.approvalUrl) {
        window.location.href = data.approvalUrl
      } else if (data.checkoutUrl) {
        window.location.href = data.checkoutUrl
      }
    } catch (error) {
      console.error('Checkout error:', error)
    } finally {
      setProcessing(false)
    }
  }

  return (
    <div className="min-h-screen bg-background noise-overlay grid-lines">
      <TopNav />
      <main className="container-custom py-8">
        {/* Header */}
        <div className="text-center mb-16 animate-slide-up">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass border border-white/[0.04] mb-6">
            <Gift className="h-3.5 w-3.5 text-accent" />
            <span className="text-[11px] text-accent font-medium tracking-tesla uppercase">7-Day Free Trial on All Plans</span>
          </div>
          <h1 className="text-5xl md:text-6xl font-display font-bold text-white tracking-tighter mb-4">
            Institutional-Grade<br />
            <span className="gradient-text">AI Trading</span>
          </h1>
          <p className="text-text-secondary text-lg font-light max-w-2xl mx-auto">
            Deploy autonomous AI agents that trade 24/7. Start with a 7-day free trial — no charge until your trial ends.
          </p>
        </div>

        {/* Trial Banner */}
        <div className="max-w-3xl mx-auto mb-10 p-5 rounded-2xl bg-accent/[0.03] border border-accent/10 animate-slide-up" style={{ animationDelay: '80ms' }}>
          <div className="flex items-center gap-4">
            <div className="w-11 h-11 rounded-[14px] bg-accent/[0.08] flex items-center justify-center border border-accent/10 flex-shrink-0">
              <Clock className="h-5 w-5 text-accent" />
            </div>
            <div>
              <p className="text-sm font-medium text-white">7-Day Free Trial — Cancel Anytime</p>
              <p className="text-[11px] text-text-dim mt-0.5">
                Full access to all plan features for 7 days. Your card isn't charged until the trial ends. Cancel with one click — no questions asked.
              </p>
            </div>
          </div>
        </div>

        {/* Pricing Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-6xl mx-auto mb-12">
          {plans.map((plan, idx) => (
            <div
              key={plan.id}
              className={`card-tesla p-8 animate-slide-up relative ${
                plan.highlight ? 'card-tesla-premium' : ''
              }`}
              style={{ animationDelay: `${120 + idx * 80}ms` }}
            >
              {plan.highlight && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <span className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full bg-gradient-to-r from-accent-deep to-accent text-[#1a0a00] text-[11px] font-semibold tracking-tesla uppercase">
                    <Star className="h-3 w-3" />
                    Most Popular
                  </span>
                </div>
              )}

              <div className="mb-6">
                <h3 className="text-xl font-display font-semibold text-white tracking-tight mb-1">{plan.name}</h3>
                <p className="text-[12px] text-text-dim font-light">{plan.description}</p>
              </div>

              <div className="mb-8">
                <span className="text-4xl font-display font-bold text-white tracking-tight">{plan.price}</span>
                <span className="text-text-muted text-sm">{plan.period}</span>
              </div>

              <ul className="space-y-3 mb-8">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-start gap-3">
                    <Check className="h-4 w-4 text-primary flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-text-secondary font-light">{feature}</span>
                  </li>
                ))}
              </ul>

              <button
                onClick={() => handleSelectPlan(plan.id)}
                className={`w-full flex items-center justify-center gap-2 px-6 py-4 rounded-full font-medium text-sm transition-all duration-500 ${
                  plan.highlight
                    ? 'bg-gradient-to-r from-accent-deep to-accent text-[#1a0a00] shadow-accent hover:shadow-[0_4px_30px_rgba(245,158,11,0.25)]'
                    : 'bg-gradient-to-r from-primary-deep to-primary text-white shadow-primary hover:shadow-primary-lg'
                }`}
              >
                {plan.cta}
                <ArrowRight className="h-4 w-4" />
              </button>

              <p className="text-center text-[10px] text-text-dim mt-3 tracking-wide">
                {plan.id !== 'enterprise' ? '7-day free trial · Cancel anytime' : 'Custom pricing tailored to your firm'}
              </p>
            </div>
          ))}
        </div>

        {/* Payment Methods Section */}
        <div className="max-w-4xl mx-auto mb-12 animate-slide-up" style={{ animationDelay: '400ms' }}>
          <div className="text-center mb-8">
            <p className="text-[11px] text-text-dim tracking-tesla uppercase font-medium mb-2">Accepted Payment Methods</p>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {paymentMethods.map((method) => (
              <div
                key={method.id}
                className={`p-5 rounded-2xl border transition-all duration-400 text-center ${
                  selectedPayment === method.id
                    ? `${method.bg} ${method.border}`
                    : 'bg-white/[0.02] border-white/[0.04] hover:border-white/[0.08]'
                }`}
              >
                <method.icon className={`h-6 w-6 mx-auto mb-2 ${selectedPayment === method.id ? method.color : 'text-text-dim'}`} />
                <p className="text-sm font-medium text-white">{method.name}</p>
                <p className="text-[10px] text-text-dim mt-1">{method.description}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Security & Trust */}
        <div className="max-w-3xl mx-auto animate-slide-up" style={{ animationDelay: '500ms' }}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {[
              { icon: Shield, label: 'Bank-Level Encryption', desc: '256-bit TLS · PCI DSS Level 1' },
              { icon: BadgeCheck, label: 'SOC 2 Type II', desc: 'Audited infrastructure compliance' },
              { icon: Sparkles, label: 'No Lock-In', desc: 'Cancel anytime · Export all data' },
            ].map((item) => (
              <div key={item.label} className="flex items-start gap-3 p-4">
                <item.icon className="h-4 w-4 text-text-dim flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-[12px] font-medium text-white">{item.label}</p>
                  <p className="text-[10px] text-text-dim">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ═══ PAYMENT SHEET MODAL ═══ */}
        {showPaymentSheet && selectedPlan && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => setShowPaymentSheet(false)}>
            <div className="w-full max-w-lg card-tesla p-8 animate-slide-up" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-8">
                <div>
                  <h2 className="text-xl font-display font-semibold text-white tracking-tight">Complete Checkout</h2>
                  <p className="text-sm text-text-secondary font-light mt-1">
                    {plans.find(p => p.id === selectedPlan)?.name} Plan · 7-day free trial
                  </p>
                </div>
                <button onClick={() => setShowPaymentSheet(false)} className="text-text-dim hover:text-white transition-colors text-xl">×</button>
              </div>

              {/* Trial Notice */}
              <div className="p-4 rounded-2xl bg-accent/[0.03] border border-accent/10 mb-8">
                <div className="flex items-center gap-3">
                  <Gift className="h-4 w-4 text-accent flex-shrink-0" />
                  <p className="text-[12px] text-text-secondary">
                    <span className="text-accent font-medium">$0 today.</span> Your 7-day free trial starts immediately. You'll be charged ${selectedPlan === 'analyst' ? '999' : '2,999'}/month after trial ends.
                  </p>
                </div>
              </div>

              {/* Payment Method Selection */}
              <p className="text-[11px] text-text-dim tracking-tesla uppercase font-medium mb-3">Choose Payment Method</p>
              <div className="space-y-2 mb-8">
                {paymentMethods.map((method) => (
                  <button
                    key={method.id}
                    onClick={() => setSelectedPayment(method.id)}
                    className={`w-full flex items-center gap-4 p-4 rounded-2xl border transition-all duration-400 ${
                      selectedPayment === method.id
                        ? `${method.bg} ${method.border}`
                        : 'bg-white/[0.02] border-white/[0.04] hover:border-white/[0.08]'
                    }`}
                  >
                    <method.icon className={`h-5 w-5 ${selectedPayment === method.id ? method.color : 'text-text-dim'}`} />
                    <div className="text-left flex-1">
                      <p className="text-sm font-medium text-white">{method.name}</p>
                      <p className="text-[10px] text-text-dim">{method.description}</p>
                    </div>
                    <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                      selectedPayment === method.id ? 'border-primary bg-primary/20' : 'border-white/10'
                    }`}>
                      {selectedPayment === method.id && <div className="w-2.5 h-2.5 rounded-full bg-primary" />}
                    </div>
                  </button>
                ))}
              </div>

              {/* CTA */}
              <button
                onClick={handleCheckout}
                disabled={processing}
                className="w-full flex items-center justify-center gap-2 px-6 py-4 bg-gradient-to-r from-accent-deep to-accent text-[#1a0a00] rounded-full font-semibold text-sm shadow-accent hover:shadow-[0_4px_30px_rgba(245,158,11,0.2)] transition-all duration-500 disabled:opacity-50"
              >
                {processing ? (
                  <>
                    <div className="w-4 h-4 border-2 border-[#1a0a00]/30 border-t-[#1a0a00] rounded-full animate-spin" />
                    Processing...
                  </>
                ) : (
                  <>
                    <Zap className="h-4 w-4" />
                    Start 7-Day Free Trial
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>

              <p className="text-center text-[10px] text-text-dim mt-4 tracking-wide">
                By subscribing, you agree to our Terms of Service and Privacy Policy.
              </p>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
