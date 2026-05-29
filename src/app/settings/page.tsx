'use client'

export const dynamic = 'force-dynamic'

import { useState, useEffect } from 'react'
import { createClient } from '@/lib/supabase/client'
import { TopNav } from '@/components/layout/top-nav'
import { Button } from '@/components/ui/button'
import { toast } from '@/components/ui/toast'
import { User, Key, Bell, Shield, Palette, Globe, Copy, Check, RefreshCw, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

type TabId = 'profile' | 'api-keys' | 'notifications' | 'appearance' | 'security'

interface Tab {
  id: TabId
  label: string
  icon: typeof User
}

const tabs: Tab[] = [
  { id: 'profile', label: 'Profile', icon: User },
  { id: 'api-keys', label: 'API Keys', icon: Key },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'appearance', label: 'Appearance', icon: Palette },
  { id: 'security', label: 'Security', icon: Shield },
]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('profile')
  const [user, setUser] = useState<{ email?: string } | null>(null)
  const supabase = createClient()

  useEffect(() => {
    const getUser = async () => {
      const { data: { user } } = await supabase.auth.getUser()
      setUser(user)
    }
    getUser()
  }, [supabase.auth])

  return (
    <div className="min-h-screen bg-background">
      <TopNav />
      <main className="container-custom py-8">
        <div className="mb-8 animate-slide-up">
          <h1 className="text-2xl font-bold text-white">Settings</h1>
          <p className="text-zinc-500 mt-1">Manage your account and preferences</p>
        </div>
        <div className="flex flex-col lg:flex-row gap-8">
          <div className="lg:w-64 flex-shrink-0">
            <nav className="flex lg:flex-col gap-1 overflow-x-auto lg:overflow-visible pb-2 lg:pb-0">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium whitespace-nowrap transition-all',
                    activeTab === tab.id
                      ? 'bg-primary/10 text-primary border border-primary/20'
                      : 'text-zinc-400 hover:text-white hover:bg-surface'
                  )}
                >
                  <tab.icon className="h-4 w-4" />
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>
          <div className="flex-1 min-w-0">
            <div className="card-elevated animate-fade-in">
              {activeTab === 'profile' && <ProfileTab user={user} />}
              {activeTab === 'api-keys' && <APIKeysTab />}
              {activeTab === 'notifications' && <NotificationsTab />}
              {activeTab === 'appearance' && <AppearanceTab />}
              {activeTab === 'security' && <SecurityTab />}
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

function ProfileTab({ user }: { user: { email?: string } | null }) {
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    await new Promise(resolve => setTimeout(resolve, 1000))
    toast.success('Profile updated successfully')
    setSaving(false)
  }

  return (
    <div className="p-6">
      <h2 className="text-lg font-semibold text-white mb-6">Profile Information</h2>
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <div className="w-20 h-20 rounded-2xl bg-primary/20 flex items-center justify-center">
            <span className="text-2xl font-bold text-primary">{user?.email?.[0]?.toUpperCase() || 'U'}</span>
          </div>
          <div>
            <p className="text-sm font-medium text-white">Profile Picture</p>
            <p className="text-xs text-zinc-500 mt-1">JPG, PNG or GIF. Max 2MB.</p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-2">Display Name</label>
            <input
              type="text"
              placeholder="Your name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2.5 bg-surface border border-border rounded-lg text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:border-primary focus:ring-primary/30"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-zinc-400 mb-2">Email</label>
            <input
              type="text"
              placeholder="your@email.com"
              value={user?.email || ''}
              disabled
              className="w-full px-3 py-2.5 bg-surface border border-border rounded-lg text-sm text-white disabled:opacity-50"
            />
            <p className="text-xs text-zinc-500 mt-1.5">Contact support to change your email</p>
          </div>
        </div>
        <div className="flex justify-end pt-4 border-t border-border">
          <Button onClick={handleSave} disabled={saving}>{saving ? 'Saving...' : 'Save Changes'}</Button>
        </div>
      </div>
    </div>
  )
}

function APIKeysTab() {
  const [copied, setCopied] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)

  const apiKeys = [
    { id: '1', name: 'Production API Key', key: 'sk_live_xxxxxxxxxxxxxx', created: '2025-01-15', lastUsed: '2 hours ago', env: 'production' },
    { id: '2', name: 'Development Key', key: 'sk_test_xxxxxxxxxxxxxx', created: '2025-01-10', lastUsed: 'Yesterday', env: 'development' },
  ]

  const copyKey = (key: string, id: string) => {
    navigator.clipboard.writeText(key)
    setCopied(id)
    setTimeout(() => setCopied(null), 2000)
    toast.success('API key copied to clipboard')
  }

  const generateKey = async () => {
    setGenerating(true)
    await new Promise(resolve => setTimeout(resolve, 1500))
    toast.success('New API key generated')
    setGenerating(false)
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-white">API Keys</h2>
          <p className="text-sm text-zinc-500 mt-1">Manage your API keys for external integrations</p>
        </div>
        <Button onClick={generateKey} disabled={generating}>
          {generating ? (
            <><RefreshCw className="h-4 w-4 animate-spin mr-2" />Generating...</>
          ) : (
            <><Key className="h-4 w-4 mr-2" />Generate New Key</>
          )}
        </Button>
      </div>
      <div className="space-y-4">
        {apiKeys.map((apiKey) => (
          <div key={apiKey.id} className="p-4 bg-surface rounded-xl border border-border hover:border-border-hover transition-colors">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <h3 className="text-sm font-medium text-white">{apiKey.name}</h3>
                  <span className={cn(
                    'text-xs px-2 py-0.5 rounded-full',
                    apiKey.env === 'production' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'
                  )}>{apiKey.env}</span>
                </div>
                <div className="flex items-center gap-2">
                  <code className="text-xs text-zinc-400 bg-surface-elevated px-2 py-1 rounded font-mono">{apiKey.key}</code>
                  <button
                    onClick={() => copyKey(apiKey.key, apiKey.id)}
                    className="p-1 rounded hover:bg-surface-elevated transition-colors"
                  >
                    {copied === apiKey.id ? (
                      <Check className="h-4 w-4 text-emerald-400" />
                    ) : (
                      <Copy className="h-4 w-4 text-zinc-400" />
                    )}
                  </button>
                </div>
                <div className="flex items-center gap-4 mt-3 text-xs text-zinc-500">
                  <span>Created {apiKey.created}</span>
                  <span>-</span>
                  <span>Last used {apiKey.lastUsed}</span>
                </div>
              </div>
              <button className="text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 px-3 py-1.5 rounded-lg transition-colors">Revoke</button>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-8 p-4 bg-primary/5 border border-primary/20 rounded-xl">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-primary flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-white">API Key Security</p>
            <p className="text-xs text-zinc-400 mt-1">Keep your API keys secure. Never share them in public repositories or client-side code.</p>
          </div>
        </div>
      </div>
    </div>
  )
}

function NotificationsTab() {
  const [settings, setSettings] = useState({
    email: true,
    push: true,
    weekly: false,
    marketing: false
  })

  const toggle = (key: keyof typeof settings) => {
    setSettings(prev => ({ ...prev, [key]: !prev[key] }))
    toast.success('Notification preferences updated')
  }

  return (
    <div className="p-6">
      <h2 className="text-lg font-semibold text-white mb-6">Notification Preferences</h2>
      <div className="space-y-4">
        {[
          { key: 'email', label: 'Email notifications', description: 'Receive updates about your agents via email' },
          { key: 'push', label: 'Push notifications', description: 'Get real-time alerts in your browser' },
          { key: 'weekly', label: 'Weekly digest', description: 'Summary of your agent activity' },
          { key: 'marketing', label: 'Marketing emails', description: 'Product updates and special offers' },
        ].map((item) => (
          <label key={item.key} className="flex items-center justify-between p-4 bg-surface rounded-xl cursor-pointer hover:bg-surface-elevated transition-colors">
            <div>
              <p className="text-sm font-medium text-white">{item.label}</p>
              <p className="text-xs text-zinc-500 mt-0.5">{item.description}</p>
            </div>
            <button
              onClick={() => toggle(item.key as keyof typeof settings)}
              className={cn(
                'relative w-10 h-6 rounded-full transition-colors',
                settings[item.key as keyof typeof settings] ? 'bg-primary' : 'bg-surface border border-border'
              )}
            >
              <span className={cn(
                'absolute top-1 w-4 h-4 rounded-full bg-white transition-transform',
                settings[item.key as keyof typeof settings] ? 'left-5' : 'left-1'
              )} />
            </button>
          </label>
        ))}
      </div>
    </div>
  )
}

function AppearanceTab() {
  const [theme, setTheme] = useState('dark')
  const [language, setLanguage] = useState('en')

  return (
    <div className="p-6">
      <h2 className="text-lg font-semibold text-white mb-6">Appearance Settings</h2>
      <div className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-zinc-400 mb-3">Theme</label>
          <div className="flex gap-3">
            {[
              { id: 'dark', label: 'Dark', preview: 'bg-zinc-900 border-zinc-700' },
              { id: 'light', label: 'Light', preview: 'bg-white border-zinc-200' },
              { id: 'system', label: 'System', preview: 'bg-gradient-to-r from-zinc-900 to-white' }
            ].map((option) => (
              <button
                key={option.id}
                onClick={() => setTheme(option.id)}
                className={cn(
                  'flex-1 p-4 rounded-xl border-2 transition-all',
                  theme === option.id ? 'border-primary bg-primary/5' : 'border-border hover:border-border-hover'
                )}
              >
                <div className={cn('w-full h-12 rounded-lg mb-3', option.preview)} />
                <span className="text-sm font-medium text-white">{option.label}</span>
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-zinc-400 mb-2">Language</label>
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="w-full px-3 py-2.5 bg-surface border border-border rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:border-primary focus:ring-primary/30"
          >
            <option value="en">English</option>
            <option value="es">Espanol</option>
            <option value="fr">Francais</option>
          </select>
        </div>
      </div>
    </div>
  )
}

function SecurityTab() {
  const [sessions, setSessions] = useState([
    { id: '1', device: 'Chrome on MacOS', location: 'New York, US', lastActive: 'Active now' },
    { id: '2', device: 'Safari on iPhone', location: 'New York, US', lastActive: '2 hours ago' },
  ])

  const revokeSession = (id: string) => {
    setSessions(prev => prev.filter(s => s.id !== id))
    toast.success('Session revoked')
  }

  return (
    <div className="p-6">
      <h2 className="text-lg font-semibold text-white mb-6">Security Settings</h2>
      <div className="mb-8">
        <h3 className="text-sm font-medium text-white mb-4">Password</h3>
        <Button variant="secondary"><Key className="h-4 w-4 mr-2" />Change Password</Button>
      </div>
      <div className="mb-8 p-4 bg-surface rounded-xl">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-emerald-500/10"><Shield className="h-5 w-5 text-emerald-400" /></div>
            <div>
              <p className="text-sm font-medium text-white">Two-Factor Authentication</p>
              <p className="text-xs text-zinc-500 mt-0.5">Add an extra layer of security to your account</p>
            </div>
          </div>
          <span className="text-xs px-2 py-1 rounded-full bg-emerald-500/10 text-emerald-400">Enabled</span>
        </div>
      </div>
      <div>
        <h3 className="text-sm font-medium text-white mb-4">Active Sessions</h3>
        <div className="space-y-3">
          {sessions.map((session) => (
            <div key={session.id} className="flex items-center justify-between p-4 bg-surface rounded-xl">
              <div className="flex items-center gap-3">
                <Globe className="h-5 w-5 text-zinc-500" />
                <div>
                  <p className="text-sm font-medium text-white">{session.device}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">{session.location} - {session.lastActive}</p>
                </div>
              </div>
              <button
                onClick={() => revokeSession(session.id)}
                className="text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 px-3 py-1.5 rounded-lg transition-colors"
              >Revoke</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}