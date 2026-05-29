'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Plus, Bot, Settings, MessageSquare, ChevronRight, TrendingUp, BarChart3, Brain, Wallet, Play, LineChart } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Agent } from '@/types/database'

interface SidebarProps {
  agents: Agent[]
}

export function Sidebar({ agents }: SidebarProps) {
  const pathname = usePathname()

  return (
    <aside className="w-72 border-r border-border bg-surface/30 hidden lg:block">
      <div className="flex flex-col h-full">
        {/* Create Agent Button */}
        <div className="p-4">
          <Link
            href="/agents/new"
            className="flex items-center justify-center gap-2 w-full px-4 py-3 bg-primary text-white text-sm font-semibold rounded-xl hover:bg-primary-hover hover:shadow-primary transition-all"
          >
            <Plus className="h-4 w-4" />
            Create Agent
          </Link>
        </div>

        {/* Quick Links */}
        <div className="px-3 mb-3 space-y-1">
          <Link
            href="/trading"
            className={cn(
              'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all',
              pathname.startsWith('/trading')
                ? 'bg-primary/10 text-primary'
                : 'text-zinc-400 hover:text-white hover:bg-surface'
            )}
          >
            <TrendingUp className="h-4 w-4" />
            <span>Trading</span>
            {pathname.startsWith('/trading') && <ChevronRight className="h-3 w-3 ml-auto" />}
          </Link>

          {/* Trading sub-navigation */}
          {pathname.startsWith('/trading') && (
            <div className="ml-6 space-y-1">
              <Link
                href="/trading"
                className={cn(
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-all',
                  pathname === '/trading'
                    ? 'bg-primary/5 text-primary'
                    : 'text-zinc-500 hover:text-zinc-300'
                )}
              >
                <LineChart className="h-3 w-3" />
                <span>Dashboard</span>
              </Link>
              <Link
                href="/trading/strategies"
                className={cn(
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-all',
                  pathname === '/trading/strategies'
                    ? 'bg-primary/5 text-primary'
                    : 'text-zinc-500 hover:text-zinc-300'
                )}
              >
                <Brain className="h-3 w-3" />
                <span>Strategies</span>
              </Link>
              <Link
                href="/trading/backtesting"
                className={cn(
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-all',
                  pathname === '/trading/backtesting'
                    ? 'bg-primary/5 text-primary'
                    : 'text-zinc-500 hover:text-zinc-300'
                )}
              >
                <Play className="h-3 w-3" />
                <span>Backtesting</span>
              </Link>
              <Link
                href="/trading/portfolio"
                className={cn(
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-all',
                  pathname === '/trading/portfolio'
                    ? 'bg-primary/5 text-primary'
                    : 'text-zinc-500 hover:text-zinc-300'
                )}
              >
                <Wallet className="h-3 w-3" />
                <span>Portfolio</span>
              </Link>
            </div>
          )}

          <Link
            href="/conversations"
            className={cn(
              'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all',
              pathname === '/conversations'
                ? 'bg-primary/10 text-primary'
                : 'text-zinc-400 hover:text-white hover:bg-surface'
            )}
          >
            <MessageSquare className="h-4 w-4" />
            <span>All Conversations</span>
          </Link>
        </div>

        {/* Divider */}
        <div className="px-4 mb-2">
          <div className="border-t border-border" />
        </div>

        {/* Agents List */}
        <div className="flex-1 overflow-y-auto px-3">
          <p className="px-3 py-2 text-xs font-semibold text-zinc-500 uppercase tracking-wider">
            Your Agents
          </p>
          {agents.length === 0 ? (
            <div className="px-3 py-8 text-center">
              <div className="w-12 h-12 rounded-xl bg-surface mx-auto mb-3 flex items-center justify-center">
                <Bot className="h-6 w-6 text-zinc-600" />
              </div>
              <p className="text-sm text-zinc-500 mb-1">No agents yet</p>
              <p className="text-xs text-zinc-600">Create your first agent to get started</p>
            </div>
          ) : (
            <div className="space-y-1 pb-4">
              {agents.map((agent) => {
                const isActive = pathname === `/agents/${agent.id}`
                return (
                  <Link
                    key={agent.id}
                    href={`/agents/${agent.id}`}
                    className={cn(
                      'group flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all duration-150',
                      isActive
                        ? 'bg-primary/10 text-primary border border-primary/20'
                        : 'text-zinc-400 hover:text-white hover:bg-surface border border-transparent'
                    )}
                  >
                    <div className={cn(
                      'p-1.5 rounded-lg transition-colors',
                      isActive ? 'bg-primary/20' : 'bg-surface group-hover:bg-border'
                    )}>
                      <Bot className="h-4 w-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <span className="truncate font-medium">{agent.name}</span>
                    </div>
                    <span
                      className={cn(
                        'w-2 h-2 rounded-full flex-shrink-0',
                        agent.status === 'active' ? 'bg-success' : 'bg-zinc-600'
                      )}
                    />
                    <ChevronRight className={cn(
                      'h-4 w-4 text-zinc-600 transition-all opacity-0 group-hover:opacity-100',
                      isActive && 'opacity-100 text-primary'
                    )} />
                  </Link>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-border">
          <Link
            href="/settings"
            className="flex items-center gap-3 px-3 py-2.5 text-sm text-zinc-400 hover:text-white rounded-xl hover:bg-surface transition-all"
          >
            <Settings className="h-4 w-4" />
            <span>Settings</span>
          </Link>
        </div>
      </div>
    </aside>
  )
}