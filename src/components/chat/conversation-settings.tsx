'use client'

import { useState } from 'react'
import { Settings2, X, ChevronDown, ChevronUp, RotateCcw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Slider } from '@/components/ui/slider'

interface ConversationSettingsProps {
  onSettingsChange?: (settings: ConversationSettings) => void
  className?: string
}

export interface ConversationSettings {
  temperature: number
  maxTokens: number
  model: string
  enableHermes: boolean
  enableFreebuff: boolean
  streaming: boolean
}

const DEFAULT_SETTINGS: ConversationSettings = {
  temperature: 0.7,
  maxTokens: 4096,
  model: 'hermes-3',
  enableHermes: true,
  enableFreebuff: true,
  streaming: true,
}

const MODELS = [
  { id: 'hermes-3', name: 'Hermes 3', provider: 'NousResearch', description: 'Advanced reasoning with tool use' },
  { id: 'claude-3-5-sonnet', name: 'Claude 3.5 Sonnet', provider: 'Anthropic', description: 'Balanced performance' },
  { id: 'gpt-4-turbo', name: 'GPT-4 Turbo', provider: 'OpenAI', description: 'Fast and capable' },
  { id: 'gemini-pro', name: 'Gemini Pro', provider: 'Google', description: 'Multimodal understanding' },
]

export function ConversationSettings({ onSettingsChange, className }: ConversationSettingsProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [settings, setSettings] = useState<ConversationSettings>(DEFAULT_SETTINGS)

  const updateSetting = <K extends keyof ConversationSettings>(key: K, value: ConversationSettings[K]) => {
    const newSettings = { ...settings, [key]: value }
    setSettings(newSettings)
    onSettingsChange?.(newSettings)
  }

  const resetSettings = () => {
    setSettings(DEFAULT_SETTINGS)
    onSettingsChange?.(DEFAULT_SETTINGS)
  }

  return (
    <div className={cn('', className)}>
      {/* Toggle Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-2 px-3 py-2 rounded-xl text-sm transition-all',
          isOpen 
            ? 'bg-primary/10 text-primary border border-primary/20' 
            : 'text-zinc-400 hover:text-white hover:bg-surface border border-transparent'
        )}
      >
        <Settings2 className="h-4 w-4" />
        <span className="hidden sm:inline">Settings</span>
        {isOpen ? (
          <ChevronUp className="h-3 w-3" />
        ) : (
          <ChevronDown className="h-3 w-3" />
        )}
      </button>

      {/* Settings Panel */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-80 bg-surface-elevated border border-border rounded-xl shadow-xl z-50 animate-scale-in overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-border">
            <h3 className="text-sm font-semibold text-white">Conversation Settings</h3>
            <div className="flex items-center gap-2">
              <button
                onClick={resetSettings}
                className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-surface transition-colors"
                title="Reset to defaults"
              >
                <RotateCcw className="h-4 w-4" />
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-surface transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Settings Content */}
          <div className="p-4 space-y-5 max-h-[400px] overflow-y-auto">
            {/* Model Selection */}
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-2">Model</label>
              <select
                value={settings.model}
                onChange={(e) => updateSetting('model', e.target.value)}
                className="w-full px-3 py-2.5 bg-surface border border-border rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:border-primary focus:ring-primary/30"
              >
                {MODELS.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.name} ({model.provider})
                  </option>
                ))}
              </select>
              <p className="text-xs text-zinc-500 mt-1.5">
                {MODELS.find(m => m.id === settings.model)?.description}
              </p>
            </div>

            {/* Temperature */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-medium text-zinc-400">Temperature</label>
                <span className="text-xs text-primary font-mono">{settings.temperature.toFixed(1)}</span>
              </div>
              <Slider 
                value={[settings.temperature * 10]} 
                onValueChange={(v) => updateSetting('temperature', v[0] / 10)}
                min={0}
                max={20}
                step={1}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-zinc-500 mt-1">
                <span>Precise</span>
                <span>Creative</span>
              </div>
            </div>

            {/* Max Tokens */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-medium text-zinc-400">Max Tokens</label>
                <span className="text-xs text-primary font-mono">{settings.maxTokens}</span>
              </div>
              <Slider 
                value={[settings.maxTokens / 32]} 
                onValueChange={(v) => updateSetting('maxTokens', v[0] * 32)}
                min={256 / 32}
                max={8192 / 32}
                step={1}
                className="w-full"
              />
              <div className="flex justify-between text-xs text-zinc-500 mt-1">
                <span>256</span>
                <span>8192</span>
              </div>
            </div>

            {/* Toggles */}
            <div className="space-y-3 pt-2 border-t border-border">
              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <p className="text-sm text-white">Hermes Agent</p>
                  <p className="text-xs text-zinc-500">Use Hermes for reasoning</p>
                </div>
                <Toggle 
                  enabled={settings.enableHermes} 
                  onChange={(v) => updateSetting('enableHermes', v)} 
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <p className="text-sm text-white">Freebuff</p>
                  <p className="text-xs text-zinc-500">Enable coding tool delegation</p>
                </div>
                <Toggle 
                  enabled={settings.enableFreebuff} 
                  onChange={(v) => updateSetting('enableFreebuff', v)} 
                />
              </label>

              <label className="flex items-center justify-between cursor-pointer">
                <div>
                  <p className="text-sm text-white">Streaming</p>
                  <p className="text-xs text-zinc-500">Receive responses in real-time</p>
                </div>
                <Toggle 
                  enabled={settings.streaming} 
                  onChange={(v) => updateSetting('streaming', v)} 
                />
              </label>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Toggle Component
function Toggle({ enabled, onChange }: { enabled: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      className={cn(
        'relative w-10 h-6 rounded-full transition-colors',
        enabled ? 'bg-primary' : 'bg-surface border border-border'
      )}
    >
      <span className={cn(
        'absolute top-1 w-4 h-4 rounded-full bg-white transition-transform',
        enabled ? 'left-5' : 'left-1'
      )} />
    </button>
  )
}