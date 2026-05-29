'use client'

import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { CheckCircle, XCircle, AlertTriangle, X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'warning'

interface ToastItem {
  id: string
  type: ToastType
  message: string
}

interface ToastProps {
  type: ToastType
  message: string
  onClose: () => void
}

const icons = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
}

const colors = {
  success: 'text-success border-success/30 bg-success/10',
  error: 'text-error border-error/30 bg-error/10',
  warning: 'text-warning border-warning/30 bg-warning/10',
}

export function Toast({ type, message, onClose }: ToastProps) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      onClose()
    }, 4000)
    return () => clearTimeout(timer)
  }, [onClose])

  if (!mounted) return null

  const Icon = icons[type]

  return (
    <div
      className={cn(
        'fixed bottom-4 right-4 z-50 flex items-center gap-3 px-4 py-3 rounded-lg border backdrop-blur-sm animate-in slide-in-from-right duration-300',
        colors[type]
      )}
    >
      <Icon className="h-5 w-5 flex-shrink-0" />
      <p className="text-sm font-medium">{message}</p>
      <button
        onClick={onClose}
        className="p-1 hover:bg-white/10 rounded transition-colors"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}

// Toast container that listens for CustomEvents from static toast API
export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  useEffect(() => {
    const handleToastShow = (event: CustomEvent<{ type: ToastType; message: string }>) => {
      const id = Math.random().toString(36).substring(7)
      setToasts((prev) => [...prev, { id, ...event.detail }])
    }

    window.addEventListener('toast-show', handleToastShow as EventListener)
    return () => {
      window.removeEventListener('toast-show', handleToastShow as EventListener)
    }
  }, [])

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  return (
    <>
      {toasts.map((t) => (
        <Toast key={t.id} type={t.type} message={t.message} onClose={() => removeToast(t.id)} />
      ))}
    </>
  )
}

// Hook for components that need to show toasts inline
export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const addToast = (type: ToastType, message: string) => {
    const id = Math.random().toString(36).substring(7)
    setToasts((prev) => [...prev, { id, type, message }])
  }

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  return { toasts, addToast, removeToast }
}

// Static toast API for use outside React components
export const toast = {
  success: (message: string) => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('toast-show', { detail: { type: 'success', message } }))
    }
  },
  error: (message: string) => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('toast-show', { detail: { type: 'error', message } }))
    }
  },
  warning: (message: string) => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('toast-show', { detail: { type: 'warning', message } }))
    }
  },
}