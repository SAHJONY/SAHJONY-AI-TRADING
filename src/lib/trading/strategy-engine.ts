// Strategy Engine — manages trading strategies with indicators and conditions
import { createClient } from '@/lib/supabase/server'
import type {
  TradingStrategy, Indicator, StrategyConditions, Condition,
  StrategyMetrics, StrategyStatus, AssetType
} from '@/types/trading'
import { marketDataService } from './market-data'

export class StrategyEngine {
  async getStrategies(userId: string): Promise<TradingStrategy[]> {
    const supabase = await createClient()
    const { data, error } = await supabase
      .from('trading_strategies')
      .select('*')
      .eq('user_id', userId)
      .order('updated_at', { ascending: false })

    if (error) throw error
    return (data || []).map(this.mapStrategy)
  }

  async getStrategy(id: string, userId: string): Promise<TradingStrategy | null> {
    const supabase = await createClient()
    const { data, error } = await supabase
      .from('trading_strategies')
      .select('*')
      .eq('id', id)
      .eq('user_id', userId)
      .single()

    if (error || !data) return null
    return this.mapStrategy(data)
  }

  async createStrategy(
    userId: string,
    name: string,
    description: string,
    assetTypes: AssetType[],
    indicators: Indicator[],
    conditions: StrategyConditions,
    code?: string
  ): Promise<TradingStrategy> {
    const supabase = await createClient()
    const { data, error } = await supabase
      .from('trading_strategies')
      .insert({
        user_id: userId,
        name,
        description,
        strategy_type: 'custom',
        asset_types: assetTypes,
        indicators: JSON.stringify(indicators),
        conditions: JSON.stringify(conditions),
        code: code || null,
        status: 'draft',
        performance_metrics: JSON.stringify({
          totalReturn: 0,
          maxDrawdown: 0,
          sharpeRatio: 0,
          winRate: 0,
          totalTrades: 0,
          profitableTrades: 0,
          avgWin: 0,
          avgLoss: 0,
        }),
      })
      .select()
      .single()

    if (error) throw error
    return this.mapStrategy(data)
  }

  async updateStrategy(
    id: string, userId: string,
    updates: Partial<Pick<TradingStrategy, 'name' | 'description' | 'assetTypes' | 'indicators' | 'conditions' | 'code' | 'status'>>
  ): Promise<TradingStrategy> {
    const supabase = await createClient()
    const dbUpdates: Record<string, unknown> = {}
    if (updates.name) dbUpdates.name = updates.name
    if (updates.description !== undefined) dbUpdates.description = updates.description
    if (updates.assetTypes) dbUpdates.asset_types = updates.assetTypes
    if (updates.indicators) dbUpdates.indicators = JSON.stringify(updates.indicators)
    if (updates.conditions) dbUpdates.conditions = JSON.stringify(updates.conditions)
    if (updates.code !== undefined) dbUpdates.code = updates.code
    if (updates.status) dbUpdates.status = updates.status

    const { data, error } = await supabase
      .from('trading_strategies')
      .update(dbUpdates)
      .eq('id', id)
      .eq('user_id', userId)
      .select()
      .single()

    if (error) throw error
    return this.mapStrategy(data)
  }

  async deleteStrategy(id: string, userId: string): Promise<void> {
    const supabase = await createClient()
    const { error } = await supabase
      .from('trading_strategies')
      .delete()
      .eq('id', id)
      .eq('user_id', userId)

    if (error) throw error
  }

  // Compute indicator values for a set of bars, returning current and previous values
  computeIndicatorValues(
    indicators: Indicator[],
    bars: { open: number; high: number; low: number; close: number; volume: number }[]
  ): { current: Record<string, number>; previous: Record<string, number> } {
    const computeForBars = (barArray: typeof bars): Record<string, number> => {
      const closes = barArray.map(b => b.close)
      const results: Record<string, number> = {}

      for (const indicator of indicators) {
        switch (indicator.type) {
          case 'sma': {
            const period = (indicator.params.period as number) || 20
            const sma = closes.slice(-period).reduce((a, b) => a + b, 0) / period
            results[indicator.id] = sma
            break
          }
          case 'ema': {
            const period = (indicator.params.period as number) || 20
            const multiplier = 2 / (period + 1)
            let ema = closes.slice(0, period).reduce((a, b) => a + b, 0) / period
            for (let i = period; i < closes.length; i++) {
              ema = (closes[i] - ema) * multiplier + ema
            }
            results[indicator.id] = ema
            break
          }
          case 'rsi': {
            const period = (indicator.params.period as number) || 14
            const deltas = closes.slice(1).map((c, i) => c - closes[i])
            const gains = deltas.map(d => d > 0 ? d : 0)
            const losses = deltas.map(d => d < 0 ? -d : 0)
            const avgGain = gains.slice(-period).reduce((a, b) => a + b, 0) / period
            const avgLoss = losses.slice(-period).reduce((a, b) => a + b, 0) / period
            if (avgLoss === 0) {
              results[indicator.id] = 100
            } else {
              const rs = avgGain / avgLoss
              results[indicator.id] = 100 - (100 / (1 + rs))
            }
            break
          }
          case 'macd': {
            const fastPeriod = 12, slowPeriod = 26
            const getEMA = (data: number[], p: number) => {
              const m = 2 / (p + 1)
              let ema = data.slice(0, p).reduce((a, b) => a + b, 0) / p
              for (let i = p; i < data.length; i++) ema = (data[i] - ema) * m + ema
              return ema
            }
            results[indicator.id] = getEMA(closes, fastPeriod) - getEMA(closes, slowPeriod)
            break
          }
          case 'bb': {
            const period = (indicator.params.period as number) || 20
            const sma = closes.slice(-period).reduce((a, b) => a + b, 0) / period
            const variance = closes.slice(-period).reduce((a, b) => a + (b - sma) ** 2, 0) / period
            results[indicator.id] = sma + 2 * Math.sqrt(variance)
            break
          }
          case 'volume': {
            const volumes = barArray.map(b => b.volume)
            results[indicator.id] = volumes.slice(-10).reduce((a, b) => a + b, 0) / 10
            break
          }
        }
      }
      return results
    }

    const current = computeForBars(bars)
    const previous = computeForBars(bars.slice(0, -1))
    return { current, previous }
  }

  // Evaluate a set of conditions against indicator values
  evaluateConditions(
    conditions: Condition[],
    currentIndicators: Record<string, number>,
    previousIndicators: Record<string, number>
  ): { met: number; total: number } {
    let met = 0
    let total = 0

    for (const condition of conditions) {
      const currentValue = currentIndicators[condition.indicator]
      const previousValue = previousIndicators[condition.indicator]
      if (currentValue === undefined) continue
      total++

      let satisfied = false
      switch (condition.operator) {
        case 'gt': satisfied = currentValue > condition.value; break
        case 'lt': satisfied = currentValue < condition.value; break
        case 'gte': satisfied = currentValue >= condition.value; break
        case 'lte': satisfied = currentValue <= condition.value; break
        case 'eq': satisfied = Math.abs(currentValue - condition.value) < 0.01; break
        case 'cross_above':
          satisfied = previousValue !== undefined
            ? previousValue <= condition.value && currentValue > condition.value
            : currentValue > condition.value
          break
        case 'cross_below':
          satisfied = previousValue !== undefined
            ? previousValue >= condition.value && currentValue < condition.value
            : currentValue < condition.value
          break
      }
      if (satisfied) met++
    }

    return { met, total }
  }

  // Signal generation — evaluate strategy conditions against current market data
  async generateSignal(strategy: TradingStrategy, symbol: string, assetType: AssetType): Promise<{
    signal: 'buy' | 'sell' | 'hold'
    confidence: number
    reason: string
  }> {
    try {
      const bars = await marketDataService.getHistoricalBars(symbol, assetType, '1d', 55)
      if (bars.length < 50) return { signal: 'hold', confidence: 0, reason: 'Insufficient data' }

      const { current, previous } = this.computeIndicatorValues(strategy.indicators, bars)

      const entryResult = this.evaluateConditions(strategy.conditions.entry, current, previous)
      const exitResult = this.evaluateConditions(strategy.conditions.exit, current, previous)

      const entryConfidence = entryResult.total > 0 ? entryResult.met / entryResult.total : 0
      const exitConfidence = exitResult.total > 0 ? exitResult.met / exitResult.total : 0

      if (entryConfidence > 0.6 && entryConfidence > exitConfidence) {
        return {
          signal: 'buy',
          confidence: entryConfidence,
          reason: `${Math.round(entryConfidence * 100)}% of entry conditions met`,
        }
      } else if (exitConfidence > 0.6) {
        return {
          signal: 'sell',
          confidence: exitConfidence,
          reason: `${Math.round(exitConfidence * 100)}% of exit conditions met`,
        }
      }

      return { signal: 'hold', confidence: 0.5, reason: 'No strong signal' }
    } catch {
      return { signal: 'hold', confidence: 0, reason: 'Signal generation failed' }
    }
  }

  private mapStrategy(row: Record<string, unknown>): TradingStrategy {
    return {
      id: row.id as string,
      userId: row.user_id as string,
      name: row.name as string,
      description: row.description as string | null,
      strategyType: row.strategy_type as string,
      assetTypes: row.asset_types as AssetType[],
      indicators: (typeof row.indicators === 'string' ? JSON.parse(row.indicators as string) : row.indicators) as Indicator[],
      conditions: (typeof row.conditions === 'string' ? JSON.parse(row.conditions as string) : row.conditions) as StrategyConditions,
      code: row.code as string | null,
      status: row.status as StrategyStatus,
      performanceMetrics: (typeof row.performance_metrics === 'string' ? JSON.parse(row.performance_metrics as string) : row.performance_metrics) as StrategyMetrics,
      createdAt: row.created_at as string,
      updatedAt: row.updated_at as string,
    }
  }
}

export const strategyEngine = new StrategyEngine()
