import { forwardRef } from 'react'
import { cn } from '@/lib/utils'
import { Loader2 } from 'lucide-react'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'outline'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', loading, disabled, children, ...props }, ref) => {
    const isDisabled = disabled || loading

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={cn(
          'inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-50 disabled:pointer-events-none',
          {
            // Primary
            'bg-primary text-white hover:bg-primary-hover hover:shadow-primary': variant === 'primary',
            // Secondary
            'bg-surface border border-border text-zinc-300 hover:bg-surface-elevated hover:border-border-hover hover:text-white': variant === 'secondary',
            // Ghost
            'text-zinc-400 hover:bg-surface hover:text-white': variant === 'ghost',
            // Danger
            'bg-error text-white hover:bg-red-600 hover:shadow-lg hover:shadow-error/25': variant === 'danger',
            // Outline
            'border border-primary text-primary hover:bg-primary/10': variant === 'outline',
          },
          {
            // Sizes
            'px-3 py-1.5 text-xs': size === 'sm',
            'px-4 py-2.5 text-sm': size === 'md',
            'px-6 py-3.5 text-base': size === 'lg',
          },
          className
        )}
        {...props}
      >
        {loading && <Loader2 className="h-4 w-4 animate-spin" />}
        {children}
      </button>
    )
  }
)

Button.displayName = 'Button'