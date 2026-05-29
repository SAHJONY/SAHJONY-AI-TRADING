import { Bot, MessageSquare, Zap, Shield, Headphones, Users, BarChart3, Code, Globe, Check, ArrowRight } from 'lucide-react'
import Link from 'next/link'
import { TopNav } from '@/components/layout/top-nav'

// Force dynamic rendering to avoid build-time Supabase initialization
export const dynamic = 'force-dynamic'

const plans = [
  {
    name: 'Starter',
    price: 49,
    description: 'Perfect for getting started with AI agents',
    features: [
      { icon: Bot, text: '5 agents included' },
      { icon: MessageSquare, text: '100 conversations/month' },
      { icon: Zap, text: 'Basic model access (GPT-3.5)' },
      { icon: Shield, text: 'Community support' },
      { icon: Users, text: '1 workspace' },
    ],
    cta: 'Get Started',
    popular: false,
  },
  {
    name: 'Pro',
    price: 99,
    description: 'Best for professionals and growing teams',
    features: [
      { icon: Bot, text: '25 agents included' },
      { icon: MessageSquare, text: 'Unlimited conversations' },
      { icon: Zap, text: 'Premium models (GPT-4, Claude)' },
      { icon: Headphones, text: 'Priority email support' },
      { icon: Users, text: '5 workspaces' },
      { icon: BarChart3, text: 'Usage analytics' },
      { icon: Code, text: 'API access' },
    ],
    cta: 'Start Free Trial',
    popular: true,
  },
  {
    name: 'Business',
    price: 149,
    description: 'For established teams scaling up',
    features: [
      { icon: Bot, text: '50 agents included' },
      { icon: MessageSquare, text: 'Unlimited conversations' },
      { icon: Zap, text: 'All models + fine-tuning' },
      { icon: Headphones, text: 'Priority support' },
      { icon: Users, text: '10 workspaces' },
      { icon: BarChart3, text: 'Advanced analytics' },
      { icon: Code, text: 'Full API access' },
      { icon: Globe, text: 'Custom integrations' },
    ],
    cta: 'Start Free Trial',
    popular: false,
  },
  {
    name: 'Enterprise',
    price: 199,
    description: 'For large organizations with custom needs',
    features: [
      { icon: Bot, text: 'Unlimited agents' },
      { icon: MessageSquare, text: 'Unlimited conversations' },
      { icon: Zap, text: 'All models + fine-tuning' },
      { icon: Headphones, text: '24/7 dedicated support' },
      { icon: Users, text: 'Unlimited workspaces' },
      { icon: BarChart3, text: 'Advanced reporting' },
      { icon: Code, text: 'Full API access' },
      { icon: Shield, text: 'SSO & SAML' },
    ],
    cta: 'Contact Sales',
    popular: false,
  },
]

const faqs = [
  {
    question: 'Can I change plans later?',
    answer: 'Yes, you can upgrade or downgrade your plan at any time. Changes take effect immediately.',
  },
  {
    question: 'What happens when I hit my conversation limit?',
    answer: "You'll receive a notification and can upgrade to continue using SAHJONY without interruption.",
  },
  {
    question: 'Is there a free trial?',
    answer: 'Yes! All paid plans come with a 14-day free trial. No credit card required to start.',
  },
  {
    question: 'What payment methods do you accept?',
    answer: 'We accept all major credit cards, PayPal, and wire transfers for Enterprise plans.',
  },
]

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      
      <main className="container-custom py-16">
        {/* Header */}
        <div className="text-center mb-16 animate-slide-up">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-primary/10 border border-primary/20 mb-6">
            <span className="text-sm text-primary font-medium">14-day free trial • No credit card required</span>
          </div>
          <h1 className="text-4xl md:text-5xl font-bold text-white mb-4">
            Simple, Transparent Pricing
          </h1>
          <p className="text-lg text-zinc-400 max-w-2xl mx-auto">
            Choose the plan that fits your needs. All plans include access to our Unified Brain architecture.
          </p>
        </div>

        {/* Billing Toggle */}
        <div className="flex items-center justify-center gap-4 mb-16 animate-slide-up" style={{ animationDelay: '100ms' }}>
          <span className="text-sm text-zinc-400">Monthly</span>
          <button className="relative w-12 h-6 rounded-full bg-surface border border-border transition-colors">
            <div className="absolute right-1 top-1 w-4 h-4 rounded-full bg-primary transition-transform" />
          </button>
          <span className="text-sm text-white flex items-center gap-2">
            Annual 
            <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400">
              Save 20%
            </span>
          </span>
        </div>

        {/* Pricing Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-20">
          {plans.map((plan, index) => (
            <div
              key={plan.name}
              className={`relative rounded-2xl border p-6 transition-all duration-200 hover:scale-[1.02] animate-slide-up ${
                plan.popular
                  ? 'border-primary bg-surface-elevated ring-1 ring-primary/30 shadow-primary'
                  : 'border-border bg-surface-elevated hover:border-primary/30'
              }`}
              style={{ animationDelay: `${150 + index * 50}ms` }}
            >
              {plan.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <span className="px-4 py-1 text-xs font-semibold bg-primary text-white rounded-full shadow-primary">
                    Most Popular
                  </span>
                </div>
              )}
              
              <div className="mb-6">
                <h3 className="text-lg font-semibold text-white mb-1">{plan.name}</h3>
                <p className="text-sm text-zinc-500">{plan.description}</p>
              </div>
              
              <div className="mb-6">
                <span className="text-4xl font-bold text-white">${plan.price}</span>
                <span className="text-zinc-500 ml-1">/month</span>
              </div>
              
              <ul className="space-y-3 mb-6">
                {plan.features.map((feature, idx) => (
                  <li key={idx} className="flex items-start gap-3 text-sm">
                    <div className={cn(
                      'w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5',
                      plan.popular ? 'bg-primary/20 text-primary' : 'bg-emerald-500/10 text-emerald-400'
                    )}>
                      <Check className="h-3 w-3" />
                    </div>
                    <span className="text-zinc-300">{feature.text}</span>
                  </li>
                ))}
              </ul>
              
              <Link
                href="mailto:sales@sahjony.com?subject=Enterprise%20Plan%20Inquiry"
                className={cn(
                  'block w-full text-center py-3 rounded-xl font-semibold transition-all duration-150',
                  plan.popular
                    ? 'bg-primary text-white hover:bg-primary-hover hover:shadow-primary'
                    : 'bg-surface border border-border text-zinc-300 hover:bg-surface-elevated hover:text-white'
                )}
              >
                {plan.cta}
              </Link>
            </div>
          ))}
        </div>

        {/* FAQ Section */}
        <div className="max-w-3xl mx-auto">
          <h2 className="text-2xl font-bold text-white text-center mb-10">
            Frequently Asked Questions
          </h2>
          
          <div className="space-y-4">
            {faqs.map((faq, index) => (
              <div 
                key={index} 
                className="border border-border rounded-2xl p-6 bg-surface-elevated hover:border-border-hover transition-colors"
              >
                <h3 className="text-lg font-medium text-white mb-2">{faq.question}</h3>
                <p className="text-zinc-400 leading-relaxed">{faq.answer}</p>
              </div>
            ))}
          </div>
        </div>

        {/* CTA Section */}
        <div className="text-center mt-20 animate-slide-up">
          <div className="relative overflow-hidden rounded-3xl bg-surface-elevated border border-border p-8 md:p-12">
            <div className="absolute inset-0 overflow-hidden pointer-events-none">
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-96 h-96 bg-primary/10 rounded-full blur-3xl" />
            </div>
            <div className="relative">
              <h2 className="text-2xl md:text-3xl font-bold text-white mb-4">
                Ready to get started?
              </h2>
              <p className="text-zinc-400 max-w-xl mx-auto mb-8">
                Join thousands of teams using SAHJONY to automate their workflows with AI agents.
              </p>
              <Link
                href="/login"
                className="inline-flex items-center gap-2 px-8 py-4 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover hover:shadow-primary transition-all"
              >
                Start Free Trial
                <ArrowRight className="h-5 w-5" />
              </Link>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-10 mt-16">
        <div className="container-custom flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-primary/10">
              <Bot className="h-5 w-5 text-primary" />
            </div>
            <span className="font-bold text-lg gradient-text">SAHJONY</span>
          </div>
          <div className="flex items-center gap-8 text-sm text-zinc-500">
            <Link href="/privacy" className="hover:text-white transition-colors">Privacy</Link>
            <Link href="/terms" className="hover:text-white transition-colors">Terms</Link>
            <Link href="/support" className="hover:text-white transition-colors">Support</Link>
          </div>
          <p className="text-sm text-zinc-600">© 2025 SAHJONY. All rights reserved.</p>
        </div>
      </footer>
    </div>
  )
}

import { cn } from '@/lib/utils'