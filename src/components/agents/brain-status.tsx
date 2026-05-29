'use client'

import { useState, useEffect } from 'react'
import { Bot, Brain, Wifi, WifiOff, AlertCircle, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'

interface BrainStatusProps {
  className?: string
  showDetails?: boolean
  onRetry?: () => void
}

interface ServiceStatus {
  name: string
  status: 'connected' | 'disconnected' | 'checking' | 'error'
  url?: string
  latency?: number
  error?: string
}

export function BrainStatus({ className, showDetails = false, onRetry }: BrainStatusProps) {
  const [expanded, setExpanded] = useState(false)
  const [services, setServices] = useState<ServiceStatus[]>([
    { name: 'Hermes Agent', status: 'checking' },
    { name: 'Freebuff', status: 'checking' },
  ])
  const [lastCheck, setLastCheck] = useState<Date | null>(null)
  const [checking, setChecking] = useState(false)

  const checkServices = async () => {
    setChecking(true)
    
    // Simulate health checks (in production, these would call actual endpoints)
    const hermesHealth = await checkHermesHealth()
    const freebuffHealth = await checkFreebuffHealth()

    setServices([
      { 
        name: 'Hermes Agent', 
        status: hermesHealth.status,
        url: process.env.NEXT_PUBLIC_HERMES_AGENT_URL || 'http://localhost:8642',
        latency: hermesHealth.latency,
        error: hermesHealth.error 
      },
      { 
        name: 'Freebuff', 
        status: freebuffHealth.status,
        url: process.env.NEXT_PUBLIC_FREEBUFF_API_URL || 'http://localhost:3001',
        latency: freebuffHealth.latency,
        error: freebuffHealth.error 
      },
    ])
    setLastCheck(new Date())
    setChecking(false)
  }

  useEffect(() => {
    checkServices()
    // Check every 30 seconds
    const interval = setInterval(checkServices, 30000)
    return () => clearInterval(interval)
  }, [])

  const overallStatus = services.every(s => s.status === 'connected') 
    ? 'connected' 
    : services.some(s => s.status === 'connected') 
      ? 'partial' 
      : 'disconnected'

  return (
    <div className={cn('bg-surface-elevated border border-border rounded-xl overflow-hidden', className)}>
      {/* Header - Always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-surface transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className={cn(
            'p-2 rounded-lg',
            overallStatus === 'connected' ? 'bg-emerald-500/10' :
            overallStatus === 'partial' ? 'bg-amber-500/10' : 'bg-red-500/10'
          )}>
            <Brain className={cn(
              'h-5 w-5',
              overallStatus === 'connected' ? 'text-emerald-400' :
              overallStatus === 'partial' ? 'text-amber-400' : 'text-red-400'
            )} />
          </div>
          <div className="text-left">
            <p className="text-sm font-medium text-white">Unified Brain</p>
            <p className="text-xs text-zinc-500">
              {overallStatus === 'connected' ? 'All services operational' :
               overallStatus === 'partial' ? 'Some services offline' : 'Services unavailable'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {checking && (
            <RefreshCw className="h-4 w-4 text-zinc-400 animate-spin" />
          )}
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-zinc-400" />
          ) : (
            <ChevronDown className="h-4 w-4 text-zinc-400" />
          )}
        </div>
      </button>

      {/* Expanded Details */}
      {expanded && showDetails && (
        <div className="border-t border-border">
          {/* Service List */}
          <div className="p-4 space-y-3">
            {services.map((service) => (
              <div key={service.name} className="flex items-center justify-between p-3 rounded-lg bg-surface">
                <div className="flex items-center gap-3">
                  {service.status === 'connected' ? (
                    <Wifi className="h-4 w-4 text-emerald-400" />
                  ) : service.status === 'error' ? (
                    <AlertCircle className="h-4 w-4 text-red-400" />
                  ) : (
                    <WifiOff className="h-4 w-4 text-zinc-500" />
                  )}
                  <div>
                    <p className="text-sm font-medium text-white">{service.name}</p>
                    <p className="text-xs text-zinc-500 truncate max-w-[200px]">
                      {service.url || 'Not configured'}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <span className={cn(
                    'text-xs px-2 py-1 rounded-full',
                    service.status === 'connected' ? 'bg-emerald-500/10 text-emerald-400' :
                    service.status === 'error' ? 'bg-red-500/10 text-red-400' :
                    service.status === 'checking' ? 'bg-zinc-500/10 text-zinc-400' :
                    'bg-amber-500/10 text-amber-400'
                  )}>
                    {service.status === 'connected' && service.latency ? `${service.latency}ms` : service.status}
                  </span>
                  {service.error && (
                    <p className="text-xs text-red-400 mt-1 max-w-[180px] truncate">
                      {service.error}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Footer with retry and last check time */}
          <div className="flex items-center justify-between p-4 border-t border-border bg-surface/50">
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <span>Last checked:</span>
              <span className="text-zinc-400">
                {lastCheck ? lastCheck.toLocaleTimeString() : 'Never'}
              </span>
            </div>
            <button
              onClick={() => {
                checkServices()
                onRetry?.()
              }}
              disabled={checking}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-primary hover:bg-primary/10 rounded-lg transition-colors disabled:opacity-50"
            >
              <RefreshCw className={cn('h-3 w-3', checking && 'animate-spin')} />
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Quick status badges when collapsed */}
      {!expanded && (
        <div className="flex items-center gap-2 px-4 pb-3">
          {services.map((service) => (
            <span key={service.name} className={cn(
              'text-xs px-2 py-1 rounded-full',
              service.status === 'connected' ? 'bg-emerald-500/10 text-emerald-400' :
              service.status === 'checking' ? 'bg-zinc-500/10 text-zinc-400' :
              'bg-red-500/10 text-red-400'
            )}>
              {service.name}: {service.status === 'connected' ? 'Online' : service.status === 'checking' ? '...' : 'Offline'}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// Mock health check functions - in production these would make actual API calls
async function checkHermesHealth(): Promise<{ status: 'connected' | 'disconnected' | 'checking' | 'error'; latency?: number; error?: string }> {
  try {
    const hermesUrl = process.env.NEXT_PUBLIC_HERMES_AGENT_URL || process.env.HERMES_AGENT_URL || 'http://localhost:8642'
    
    // Skip actual fetch in demo mode - just return checking status
    if (hermesUrl.includes('localhost')) {
      return { status: 'disconnected', error: 'Localhost URL - deploy to production' }
    }

    const start = Date.now()
    const response = await fetch(`${hermesUrl}/health`, { 
      method: 'GET',
      signal: AbortSignal.timeout(5000)
    })
    const latency = Date.now() - start

    return response.ok 
      ? { status: 'connected', latency }
      : { status: 'error', error: `HTTP ${response.status}` }
  } catch (error) {
    return { 
      status: 'disconnected', 
      error: error instanceof Error ? error.message : 'Connection failed' 
    }
  }
}

async function checkFreebuffHealth(): Promise<{ status: 'connected' | 'disconnected' | 'checking' | 'error'; latency?: number; error?: string }> {
  try {
    const freebuffUrl = process.env.NEXT_PUBLIC_FREEBUFF_API_URL || process.env.FREEBUFF_API_URL || 'http://localhost:3001'
    
    if (freebuffUrl.includes('localhost')) {
      return { status: 'disconnected', error: 'Localhost URL - deploy to production' }
    }

    const start = Date.now()
    const response = await fetch(`${freebuffUrl}/health`, { 
      method: 'GET',
      signal: AbortSignal.timeout(5000)
    })
    const latency = Date.now() - start

    return response.ok 
      ? { status: 'connected', latency }
      : { status: 'error', error: `HTTP ${response.status}` }
  } catch (error) {
    return { 
      status: 'disconnected', 
      error: error instanceof Error ? error.message : 'Connection failed' 
    }
  }
}