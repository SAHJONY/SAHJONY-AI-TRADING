'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'

interface SliderProps {
  value: number[]
  onValueChange: (value: number[]) => void
  min?: number
  max?: number
  step?: number
  className?: string
  disabled?: boolean
}

export function Slider({ 
  value, 
  onValueChange, 
  min = 0, 
  max = 100, 
  step = 1,
  className,
  disabled = false 
}: SliderProps) {
  const [isDragging, setIsDragging] = useState(false)

  const percentage = ((value[0] - min) / (max - min)) * 100

  const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    if (disabled) return
    setIsDragging(true)
    updateValue(e.clientX, e.currentTarget.parentElement)
    
    const handleMouseMove = (moveEvent: MouseEvent) => {
      updateValue(moveEvent.clientX, e.currentTarget.parentElement)
    }
    
    const handleMouseUp = () => {
      setIsDragging(false)
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
    
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }

  const updateValue = (clientX: number, trackElement: HTMLElement | null | undefined) => {
    if (!trackElement) return
    
    const rect = trackElement.getBoundingClientRect()
    const x = clientX - rect.left
    const percent = Math.max(0, Math.min(1, x / rect.width))
    const rawValue = min + percent * (max - min)
    const steppedValue = Math.round(rawValue / step) * step
    const clampedValue = Math.max(min, Math.min(max, steppedValue))
    
    onValueChange([clampedValue])
  }

  return (
    <div className={cn('relative w-full h-6 flex items-center', className, disabled && 'opacity-50 cursor-not-allowed')}>
      {/* Track */}
      <div 
        className="absolute w-full h-1.5 bg-surface rounded-full cursor-pointer"
        onMouseDown={handleMouseDown}
      >
        {/* Filled portion */}
        <div 
          className="absolute h-full bg-primary rounded-full"
          style={{ width: `${percentage}%` }}
        />
      </div>

      {/* Thumb */}
      <div
        className={cn(
          'absolute w-4 h-4 bg-white rounded-full shadow-md cursor-grab active:cursor-grabbing transition-transform',
          isDragging && 'scale-110'
        )}
        style={{ left: `calc(${percentage}% - 8px)` }}
        onMouseDown={(e) => {
          if (disabled) return
          e.stopPropagation()
          setIsDragging(true)
          
          const trackElement = e.currentTarget.parentElement?.parentElement ?? null
          const handleMouseMove = (moveEvent: MouseEvent) => {
            updateValue(moveEvent.clientX, trackElement)
          }
          
          const handleMouseUp = () => {
            setIsDragging(false)
            document.removeEventListener('mousemove', handleMouseMove)
            document.removeEventListener('mouseup', handleMouseUp)
          }
          
          document.addEventListener('mousemove', handleMouseMove)
          document.addEventListener('mouseup', handleMouseUp)
        }}
      />
    </div>
  )
}