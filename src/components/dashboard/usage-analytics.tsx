'use client'

import { useState } from 'react'
import { BarChart3, TrendingUp, MessageSquare, Bot, Clock, Zap, Activity, ChevronRight, Calendar } from 'lucide-react'
import { cn } from '@/lib/utils'

interface UsageAnalyticsProps {
  className?: string
}

interface DailyUsage {
  date: string
  messages: number
  agents: number
  tokens: number
}

export function UsageAnalytics({ className }: UsageAnalyticsProps) {
  const [period, setPeriod] = useState<'7d' | '30d' | '90d'>('7d')

  // Mock data - in production this would come from an API
  const weeklyData: DailyUsage[] = [
    { date: 'Mon', messages: 42, agents: 3, tokens: 12500 },
    { date: 'Tue', messages: 68, agents: 5, tokens: 18200 },
    { date: 'Wed', messages: 35, agents: 2, tokens: 9800 },
    { date: 'Thu', messages: 91, agents: 7, tokens: 24500 },
    { date: 'Fri', messages: 56, agents: 4, tokens: 15200 },
    { date: 'Sat', messages: 23, agents: 2, tokens: 7200 },
    { date: 'Sun', messages: 18, agents: 1, tokens: 5400 },
  ]

  const stats = {
    totalMessages: 333,
    totalAgents: 8,
    totalTokens: 92800,
    avgResponseTime: '145ms',
    activeDays: 7,
    peakHour: '2:00 PM',
  }

  const maxMessages = Math.max(...weeklyData.map(d => d.messages))

  return (
    <div className={cn('space-y-6', className)}>
      {/* Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          icon={MessageSquare}
          label="Total Messages"
          value={stats.totalMessages.toLocaleString()}
          change="+12%"
          positive
        />
        <StatCard
          icon={Bot}
          label="Active Agents"
          value={stats.totalAgents.toString()}
          change="+2"
          positive
        />
        <StatCard
          icon={Zap}
          label="Tokens Used"
          value={(stats.totalTokens / 1000).toFixed(1) + 'K'}
          change="+8%"
          positive
        />
        <StatCard
          icon={Clock}
          label="Avg Response"
          value={stats.avgResponseTime}
          change="-5ms"
          positive
        />
      </div>

      {/* Chart Section */}
      <div className="card-elevated p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10">
              <BarChart3 className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">Message Volume</h3>
              <p className="text-xs text-zinc-500">Daily conversation activity</p>
            </div>
          </div>
          
          {/* Period Selector */}
          <div className="flex items-center gap-1 bg-surface rounded-lg p-1">
            {(['7d', '30d', '90d'] as const).map((p) => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                className={cn(
                  'px-3 py-1.5 text-xs font-medium rounded-md transition-colors',
                  period === p
                    ? 'bg-primary text-white'
                    : 'text-zinc-400 hover:text-white'
                )}
              >
                {p === '7d' ? '7 days' : p === '30d' ? '30 days' : '90 days'}
              </button>
            ))}
          </div>
        </div>

        {/* Bar Chart */}
        <div className="h-48 flex items-end justify-between gap-2">
          {weeklyData.map((day, index) => (
            <div key={day.date} className="flex-1 flex flex-col items-center gap-2">
              <div className="w-full flex flex-col items-center justify-end h-36">
                <div 
                  className={cn(
                    'w-full rounded-t-lg transition-all duration-300',
                    index === weeklyData.length - 1 
                      ? 'bg-primary' 
                      : 'bg-primary/30 hover:bg-primary/50'
                  )}
                  style={{ height: `${(day.messages / maxMessages) * 100}%` }}
                />
              </div>
              <span className="text-xs text-zinc-500">{day.date}</span>
            </div>
          ))}
        </div>

        {/* Legend */}
        <div className="flex items-center justify-center gap-6 mt-4 pt-4 border-t border-border">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-primary" />
            <span className="text-xs text-zinc-500">Messages</span>
          </div>
          <div className="text-xs text-zinc-500">
            Peak: <span className="text-primary font-medium">{stats.peakHour}</span>
          </div>
        </div>
      </div>

      {/* Additional Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Top Agents */}
        <div className="card-elevated p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">Top Agents</h3>
            <button className="text-xs text-zinc-400 hover:text-primary flex items-center gap-1">
              View all <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <div className="space-y-3">
            {[
              { name: 'Code Assistant', usage: 156, conversations: 89 },
              { name: 'Data Analyst', usage: 98, conversations: 45 },
              { name: 'Customer Support', usage: 79, conversations: 112 },
            ].map((agent, index) => (
              <div key={agent.name} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-zinc-600 w-4">{index + 1}</span>
                  <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                    <Bot className="h-4 w-4 text-primary" />
                  </div>
                  <span className="text-sm text-white">{agent.name}</span>
                </div>
                <div className="text-right">
                  <span className="text-sm font-semibold text-white">{agent.usage}</span>
                  <span className="text-xs text-zinc-500 ml-1">msgs</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Quick Stats */}
        <div className="card-elevated p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-white">Activity Insights</h3>
            <Activity className="h-4 w-4 text-zinc-500" />
          </div>
          <div className="space-y-4">
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg">
              <div className="flex items-center gap-3">
                <Calendar className="h-4 w-4 text-zinc-500" />
                <span className="text-sm text-zinc-300">Active Days</span>
              </div>
              <span className="text-sm font-semibold text-white">{stats.activeDays}/7</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg">
              <div className="flex items-center gap-3">
                <TrendingUp className="h-4 w-4 text-zinc-500" />
                <span className="text-sm text-zinc-300">Growth Rate</span>
              </div>
              <span className="text-sm font-semibold text-emerald-400">+23%</span>
            </div>
            <div className="flex items-center justify-between p-3 bg-surface rounded-lg">
              <div className="flex items-center gap-3">
                <MessageSquare className="h-4 w-4 text-zinc-500" />
                <span className="text-sm text-zinc-300">Avg/Day</span>
              </div>
              <span className="text-sm font-semibold text-white">48</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// Stat Card Component
function StatCard({ 
  icon: Icon, 
  label, 
  value, 
  change,
  positive 
}: { 
  icon: typeof MessageSquare
  label: string
  value: string
  change: string
  positive: boolean
}) {
  return (
    <div className="card-elevated p-4 animate-slide-up">
      <div className="flex items-center gap-3 mb-3">
        <div className="p-2 rounded-lg bg-surface">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <span className="text-xs text-zinc-500">{label}</span>
      </div>
      <div className="flex items-end justify-between">
        <span className="text-2xl font-bold text-white">{value}</span>
        <span className={cn(
          'text-xs px-2 py-0.5 rounded-full',
          positive ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
        )}>
          {change}
        </span>
      </div>
    </div>
  )
}