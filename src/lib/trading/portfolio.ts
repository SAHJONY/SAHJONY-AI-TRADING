// Portfolio Service — manages trading portfolios, holdings, and orders
import { createClient } from '@/lib/supabase/server'
import type {
  TradingPortfolio, Holding, PortfolioSummary, AssetAllocation,
  TradingOrder, CreateOrderInput, AssetType
} from '@/types/trading'
import { marketDataService } from './market-data'

export class PortfolioService {
  async getPortfolios(userId: string): Promise<TradingPortfolio[]> {
    const supabase = await createClient()
    const { data, error } = await supabase
      .from('trading_portfolios')
      .select('*')
      .eq('user_id', userId)
      .order('updated_at', { ascending: false })

    if (error) throw error
    return (data || []).map(this.mapPortfolio)
  }

  async getPortfolio(portfolioId: string, userId: string): Promise<PortfolioSummary | null> {
    const supabase = await createClient()
    const { data: portfolio, error: pError } = await supabase
      .from('trading_portfolios')
      .select('*')
      .eq('id', portfolioId)
      .eq('user_id', userId)
      .single()

    if (pError || !portfolio) return null

    const { data: holdings, error: hError } = await supabase
      .from('trading_holdings')
      .select('*')
      .eq('portfolio_id', portfolioId)
      .eq('user_id', userId)

    if (hError) throw hError

    const mappedPortfolio = this.mapPortfolio(portfolio)
    const mappedHoldings = (holdings || []).map(this.mapHolding)

    // Calculate totals with live prices
    let holdingsValue = 0
    const holdingsWithLivePrices = await Promise.all(
      mappedHoldings.map(async (h) => {
        try {
          const quote = await marketDataService.getQuote(h.symbol, h.assetType)
          if (quote) {
            h.currentPrice = quote.price
            return { holding: h, value: h.quantity * quote.price, price: quote.price }
          }
          return { holding: h, value: h.quantity * (h.averagePrice || 0), price: h.averagePrice }
        } catch {
          return { holding: h, value: h.quantity * h.averagePrice, price: h.averagePrice }
        }
      })
    )

    for (const item of holdingsWithLivePrices) {
      holdingsValue += item.value
    }

    const totalValue = mappedPortfolio.currentBalance + holdingsValue
    const totalPL = totalValue - mappedPortfolio.initialBalance
    const totalPLPct = (totalPL / mappedPortfolio.initialBalance) * 100

    // Asset allocation
    const allocations: Record<AssetType, number> = { stock: 0, crypto: 0, forex: 0 }
    for (const item of holdingsWithLivePrices) {
      allocations[item.holding.assetType] += item.value
    }

    const assetAllocation: AssetAllocation[] = (Object.entries(allocations) as [AssetType, number][])
      .filter(([, v]) => v > 0)
      .map(([assetType, value]) => ({
        assetType,
        value,
        percentage: totalValue > 0 ? (value / totalValue) * 100 : 0,
      }))
      .sort((a, b) => b.percentage - a.percentage)

    return {
      portfolio: mappedPortfolio,
      holdings: holdingsWithLivePrices.map(h => h.holding),
      totalValue,
      totalPL,
      totalPLPct,
      assetAllocation,
    }
  }

  async createPortfolio(userId: string, name: string, initialBalance: number = 10000, isPaper: boolean = true): Promise<TradingPortfolio> {
    const supabase = await createClient()
    const { data, error } = await supabase
      .from('trading_portfolios')
      .insert({
        user_id: userId,
        name,
        initial_balance: initialBalance,
        current_balance: initialBalance,
        is_paper: isPaper,
        currency: 'USD',
      })
      .select()
      .single()

    if (error) throw error
    return this.mapPortfolio(data)
  }

  async deletePortfolio(portfolioId: string, userId: string): Promise<void> {
    const supabase = await createClient()
    const { error } = await supabase
      .from('trading_portfolios')
      .delete()
      .eq('id', portfolioId)
      .eq('user_id', userId)

    if (error) throw error
  }

  async placeOrder(userId: string, input: CreateOrderInput): Promise<TradingOrder> {
    const supabase = await createClient()
    const quote = await marketDataService.getQuote(input.symbol, input.assetType)
    const execPrice = input.orderType === 'market' ? (quote?.price || 0) : (input.price || 0)
    const totalValue = execPrice * input.quantity

    const { data, error } = await supabase
      .from('trading_orders')
      .insert({
        user_id: userId,
        portfolio_id: input.portfolioId,
        symbol: input.symbol,
        asset_type: input.assetType,
        order_type: input.orderType,
        side: input.side,
        quantity: input.quantity,
        price: input.price || null,
        stop_price: input.stopPrice || null,
        limit_price: input.limitPrice || null,
        status: input.orderType === 'market' ? 'filled' : 'pending',
        filled_quantity: input.orderType === 'market' ? input.quantity : 0,
        filled_price: input.orderType === 'market' ? execPrice : null,
        total_value: input.orderType === 'market' ? totalValue : null,
        executed_at: input.orderType === 'market' ? new Date().toISOString() : null,
        notes: input.notes || null,
      })
      .select()
      .single()

    if (error) throw error

    // If market order, update portfolio and holdings
    if (input.orderType === 'market') {
      await this.updatePortfolioAfterTrade(userId, input.portfolioId, input.symbol, input.assetType, input.side, input.quantity, execPrice)
    }

    return this.mapOrder(data)
  }

  async getOrders(userId: string, portfolioId?: string): Promise<TradingOrder[]> {
    const supabase = await createClient()
    let query = supabase
      .from('trading_orders')
      .select('*')
      .eq('user_id', userId)
      .order('created_at', { ascending: false })
      .limit(50)

    if (portfolioId) {
      query = query.eq('portfolio_id', portfolioId)
    }

    const { data, error } = await query
    if (error) throw error
    return (data || []).map(this.mapOrder)
  }

  async cancelOrder(orderId: string, userId: string): Promise<void> {
    const supabase = await createClient()
    const { error } = await supabase
      .from('trading_orders')
      .update({ status: 'cancelled' })
      .eq('id', orderId)
      .eq('user_id', userId)
      .eq('status', 'pending')

    if (error) throw error
  }

  private async updatePortfolioAfterTrade(
    userId: string, portfolioId: string, symbol: string, assetType: AssetType,
    side: 'buy' | 'sell', quantity: number, price: number
  ) {
    const supabase = await createClient()
    const totalCost = price * quantity

    // Update portfolio balance
    const { data: portfolio } = await supabase
      .from('trading_portfolios')
      .select('current_balance')
      .eq('id', portfolioId)
      .eq('user_id', userId)
      .single()

    if (!portfolio) throw new Error('Portfolio not found')

    const newBalance = side === 'buy'
      ? portfolio.current_balance - totalCost
      : portfolio.current_balance + totalCost

    await supabase
      .from('trading_portfolios')
      .update({ current_balance: newBalance })
      .eq('id', portfolioId)
      .eq('user_id', userId)

    // Update holdings
    const { data: existing } = await supabase
      .from('trading_holdings')
      .select('*')
      .eq('portfolio_id', portfolioId)
      .eq('symbol', symbol)
      .maybeSingle()

    if (existing) {
      const newQuantity = side === 'buy'
        ? existing.quantity + quantity
        : existing.quantity - quantity

      const newAvgPrice = side === 'buy'
        ? ((existing.average_price * existing.quantity) + (price * quantity)) / newQuantity
        : existing.average_price

      if (newQuantity <= 0.00000001) {
        await supabase.from('trading_holdings').delete().eq('id', existing.id)
      } else {
        await supabase
          .from('trading_holdings')
          .update({ quantity: newQuantity, average_price: newAvgPrice, current_price: price })
          .eq('id', existing.id)
      }
    } else if (side === 'buy') {
      await supabase.from('trading_holdings').insert({
        portfolio_id: portfolioId,
        user_id: userId,
        symbol,
        asset_type: assetType,
        quantity,
        average_price: price,
        current_price: price,
        last_updated: new Date().toISOString(),
      })
    }
  }

  // Mappers
  private mapPortfolio(row: Record<string, unknown>): TradingPortfolio {
    return {
      id: row.id as string,
      userId: row.user_id as string,
      name: row.name as string,
      description: row.description as string | null,
      initialBalance: row.initial_balance as number,
      currentBalance: row.current_balance as number,
      currency: row.currency as string,
      isPaper: row.is_paper as boolean,
      createdAt: row.created_at as string,
      updatedAt: row.updated_at as string,
    }
  }

  private mapHolding(row: Record<string, unknown>): Holding {
    return {
      id: row.id as string,
      portfolioId: row.portfolio_id as string,
      userId: row.user_id as string,
      symbol: row.symbol as string,
      assetType: row.asset_type as AssetType,
      quantity: row.quantity as number,
      averagePrice: row.average_price as number,
      currentPrice: row.current_price as number | null,
      lastUpdated: row.last_updated as string | null,
      createdAt: row.created_at as string,
      updatedAt: row.updated_at as string,
    }
  }

  private mapOrder(row: Record<string, unknown>): TradingOrder {
    return {
      id: row.id as string,
      userId: row.user_id as string,
      portfolioId: row.portfolio_id as string,
      symbol: row.symbol as string,
      assetType: row.asset_type as AssetType,
      orderType: row.order_type as TradingOrder['orderType'],
      side: row.side as TradingOrder['side'],
      quantity: row.quantity as number,
      price: row.price as number | null,
      stopPrice: row.stop_price as number | null,
      limitPrice: row.limit_price as number | null,
      status: row.status as TradingOrder['status'],
      filledQuantity: row.filled_quantity as number,
      filledPrice: row.filled_price as number | null,
      totalValue: row.total_value as number | null,
      notes: row.notes as string | null,
      executedAt: row.executed_at as string | null,
      createdAt: row.created_at as string,
      updatedAt: row.updated_at as string,
    }
  }
}

export const portfolioService = new PortfolioService()
