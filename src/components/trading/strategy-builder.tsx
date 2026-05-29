'use client'

import React, { useState } from 'react'
import { Plus, Trash2, Play, Save, Loader2, ChevronDown, ChevronUp, GripVertical } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Indicator, Condition, StrategyConditions, AssetType } from '@/types/trading'
import { TRADING_ASSETS, INDICATOR_TYPES } from '@/types/trading'

interface StrategyBuilderProps {
  initialName?: string
  initialDescription?: string
  initialAssetTypes?: AssetType[]
  initialIndicators?: Indicator[]
  initialConditions?: StrategyConditions
  onSave: (data: {
    name: string
    description: string
    assetTypes: AssetType[]
    indicators: Indicator[]
    conditions: StrategyConditions
  }) => Promise<void>
  className?: string
}

export function StrategyBuilder({
  initialName = '',
  initialDescription = '',
  initialAssetTypes = ['stock'],
  initialIndicators = [],
  initialConditions = { entry: [], exit: [] },
  onSave,
  className,
}: StrategyBuilderProps) {
  const [name, setName] = useState(initialName)
  const [description, setDescription] = useState(initialDescription)
  const [assetTypes, setAssetTypes] = useState<AssetType[]>(initialAssetTypes)
  const [indicators, setIndicators] = useState<Indicator[]>(initialIndicators)
  const [conditions, setConditions] = useState<StrategyConditions>(initialConditions)
  const [saving, setSaving] = useState(false)
  const [expandedSection, setExpandedSection] = useState<'indicators' | 'entry' | 'exit'>('indicators')

  const toggleAssetType = (at: AssetType) => {
    setAssetTypes(prev => prev.includes(at) ? prev.filter(a => a !== at) : [...prev, at])
  }

  const addIndicator = () => {
    setIndicators(prev => [...prev, {
      id: `ind_${Date.now()}`,
      name: '',
      type: 'sma',
      params: { period: 20 },
    }])
  }

  const updateIndicator = (id: string, updates: Partial<Indicator>) => {
    setIndicators(prev => prev.map(ind => ind.id === id ? { ...ind, ...updates } : ind))
  }

  const removeIndicator = (id: string) => {
    setIndicators(prev => prev.filter(ind => ind.id !== id))
  }

  const addCondition = (section: 'entry' | 'exit') => {
    setConditions(prev => ({
      ...prev,
      [section]: [...prev[section], {
        id: `cond_${Date.now()}`,
        indicator: '',
        operator: 'gt',
        value: 0,
      }],
    }))
  }

  const updateCondition = (section: 'entry' | 'exit', id: string, updates: Partial<Condition>) => {
    setConditions(prev => ({
      ...prev,
      [section]: prev[section].map(c => c.id === id ? { ...c, ...updates } : c),
    }))
  }

  const removeCondition = (section: 'entry' | 'exit', id: string) => {
    setConditions(prev => ({
      ...prev,
      [section]: prev[section].filter(c => c.id !== id),
    }))
  }

  const handleSave = async () => {
    if (!name) return
    setSaving(true)
    try {
      await onSave({
        name,
        description,
        assetTypes,
        indicators,
        conditions,
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Name & Description */}
      <div className="space-y-3">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Strategy Name"
          className="w-full px-4 py-3 bg-zinc-800 border border-border rounded-xl text-white text-lg font-semibold placeholder:text-zinc-600 focus:outline-none focus:border-primary transition-all"
        />
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Describe your strategy..."
          rows={2}
          className="w-full px-4 py-3 bg-zinc-800 border border-border rounded-xl text-sm text-white placeholder:text-zinc-600 focus:outline-none focus:border-primary transition-all resize-none"
        />
      </div>

      {/* Asset Types */}
      <div>
        <label className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2 block">
          Asset Types
        </label>
        <div className="flex gap-2">
          {(Object.entries(TRADING_ASSETS) as [AssetType, typeof TRADING_ASSETS['stock']][]).map(([key, info]) => (
            <button
              key={key}
              onClick={() => toggleAssetType(key)}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium transition-all border',
                assetTypes.includes(key)
                  ? 'bg-primary/20 text-primary border-primary/30'
                  : 'text-zinc-500 border-border hover:text-white hover:border-zinc-600'
              )}
            >
              {info.label}
            </button>
          ))}
        </div>
      </div>

      {/* Indicators */}
      <div>
        <button
          onClick={() => setExpandedSection(expandedSection === 'indicators' ? 'entry' : 'indicators')}
          className="flex items-center justify-between w-full py-2"
        >
          <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
            Indicators ({indicators.length})
          </span>
          {expandedSection === 'indicators' ? <ChevronUp className="h-4 w-4 text-zinc-500" /> : <ChevronDown className="h-4 w-4 text-zinc-500" />}
        </button>
        {expandedSection === 'indicators' && (
          <div className="space-y-3">
            {indicators.map((ind) => (
              <div key={ind.id} className="flex items-center gap-2 p-3 bg-zinc-800/50 rounded-lg border border-border">
                <GripVertical className="h-4 w-4 text-zinc-600" />
                <input
                  type="text"
                  value={ind.name}
                  onChange={(e) => updateIndicator(ind.id, { name: e.target.value })}
                  placeholder="Indicator name"
                  className="flex-1 bg-transparent text-sm text-white placeholder:text-zinc-600 focus:outline-none"
                />
                <select
                  value={ind.type}
                  onChange={(e) => updateIndicator(ind.id, { type: e.target.value as Indicator['type'] })}
                  className="bg-zinc-800 border border-border rounded-lg px-2 py-1 text-xs text-white"
                >
                  {INDICATOR_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
                <button onClick={() => removeIndicator(ind.id)} className="text-zinc-500 hover:text-red-400 transition-colors">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button
              onClick={addIndicator}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm text-zinc-400 hover:text-white border border-dashed border-border rounded-lg hover:border-primary/30 transition-all"
            >
              <Plus className="h-4 w-4" />
              Add Indicator
            </button>
          </div>
        )}
      </div>

      {/* Entry Conditions */}
      <div>
        <button
          onClick={() => setExpandedSection(expandedSection === 'entry' ? 'exit' : 'entry')}
          className="flex items-center justify-between w-full py-2"
        >
          <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">
            Entry Conditions ({conditions.entry.length})
          </span>
          {expandedSection === 'entry' ? <ChevronUp className="h-4 w-4 text-zinc-500" /> : <ChevronDown className="h-4 w-4 text-zinc-500" />}
        </button>
        {expandedSection === 'entry' && (
          <div className="space-y-3">
            {conditions.entry.map((cond) => (
              <div key={cond.id} className="flex items-center gap-2 p-3 bg-zinc-800/50 rounded-lg border border-border">
                <select
                  value={cond.indicator}
                  onChange={(e) => updateCondition('entry', cond.id, { indicator: e.target.value })}
                  className="bg-zinc-800 border border-border rounded-lg px-2 py-1 text-xs text-white flex-1"
                >
                  <option value="">Select indicator</option>
                  {indicators.map(ind => (
                    <option key={ind.id} value={ind.name || ind.id}>{ind.name || ind.type}</option>
                  ))}
                </select>
                <select
                  value={cond.operator}
                  onChange={(e) => updateCondition('entry', cond.id, { operator: e.target.value as Condition['operator'] })}
                  className="bg-zinc-800 border border-border rounded-lg px-2 py-1 text-xs text-white"
                >
                  <option value="gt">&gt;</option>
                  <option value="lt">&lt;</option>
                  <option value="gte">&gt;=</option>
                  <option value="lte">&lt;=</option>
                  <option value="eq">==</option>
                  <option value="cross_above">Crosses Above</option>
                  <option value="cross_below">Crosses Below</option>
                </select>
                <input
                  type="number"
                  value={cond.value}
                  onChange={(e) => updateCondition('entry', cond.id, { value: parseFloat(e.target.value) || 0 })}
                  className="w-20 bg-zinc-800 border border-border rounded-lg px-2 py-1 text-xs text-white text-center"
                />
                <button onClick={() => removeCondition('entry', cond.id)} className="text-zinc-500 hover:text-red-400 transition-colors">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button
              onClick={() => addCondition('entry')}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm text-zinc-400 hover:text-white border border-dashed border-border rounded-lg hover:border-primary/30 transition-all"
            >
              <Plus className="h-4 w-4" />
              Add Entry Condition
            </button>
          </div>
        )}
      </div>

      {/* Exit Conditions */}
      <div>
        <button
          onClick={() => setExpandedSection(expandedSection === 'exit' ? 'indicators' : 'exit')}
          className="flex items-center justify-between w-full py-2"
        >
          <span className="text-xs font-semibold text-red-400 uppercase tracking-wider">
            Exit Conditions ({conditions.exit.length})
          </span>
          {expandedSection === 'exit' ? <ChevronUp className="h-4 w-4 text-zinc-500" /> : <ChevronDown className="h-4 w-4 text-zinc-500" />}
        </button>
        {expandedSection === 'exit' && (
          <div className="space-y-3">
            {conditions.exit.map((cond) => (
              <div key={cond.id} className="flex items-center gap-2 p-3 bg-zinc-800/50 rounded-lg border border-border">
                <select
                  value={cond.indicator}
                  onChange={(e) => updateCondition('exit', cond.id, { indicator: e.target.value })}
                  className="bg-zinc-800 border border-border rounded-lg px-2 py-1 text-xs text-white flex-1"
                >
                  <option value="">Select indicator</option>
                  {indicators.map(ind => (
                    <option key={ind.id} value={ind.name || ind.id}>{ind.name || ind.type}</option>
                  ))}
                </select>
                <select
                  value={cond.operator}
                  onChange={(e) => updateCondition('exit', cond.id, { operator: e.target.value as Condition['operator'] })}
                  className="bg-zinc-800 border border-border rounded-lg px-2 py-1 text-xs text-white"
                >
                  <option value="gt">&gt;</option>
                  <option value="lt">&lt;</option>
                  <option value="gte">&gt;=</option>
                  <option value="lte">&lt;=</option>
                  <option value="eq">==</option>
                  <option value="cross_above">Crosses Above</option>
                  <option value="cross_below">Crosses Below</option>
                </select>
                <input
                  type="number"
                  value={cond.value}
                  onChange={(e) => updateCondition('exit', cond.id, { value: parseFloat(e.target.value) || 0 })}
                  className="w-20 bg-zinc-800 border border-border rounded-lg px-2 py-1 text-xs text-white text-center"
                />
                <button onClick={() => removeCondition('exit', cond.id)} className="text-zinc-500 hover:text-red-400 transition-colors">
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button
              onClick={() => addCondition('exit')}
              className="flex items-center gap-2 w-full px-3 py-2 text-sm text-zinc-400 hover:text-white border border-dashed border-border rounded-lg hover:border-primary/30 transition-all"
            >
              <Plus className="h-4 w-4" />
              Add Exit Condition
            </button>
          </div>
        )}
      </div>

      {/* Save Button */}
      <button
        onClick={handleSave}
        disabled={!name || saving}
        className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-primary text-white rounded-xl font-semibold hover:bg-primary-hover hover:shadow-primary transition-all disabled:opacity-30 disabled:cursor-not-allowed"
      >
        {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
        Save Strategy
      </button>
    </div>
  )
}
