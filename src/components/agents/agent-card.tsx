import Link from 'next/link'
import { Bot, MoreHorizontal, Pencil, Trash2, ArrowRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatDate } from '@/lib/utils'
import { MODEL_DISPLAY_NAMES } from '@/lib/constants'
import type { Agent } from '@/types/database'

interface AgentCardProps {
  agent: Agent
  onDelete?: (id: string) => void
}

export function AgentCard({ agent, onDelete }: AgentCardProps) {
  return (
    <div className="group card-elevated card-hover relative">
      <Link href={`/agents/${agent.id}`} className="block p-5">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-xl bg-primary/10 group-hover:bg-primary/20 transition-colors">
              <Bot className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h3 className="font-semibold text-white text-lg">{agent.name}</h3>
              <p className="text-sm text-zinc-500 mt-0.5">
                {MODEL_DISPLAY_NAMES[agent.model] || agent.model}
              </p>
            </div>
          </div>
          <span
            className={cn(
              'badge',
              agent.status === 'active'
                ? 'badge-success'
                : 'bg-zinc-700/50 text-zinc-400'
            )}
          >
            <span className={cn(
              'w-1.5 h-1.5 rounded-full mr-1.5',
              agent.status === 'active' ? 'bg-emerald-400' : 'bg-zinc-500'
            )} />
            {agent.status}
          </span>
        </div>

        {/* Description */}
        {agent.description && (
          <p className="text-sm text-zinc-400 line-clamp-2 mb-4 leading-relaxed">
            {agent.description}
          </p>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-3 border-t border-border/50">
          <span className="text-xs text-zinc-500">Updated {formatDate(agent.updated_at)}</span>
          <span className="flex items-center gap-1 text-xs text-primary opacity-0 group-hover:opacity-100 transition-opacity">
            Open
            <ArrowRight className="h-3 w-3" />
          </span>
        </div>
      </Link>

      {/* Actions */}
      <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-all flex gap-1.5">
        <Link
          href={`/agents/${agent.id}/edit`}
          className="p-2 rounded-xl bg-surface hover:bg-border text-zinc-400 hover:text-white transition-all"
          title="Edit agent"
        >
          <Pencil className="h-4 w-4" />
        </Link>
        <button
          onClick={(e) => {
            e.preventDefault()
            onDelete?.(agent.id)
          }}
          className="p-2 rounded-xl bg-surface hover:bg-error/20 text-zinc-400 hover:text-error transition-all"
          title="Delete agent"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}