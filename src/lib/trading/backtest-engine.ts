// Backtest Engine — runs strategy backtests against historical data
import { createClient } from '@/lib/supabase/server'
import type {
  TradingBacktest, BacktestResults, BacktestTrade,
  TradingStrategy, AssetType, OrderSide
} from '@/types/trading'
import { marketDataService } from './market-data'
import { strategyEngine } from './strategy-engine'

export class BacktestEngine {
  async getBacktests(userId: string): Promise<TradingBacktest[]> {
    const supabase = await createClient()
    const { data, error } = await supabase
      .from('trading_backtests')
      .select('*')
      .eq('user_id', userId)
      .order('created_at', { ascending: false })

    if (error) throw error
    return (data || []).map(this.mapBacktest)
  }

  async runBacktest(
    userId: string,
    strategyId: string,
    name: string,
    symbol: string,
    assetType: AssetType,
    timeframe: string,
    startDate: string,
    endDate: string,
    initialCapital: number
  ): Promise<TradingBacktest> {
    const supabase = await createClient()

    // Get strategy
    const strategy = await strategyEngine.getStrategy(strategyId, userId)
    if (!strategy) throw new Error('Strategy not found')

    // Create backtest record
    const { data: backtest, error } = await supabase
      .from('trading_backtests')
      .insert({
        user_id: userId,
        strategy_id: strategyId,
        name,
        symbol,
        asset_type: assetType,
        timeframe,
        start_date: startDate,
        end_date: endDate,
        initial_capital: initialCapital,
        status: 'running',
      })
      .select()
      .single()

    if (error) throw error

    try {
      // Get historical data
      const bars = await marketDataService.getHistoricalBars(symbol, assetType, timeframe, 200)
      if (bars.length < 50) {
        await this.failBacktest(backtest.id, userId, 'Insufficient historical data')
        return this.mapBacktest({ ...backtest, status: 'failed' })
      }

      // Filter by date range
      const startTs = new Date(startDate).getTime()
      const endTs = new Date(endDate).getTime()
      const filteredBars = bars.filter(b => {
        const t = new Date(b.timestamp).getTime()
        return t >= startTs && t <= endTs
      })

      if (filteredBars.length < 20) {
        await this.failBacktest(backtest.id, userId, 'Insufficient data in date range')
        return this.mapBacktest({ ...backtest, status: 'failed' })
      }

      // Run simulation
      const result = this.simulate(strategy, filteredBars, initialCapital)

      // Update backtest with results
      const { data: updated } = await supabase
        .from('trading_backtests')
        .update({
          status: 'completed',
          final_capital: result.finalCapital,
          total_return: result.totalReturn,
          max_drawdown: result.maxDrawdown,
          sharpe_ratio: result.sharpeRatio,
          win_rate: result.winRate,
          total_trades: result.totalTrades,
          profitable_trades: result.profitableTrades,
          losing_trades: result.losingTrades,
          avg_win: result.avgWin,
          avg_loss: result.avgLoss,
          results_json: JSON.stringify(result.results),
        })
        .eq('id', backtest.id)
        .eq('user_id', userId)
        .select()
        .single()

      return this.mapBacktest(updated || backtest)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      await this.failBacktest(backtest.id, userId, message)
      return this.mapBacktest({ ...backtest, status: 'failed' })
    }
  }

  private simulate(strategy: TradingStrategy, bars: { timestamp: string; open: number; high: number; low: number; close: number; volume: number }[], initialCapital: number) {
    let capital = initialCapital
    let position = 0
    let entryPrice = 0
    const trades: BacktestTrade[] = []
    const equityCurve: { timestamp: string; value: number }[] = [{ timestamp: bars[0].timestamp, value: initialCapital }]
    let maxCapital = initialCapital
    let maxDrawdown = 0

    const minWindow = 50
    const hasCustomIndicator = strategy.indicators && strategy.indicators.length > 0
    const hasCustomEntry = strategy.conditions?.entry && strategy.conditions.entry.length > 0
    const hasCustomExit = strategy.conditions?.exit && strategy.conditions.exit.length > 0
    const hasCustomConditions = (hasCustomIndicator && (hasCustomEntry || hasCustomExit))

    for (let i = minWindow; i < bars.length; i++) {
      const windowBars = bars.slice(i - minWindow, i + 1)
      const currentBar = bars[i]

      let entrySignal = false
      let exitSignal = false

      if (hasCustomConditions) {
        // Use strategy's actual indicators and conditions
        const { current, previous } = strategyEngine.computeIndicatorValues(strategy.indicators, windowBars)
        const entryResult = strategyEngine.evaluateConditions(strategy.conditions.entry, current, previous)
        const exitResult = strategyEngine.evaluateConditions(strategy.conditions.exit, current, previous)

        entrySignal = position === 0 && entryResult.total > 0 && (entryResult.met / entryResult.total) > 0.6
        exitSignal = position > 0 && exitResult.total > 0 && (exitResult.met / exitResult.total) > 0.6
      } else {
        // Fallback: use default SMA 20/50 crossover
        const closes = windowBars.map(b => b.close)
        const sma20 = closes.slice(-20).reduce((a, b) => a + b, 0) / 20
        const sma50 = closes.reduce((a, b) => a + b, 0) / 50

        const prevCloses = windowBars.slice(0, -1).map(b => b.close)
        const prevSMA20 = prevCloses.slice(-20).reduce((a, b) => a + b, 0) / 20
        const prevSMA50 = prevCloses.reduce((a, b) => a + b, 0) / 50

        entrySignal = position === 0 && prevSMA20 <= prevSMA50 && sma20 > sma50
        exitSignal = position > 0 && prevSMA20 >= prevSMA50 && sma20 < sma50
      }

      if (entrySignal) {
        position = capital / currentBar.close
        entryPrice = currentBar.close
        capital = 0
      } else if (exitSignal) {
        const exitPrice = currentBar.close
        const pnl = position * (exitPrice - entryPrice)
        const pnlPct = ((exitPrice - entryPrice) / entryPrice) * 100

        trades.push({
          entryDate: bars[i - 1].timestamp,
          exitDate: currentBar.timestamp,
          side: 'buy',
          entryPrice,
          exitPrice,
          quantity: position,
          pnl,
          pnlPct,
        })

        capital = position * exitPrice
        position = 0
      }

      const equity = position > 0 ? position * currentBar.close : capital
      equityCurve.push({ timestamp: currentBar.timestamp, value: equity })

      if (equity > maxCapital) maxCapital = equity
      const drawdown = (maxCapital - equity) / maxCapital * 100
      if (drawdown > maxDrawdown) maxDrawdown = drawdown
    }

    // Close any open position
    if (position > 0) {
      const lastBar = bars[bars.length - 1]
      const exitPrice = lastBar.close
      const pnl = position * (exitPrice - entryPrice)
      const pnlPct = ((exitPrice - entryPrice) / entryPrice) * 100
      trades.push({
        entryDate: bars[bars.length - 2].timestamp,
        exitDate: lastBar.timestamp,
        side: 'buy',
        entryPrice,
        exitPrice,
        quantity: position,
        pnl,
        pnlPct,
      })
      capital = position * exitPrice
      position = 0
    }

    const finalCapital = capital + (position > 0 ? position * bars[bars.length - 1].close : 0)
    const totalReturn = ((finalCapital - initialCapital) / initialCapital) * 100

    // Calculate metrics
    const winningTrades = trades.filter(t => t.pnl > 0)
    const losingTrades = trades.filter(t => t.pnl < 0)
    const winRate = trades.length > 0 ? (winningTrades.length / trades.length) * 100 : 0

    const avgWin = winningTrades.length > 0
      ? winningTrades.reduce((sum, t) => sum + t.pnl, 0) / winningTrades.length
      : 0
    const avgLoss = losingTrades.length > 0
      ? Math.abs(losingTrades.reduce((sum, t) => sum + t.pnl, 0) / losingTrades.length)
      : 0

    // Sharpe ratio (simplified)
    const returns: number[] = []
    for (let i = 1; i < equityCurve.length; i++) {
      returns.push((equityCurve[i].value - equityCurve[i - 1].value) / equityCurve[i - 1].value)
    }
    const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length
    const stdReturn = Math.sqrt(returns.reduce((a, b) => a + (b - avgReturn) ** 2, 0) / returns.length)
    const sharpeRatio = stdReturn > 0 ? (avgReturn / stdReturn) * Math.sqrt(252) : 0

    return {
      finalCapital,
      totalReturn,
      maxDrawdown,
      sharpeRatio,
      winRate,
      totalTrades: trades.length,
      profitableTrades: winningTrades.length,
      losingTrades: losingTrades.length,
      avgWin,
      avgLoss,
      results: {
        equityCurve,
        trades,
        drawdowns: [],
        monthlyReturns: [],
      } as BacktestResults,
    }
  }

  private async failBacktest(id: string, userId: string, error: string): Promise<void> {
    const supabase = await createClient()
    await supabase
      .from('trading_backtests')
      .update({ status: 'failed', results_json: JSON.stringify({ error }) })
      .eq('id', id)
      .eq('user_id', userId)
  }

  async deleteBacktest(id: string, userId: string): Promise<void> {
    const supabase = await createClient()
    const { error } = await supabase
      .from('trading_backtests')
      .delete()
      .eq('id', id)
      .eq('user_id', userId)

    if (error) throw error
  }

  private mapBacktest(row: Record<string, unknown>): TradingBacktest {
    return {
      id: row.id as string,
      userId: row.user_id as string,
      strategyId: row.strategy_id as string | null,
      name: row.name as string,
      symbol: row.symbol as string,
      assetType: row.asset_type as AssetType,
      timeframe: row.timeframe as string,
      startDate: row.start_date as string,
      endDate: row.end_date as string,
      initialCapital: row.initial_capital as number,
      finalCapital: row.final_capital as number | null,
      totalReturn: row.total_return as number | null,
      maxDrawdown: row.max_drawdown as number | null,
      sharpeRatio: row.sharpe_ratio as number | null,
      winRate: row.win_rate as number | null,
      totalTrades: row.total_trades as number | null,
      profitableTrades: row.profitable_trades as number | null,
      losingTrades: row.losing_trades as number | null,
      avgWin: row.avg_win as number | null,
      avgLoss: row.avg_loss as number | null,
      resultsJson: (typeof row.results_json === 'string' ? JSON.parse(row.results_json as string) : row.results_json) as BacktestResults,
      status: row.status as TradingBacktest['status'],
      createdAt: row.created_at as string,
      updatedAt: row.updated_at as string,
    }
  }
}

export const backtestEngine = new BacktestEngine()
