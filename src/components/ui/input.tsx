import { forwardRef } from 'react'
import { cn } from '@/lib/utils'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  icon?: React.ReactNode
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, icon, ...props }, ref) => {
    return (
      <div className="space-y-1.5">
        {label && (
          <label className="block text-sm font-medium text-zinc-300">
            {label}
          </label>
        )}
        <div className="relative">
          {icon && (
            <div className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-500">
              {icon}
            </div>
          )}
          <input
            ref={ref}
            className={cn(
              'w-full rounded-xl border bg-surface px-4 py-3 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 transition-all duration-150',
              error
                ? 'border-error focus:border-error focus:ring-error/30'
                : 'border-border focus:border-primary focus:ring-primary/30',
              icon && 'pl-11',
              className
            )}
            {...props}
          />
        </div>
        {error && (
          <p className="text-xs text-error mt-1.5">{error}</p>
        )}
      </div>
    )
  }
)

Input.displayName = 'Input'

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, label, error, ...props }, ref) => {
    return (
      <div className="space-y-1.5">
        {label && (
          <label className="block text-sm font-medium text-zinc-300">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          className={cn(
            'w-full rounded-xl border bg-surface px-4 py-3 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:ring-2 transition-all duration-150 min-h-[120px] resize-y',
            error
              ? 'border-error focus:border-error focus:ring-error/30'
              : 'border-border focus:border-primary focus:ring-primary/30',
            className
          )}
          {...props}
        />
        {error && (
          <p className="text-xs text-error mt-1.5">{error}</p>
        )}
      </div>
    )
  }
)

Textarea.displayName = 'Textarea'