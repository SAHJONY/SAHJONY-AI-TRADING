'use client'

import { useState } from 'react'
import { 
  Trash2, 
  Download, 
  Share2, 
  MoreHorizontal,
  Copy,
  RefreshCw,
  MessageSquare,
  Sparkles,
  Bookmark,
  Image
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface QuickActionsProps {
  onClear?: () => void
  onExport?: () => void
  onShare?: () => void
  onCopy?: () => void
  onRegenerate?: () => void
  className?: string
}

export function QuickActions({ 
  onClear, 
  onExport, 
  onShare, 
  onCopy,
  onRegenerate,
  className 
}: QuickActionsProps) {
  const [showMenu, setShowMenu] = useState(false)

  return (
    <div className={cn('flex items-center gap-1', className)}>
      {/* Quick prompts */}
      <QuickPrompt
        icon={Sparkles}
        label="Summarize"
        onClick={() => {/* TODO: Implement */}}
      />
      <QuickPrompt
        icon={Image}
        label="Analyze"
        onClick={() => {/* TODO: Implement */}}
      />
      <QuickPrompt
        icon={Bookmark}
        label="Save"
        onClick={() => {/* TODO: Implement */}}
      />

      <div className="w-px h-5 bg-border mx-1" />

      {/* Common actions */}
      <ActionButton
        icon={Copy}
        label="Copy"
        onClick={onCopy}
      />
      <ActionButton
        icon={RefreshCw}
        label="Regenerate"
        onClick={onRegenerate}
      />
      <ActionButton
        icon={Download}
        label="Export"
        onClick={onExport}
      />

      {/* More menu */}
      <div className="relative">
        <button
          onClick={() => setShowMenu(!showMenu)}
          className="p-2 rounded-lg text-zinc-400 hover:text-white hover:bg-surface transition-colors"
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>

        {showMenu && (
          <>
            <div 
              className="fixed inset-0 z-40" 
              onClick={() => setShowMenu(false)} 
            />
            <div className="absolute right-0 top-full mt-1 w-48 py-2 bg-surface-elevated border border-border rounded-xl shadow-xl z-50 animate-scale-in">
              <button
                onClick={() => {
                  setShowMenu(false)
                  onClear?.()
                }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-400 hover:bg-red-500/10 transition-colors"
              >
                <Trash2 className="h-4 w-4" />
                Clear conversation
              </button>
              <button
                onClick={() => {
                  setShowMenu(false)
                  onShare?.()
                }}
                className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-zinc-300 hover:bg-surface transition-colors"
              >
                <Share2 className="h-4 w-4" />
                Share conversation
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// Quick Prompt Button
function QuickPrompt({ 
  icon: Icon, 
  label, 
  onClick 
}: { 
  icon: typeof Sparkles
  label: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-zinc-400 hover:text-primary hover:bg-primary/10 rounded-lg transition-colors"
    >
      <Icon className="h-3.5 w-3.5" />
      {label}
    </button>
  )
}

// Action Button
function ActionButton({ 
  icon: Icon, 
  label, 
  onClick 
}: { 
  icon: typeof Copy
  label: string
  onClick?: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="p-2 rounded-lg text-zinc-400 hover:text-white hover:bg-surface transition-colors group relative"
      title={label}
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}