'use client'

import { useState } from 'react'
import { useAuth } from '@/components/providers'
import { Mail, Phone, MapPin, Send, Building2, Globe, Clock, ArrowRight } from 'lucide-react'

export default function ContactPage() {
  const { user } = useAuth()
  const [submitted, setSubmitted] = useState(false)
  const [form, setForm] = useState({
    name: '', email: '', company: '', subject: 'general', message: ''
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitted(true)
  }

  const contactMethods = [
    {
      icon: Mail,
      label: 'Email',
      value: 'sahjonycapitalllc@outlook.com',
      href: 'mailto:sahjonycapitalllc@outlook.com',
      description: 'Institutional inquiries & partnerships'
    },
    {
      icon: Phone,
      label: 'Phone',
      value: 'Available for clients',
      href: '#',
      description: 'Direct line for funded accounts'
    },
    {
      icon: Globe,
      label: 'Global Operations',
      value: '24/7/365',
      href: '/markets',
      description: '60+ exchanges, 72 languages'
    }
  ]

  const officeInfo = [
    { icon: Building2, label: 'Firm', value: 'Sahjony Capital LLC' },
    { icon: Clock, label: 'Markets', value: '24/7/365 — Crypto & Forex' },
    { icon: MapPin, label: 'Jurisdiction', value: 'United States' },
  ]

  return (
    <div className="min-h-screen bg-background">
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-border/30">
        <div className="absolute inset-0 bg-gradient-to-b from-primary/5 via-transparent to-transparent" />
        <div className="container-custom relative py-16 md:py-24">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 text-primary text-xs font-medium mb-6 border border-primary/20">
              <Send className="h-3 w-3" />
              Contact Us
            </div>
            <h1 className="text-4xl md:text-5xl font-display font-bold text-white tracking-tight mb-4">
              Let's Build Your{' '}
              <span className="gradient-text">Trading Edge</span>
            </h1>
            <p className="text-lg text-text-secondary max-w-2xl">
              Whether you're an institutional investor, accredited trader, or exploring AI-driven
              trading — our team is ready to connect.
            </p>
          </div>
        </div>
      </section>

      <div className="container-custom py-12 md:py-20">
        <div className="grid lg:grid-cols-5 gap-8">
          {/* Contact Form */}
          <div className="lg:col-span-3">
            <div className="card-tesla p-6 md:p-8">
              {submitted ? (
                <div className="text-center py-12">
                  <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-6">
                    <Send className="h-8 w-8 text-primary" />
                  </div>
                  <h3 className="text-xl font-display font-bold text-white mb-2">Message Sent</h3>
                  <p className="text-text-secondary mb-6">
                    Our team will respond within 24 hours. For urgent institutional inquiries,
                    email us directly.
                  </p>
                  <button
                    onClick={() => setSubmitted(false)}
                    className="btn btn-secondary px-6 py-2"
                  >
                    Send Another Message
                  </button>
                </div>
              ) : (
                <>
                  <h2 className="text-xl font-display font-bold text-white mb-6">
                    Send a Message
                  </h2>
                  <form onSubmit={handleSubmit} className="space-y-5">
                    <div className="grid sm:grid-cols-2 gap-5">
                      <div>
                        <label className="block text-sm font-medium text-text-secondary mb-1.5">Full Name</label>
                        <input
                          type="text"
                          required
                          value={form.name}
                          onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                          className="input"
                          placeholder="John Smith"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-text-secondary mb-1.5">Email</label>
                        <input
                          type="email"
                          required
                          value={form.email}
                          onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                          className="input"
                          placeholder="john@firm.com"
                        />
                      </div>
                    </div>
                    <div className="grid sm:grid-cols-2 gap-5">
                      <div>
                        <label className="block text-sm font-medium text-text-secondary mb-1.5">Company / Firm</label>
                        <input
                          type="text"
                          value={form.company}
                          onChange={e => setForm(f => ({ ...f, company: e.target.value }))}
                          className="input"
                          placeholder="Optional"
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-text-secondary mb-1.5">Subject</label>
                        <select
                          value={form.subject}
                          onChange={e => setForm(f => ({ ...f, subject: e.target.value }))}
                          className="input"
                        >
                          <option value="general">General Inquiry</option>
                          <option value="institutional">Institutional Onboarding</option>
                          <option value="partnership">Partnership</option>
                          <option value="technical">Technical Support</option>
                          <option value="billing">Billing & Funding</option>
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-text-secondary mb-1.5">Message</label>
                      <textarea
                        required
                        rows={5}
                        value={form.message}
                        onChange={e => setForm(f => ({ ...f, message: e.target.value }))}
                        className="input resize-none"
                        placeholder="Tell us about your trading goals and how we can help..."
                      />
                    </div>
                    <button
                      type="submit"
                      className="btn btn-primary w-full py-3 text-sm font-semibold"
                    >
                      <Send className="h-4 w-4" />
                      Send Message
                      <ArrowRight className="h-4 w-4 ml-1" />
                    </button>
                  </form>
                </>
              )}
            </div>
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-2 space-y-6">
            {/* Contact Methods */}
            <div className="card-tesla p-6">
              <h3 className="text-lg font-display font-bold text-white mb-5">Get in Touch</h3>
              <div className="space-y-5">
                {contactMethods.map(method => (
                  <a
                    key={method.label}
                    href={method.href}
                    className="flex items-start gap-4 group"
                  >
                    <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0 group-hover:bg-primary/20 transition-colors">
                      <method.icon className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-white">{method.label}</p>
                      <p className="text-sm text-text-secondary">{method.value}</p>
                      <p className="text-xs text-text-muted mt-0.5">{method.description}</p>
                    </div>
                  </a>
                ))}
              </div>
            </div>

            {/* Firm Info */}
            <div className="card-tesla p-6">
              <h3 className="text-lg font-display font-bold text-white mb-5">Firm Details</h3>
              <div className="space-y-4">
                {officeInfo.map(info => (
                  <div key={info.label} className="flex items-center gap-3">
                    <info.icon className="h-4 w-4 text-text-muted" />
                    <div>
                      <p className="text-xs text-text-muted">{info.label}</p>
                      <p className="text-sm text-white">{info.value}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick Actions */}
            <div className="card-tesla p-6">
              <h3 className="text-lg font-display font-bold text-white mb-4">Quick Actions</h3>
              <div className="space-y-3">
                <a href="/pricing" className="flex items-center justify-between p-3 rounded-xl bg-white/[0.02] hover:bg-white/[0.04] border border-border/50 transition-all group">
                  <span className="text-sm text-text-secondary group-hover:text-white transition-colors">View Pricing Plans</span>
                  <ArrowRight className="h-4 w-4 text-text-muted group-hover:text-white transition-colors" />
                </a>
                <a href="/funding" className="flex items-center justify-between p-3 rounded-xl bg-white/[0.02] hover:bg-white/[0.04] border border-border/50 transition-all group">
                  <span className="text-sm text-text-secondary group-hover:text-white transition-colors">Fund Your Account</span>
                  <ArrowRight className="h-4 w-4 text-text-muted group-hover:text-white transition-colors" />
                </a>
                <a href="/agents" className="flex items-center justify-between p-3 rounded-xl bg-white/[0.02] hover:bg-white/[0.04] border border-border/50 transition-all group">
                  <span className="text-sm text-text-secondary group-hover:text-white transition-colors">Explore AI Agents</span>
                  <ArrowRight className="h-4 w-4 text-text-muted group-hover:text-white transition-colors" />
                </a>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
