'use client'

import React, { useEffect, useRef } from 'react'
import { cn } from '@/lib/utils'
import type { HistoricalBar } from '@/types/trading'

interface MarketChartProps {
  data: HistoricalBar[]
  width?: number
  height?: number
  color?: string
  showVolume?: boolean
  className?: string
}

export function MarketChart({
  data,
  width = 800,
  height = 400,
  color = '#6366f1',
  showVolume = true,
  className,
}: MarketChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || data.length < 2) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    canvas.width = width * dpr
    canvas.height = height * dpr
    ctx.scale(dpr, dpr)
    canvas.style.width = width + 'px'
    canvas.style.height = height + 'px'

    // Chart area
    const volumeHeight = showVolume ? height * 0.2 : 0
    const chartHeight = height - volumeHeight - 20
    const padding = { top: 20, right: 60, bottom: 20, left: 60 }
    const chartWidth = width - padding.left - padding.right

    // Find min/max
    let minPrice = Infinity, maxPrice = -Infinity
    let maxVolume = -Infinity
    for (const bar of data) {
      if (bar.low < minPrice) minPrice = bar.low
      if (bar.high > maxPrice) maxPrice = bar.high
      if (bar.volume > maxVolume) maxVolume = bar.volume
    }

    const priceRange = maxPrice - minPrice || 1
    const scaleY = (price: number) =>
      padding.top + chartHeight - ((price - minPrice) / priceRange) * chartHeight
    const scaleVolume = (v: number) =>
      height - padding.bottom - (v / maxVolume) * volumeHeight
    const scaleX = (i: number) =>
      padding.left + (i / (data.length - 1)) * chartWidth

    // Clear
    ctx.clearRect(0, 0, width, height)

    // Grid lines
    ctx.strokeStyle = 'rgba(255,255,255,0.05)'
    ctx.lineWidth = 0.5
    const gridLines = 6
    for (let i = 0; i <= gridLines; i++) {
      const y = padding.top + (chartHeight / gridLines) * i
      ctx.beginPath()
      ctx.moveTo(padding.left, y)
      ctx.lineTo(width - padding.right, y)
      ctx.stroke()

      const price = maxPrice - (priceRange / gridLines) * i
      ctx.fillStyle = '#71717a'
      ctx.font = '10px Inter, sans-serif'
      ctx.textAlign = 'right'
      ctx.fillText(price.toFixed(price > 1000 ? 0 : price > 1 ? 2 : 4), padding.left - 6, y + 3)
    }

    // Price line
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.beginPath()
    for (let i = 0; i < data.length; i++) {
      const x = scaleX(i)
      const y = scaleY(data[i].close)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    }
    ctx.stroke()

    // Gradient fill under line
    const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartHeight)
    gradient.addColorStop(0, color + '30')
    gradient.addColorStop(1, color + '00')
    ctx.fillStyle = gradient
    ctx.lineTo(scaleX(data.length - 1), padding.top + chartHeight)
    ctx.lineTo(padding.left, padding.top + chartHeight)
    ctx.closePath()
    ctx.fill()

    // Candles (show every Nth candle)
    const candleSpacing = chartWidth / (data.length - 1)
    const maxCandles = 80
    const step = Math.max(1, Math.floor(data.length / maxCandles))
    const candleWidth = Math.max(1, Math.min(candleSpacing * 0.6, 8))

    for (let i = 0; i < data.length; i += step) {
      const bar = data[i]
      const x = scaleX(i)
      const isUp = bar.close >= bar.open
      const c = isUp ? '#22c55e' : '#ef4444'

      // Wick
      ctx.strokeStyle = c
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(x, scaleY(bar.high))
      ctx.lineTo(x, scaleY(bar.low))
      ctx.stroke()

      // Body
      ctx.fillStyle = isUp ? '#22c55e30' : '#ef444430'
      ctx.strokeStyle = c
      ctx.lineWidth = 1
      const bodyTop = scaleY(Math.max(bar.open, bar.close))
      const bodyBottom = scaleY(Math.min(bar.open, bar.close))
      const bodyHeight = Math.max(1, bodyBottom - bodyTop)
      ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight)
      ctx.strokeRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight)
    }

    // Volume bars
    if (showVolume && volumeHeight > 0) {
      for (let i = 0; i < data.length; i += step) {
        const bar = data[i]
        const x = scaleX(i)
        const isUp = bar.close >= bar.open
        ctx.fillStyle = isUp ? '#22c55e20' : '#ef444420'
        const volH = (bar.volume / maxVolume) * volumeHeight
        ctx.fillRect(x - candleWidth / 2, scaleVolume(bar.volume), candleWidth, volH)
      }
    }

    // Time labels
    ctx.fillStyle = '#71717a'
    ctx.font = '9px Inter, sans-serif'
    ctx.textAlign = 'center'
    const labelCount = Math.min(6, data.length)
    for (let i = 0; i < labelCount; i++) {
      const idx = Math.floor((i / (labelCount - 1)) * (data.length - 1))
      const date = new Date(data[idx].timestamp)
      const label = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
      ctx.fillText(label, scaleX(idx), height - 4)
    }
  }, [data, width, height, color, showVolume])

  return (
    <canvas
      ref={canvasRef}
      className={cn('rounded-lg', className)}
      style={{ width: '100%', height: 'auto' }}
    />
  )
}
