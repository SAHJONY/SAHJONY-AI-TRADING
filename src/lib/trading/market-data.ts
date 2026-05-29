// Market Data Service — handles live quotes, historical data, and news
import type { MarketQuote, HistoricalBar, MarketNewsItem, AssetType } from '@/types/trading'

// Simulated market data for demo/development purposes
// In production, replace with real API calls (Alpha Vantage, Polygon, CoinGecko, etc.)

const MOCK_STOCKS: Record<string, { name: string; basePrice: number; volatility: number }> = {
  AAPL: { name: 'Apple Inc.', basePrice: 185.50, volatility: 0.015 },
  GOOGL: { name: 'Alphabet Inc.', basePrice: 175.20, volatility: 0.018 },
  MSFT: { name: 'Microsoft Corp.', basePrice: 415.80, volatility: 0.012 },
  TSLA: { name: 'Tesla Inc.', basePrice: 245.30, volatility: 0.035 },
  AMZN: { name: 'Amazon.com Inc.', basePrice: 178.90, volatility: 0.02 },
  NVDA: { name: 'NVIDIA Corp.', basePrice: 880.40, volatility: 0.028 },
  META: { name: 'Meta Platforms Inc.', basePrice: 510.20, volatility: 0.022 },
  JPM: { name: 'JPMorgan Chase', basePrice: 195.30, volatility: 0.01 },
  SPY: { name: 'SPDR S&P 500 ETF', basePrice: 520.00, volatility: 0.008 },
  QQQ: { name: 'Invesco QQQ Trust', basePrice: 445.00, volatility: 0.012 },
}

const MOCK_CRYPTO: Record<string, { name: string; basePrice: number; volatility: number }> = {
  BTC: { name: 'Bitcoin', basePrice: 68200.00, volatility: 0.03 },
  ETH: { name: 'Ethereum', basePrice: 3450.00, volatility: 0.035 },
  SOL: { name: 'Solana', basePrice: 168.00, volatility: 0.045 },
  DOGE: { name: 'Dogecoin', basePrice: 0.15, volatility: 0.06 },
  ADA: { name: 'Cardano', basePrice: 0.48, volatility: 0.04 },
  AVAX: { name: 'Avalanche', basePrice: 38.50, volatility: 0.04 },
}

const MOCK_FOREX: Record<string, { name: string; basePrice: number; volatility: number }> = {
  'EUR/USD': { name: 'Euro / US Dollar', basePrice: 1.0850, volatility: 0.003 },
  'GBP/USD': { name: 'British Pound / US Dollar', basePrice: 1.2650, volatility: 0.004 },
  'USD/JPY': { name: 'US Dollar / Japanese Yen', basePrice: 151.50, volatility: 0.005 },
  'AUD/USD': { name: 'Australian Dollar / US Dollar', basePrice: 0.6580, volatility: 0.004 },
  'USD/CAD': { name: 'US Dollar / Canadian Dollar', basePrice: 1.3580, volatility: 0.003 },
  'EUR/GBP': { name: 'Euro / British Pound', basePrice: 0.8575, volatility: 0.003 },
}

function getMockAssetMap(assetType: AssetType) {
  switch (assetType) {
    case 'stock': return MOCK_STOCKS
    case 'crypto': return MOCK_CRYPTO
    case 'forex': return MOCK_FOREX
    default: return {}
  }
}

function seededRandom(seed: string): number {
  let hash = 0
  for (let i = 0; i < seed.length; i++) {
    hash = ((hash << 5) - hash) + seed.charCodeAt(i)
    hash |= 0
  }
  return Math.abs(hash) / 2147483647
}

function generatePrice(basePrice: number, volatility: number, symbol: string): number {
  const dateStr = new Date().toISOString().slice(0, 13)
  const rand = seededRandom(symbol + dateStr)
  const change = (rand - 0.5) * 2 * volatility * basePrice
  return parseFloat((basePrice + change).toFixed(4))
}

export class MarketDataService {
  async getQuote(symbol: string, assetType: AssetType): Promise<MarketQuote | null> {
    const assetMap = getMockAssetMap(assetType)
    const asset = assetMap[symbol]
    if (!asset) return null

    const price = generatePrice(asset.basePrice, asset.volatility, symbol)
    const change24h = price - asset.basePrice
    const changePct24h = (change24h / asset.basePrice) * 100

    const high24h = price * (1 + asset.volatility * 0.5)
    const low24h = price * (1 - asset.volatility * 0.5)
    const volume24h = assetType === 'crypto' ? price * 100000 : price * 10000

    return {
      symbol,
      assetType,
      name: asset.name,
      price: parseFloat(price.toFixed(assetType === 'forex' ? 4 : 2)),
      change24h: parseFloat(change24h.toFixed(4)),
      changePct24h: parseFloat(changePct24h.toFixed(2)),
      high24h: parseFloat(high24h.toFixed(4)),
      low24h: parseFloat(low24h.toFixed(4)),
      volume24h: parseFloat(volume24h.toFixed(2)),
      marketCap: assetType === 'crypto' ? price * 1000000000 : price * 10000000,
      currency: 'USD',
      exchange: assetType === 'stock' ? 'NASDAQ' : assetType === 'crypto' ? 'Crypto' : 'FX',
      fetchedAt: new Date().toISOString(),
    }
  }

  async getQuotes(symbols: string[], assetType: AssetType): Promise<MarketQuote[]> {
    const results = await Promise.all(
      symbols.map(s => this.getQuote(s, assetType))
    )
    return results.filter((q): q is MarketQuote => q !== null)
  }

  async getHistoricalBars(
    symbol: string,
    assetType: AssetType,
    timeframe: string,
    limit: number = 100
  ): Promise<HistoricalBar[]> {
    const assetMap = getMockAssetMap(assetType)
    const asset = assetMap[symbol]
    if (!asset) return []

    const timeframeMinutes: Record<string, number> = {
      '1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240, '1d': 1440, '1w': 10080, '1M': 43200,
    }
    const intervalMinutes = timeframeMinutes[timeframe] || 1440
    const bars: HistoricalBar[] = []
    let price = asset.basePrice * 0.8

    // Use a fixed seed per symbol so bars are deterministic across calls
    const baseSeed = symbol + '_historical'

    for (let i = limit; i >= 0; i--) {
      const ts = Date.now() - i * intervalMinutes * 60000
      const timestamp = new Date(ts).toISOString()
      const volatility = asset.volatility * 0.3
      const openSeed = baseSeed + '_open_' + i
      const closeSeed = baseSeed + '_close_' + i
      const volSeed = baseSeed + '_vol_' + i
      const change = (seededRandom(openSeed) - 0.5) * 2 * volatility * price
      const open = parseFloat((price + change).toFixed(4))
      const high = parseFloat((open * (1 + volatility * 0.5)).toFixed(4))
      const low = parseFloat((open * (1 - volatility * 0.5)).toFixed(4))
      const close = parseFloat((low + seededRandom(closeSeed) * (high - low)).toFixed(4))
      const volume = parseFloat((close * 10000 * (0.5 + seededRandom(volSeed))).toFixed(2))

      bars.push({ timestamp, open, high, low, close, volume })
      price = close
    }

    return bars
  }

  async getMarketNews(symbols?: string[]): Promise<MarketNewsItem[]> {
    const allSymbols = symbols && symbols.length > 0
      ? symbols
      : [...Object.keys(MOCK_STOCKS).slice(0, 4), ...Object.keys(MOCK_CRYPTO).slice(0, 3)]

    const headlines: Array<{ title: string; sentiment: 'positive' | 'negative' | 'neutral' }> = [
      { title: 'Market rally continues as tech earnings beat expectations', sentiment: 'positive' },
      { title: 'Fed signals potential rate cut in upcoming meeting', sentiment: 'positive' },
      { title: 'Crypto market sees renewed institutional interest', sentiment: 'positive' },
      { title: 'Trading volumes surge amid market volatility', sentiment: 'neutral' },
      { title: 'Regulatory concerns weigh on tech sector', sentiment: 'negative' },
      { title: 'Global markets mixed as investors assess economic data', sentiment: 'neutral' },
      { title: 'AI sector stocks outperform broader market', sentiment: 'positive' },
      { title: 'Oil prices drop on demand concerns', sentiment: 'negative' },
      { title: 'Strong jobs data boosts market confidence', sentiment: 'positive' },
      { title: 'Inflation data comes in below expectations', sentiment: 'positive' },
      { title: 'Supply chain issues persist in semiconductor industry', sentiment: 'negative' },
      { title: 'New ETF filings signal growing institutional crypto adoption', sentiment: 'positive' },
    ]

    return headlines.slice(0, Math.min(headlines.length, allSymbols.length + 4)).map((h, i) => {
      const relevantSymbols = allSymbols.length > 0
        ? [allSymbols[i % allSymbols.length], ...(i < allSymbols.length - 1 ? [allSymbols[(i + 1) % allSymbols.length]] : [])]
        : ['AAPL']
      const sentimentRand = seededRandom(`news_sentiment_${i}`)
      return {
        id: `news-${i}-${Date.now()}`,
        title: h.title,
        summary: `Latest market update regarding ${h.title.toLowerCase()}. Market participants are closely watching developments.`,
        url: '#',
        source: ['Bloomberg', 'Reuters', 'CNBC', 'CoinDesk', 'WSJ'][i % 5],
        publishedAt: new Date(Date.now() - i * 3600000).toISOString(),
        sentiment: h.sentiment,
        sentimentScore: h.sentiment === 'positive' ? 0.6 + sentimentRand * 0.35 : h.sentiment === 'negative' ? 0.1 + sentimentRand * 0.25 : 0.35 + sentimentRand * 0.3,
        symbols: relevantSymbols,
        assetType: i < 5 ? 'stock' : 'crypto',
      }
    })
  }

  async searchSymbols(query: string, assetType?: AssetType): Promise<{ symbol: string; name: string; assetType: AssetType }[]> {
    const results: { symbol: string; name: string; assetType: AssetType }[] = []
    const q = query.toUpperCase()

    const searchAssets = assetType ? [assetType] : (['stock', 'crypto', 'forex'] as AssetType[])

    for (const at of searchAssets) {
      const assetMap = getMockAssetMap(at)
      for (const [symbol, info] of Object.entries(assetMap)) {
        if (symbol.includes(q) || info.name.toUpperCase().includes(q)) {
          results.push({ symbol, name: info.name, assetType: at })
        }
      }
    }

    return results.slice(0, 20)
  }
}

export const marketDataService = new MarketDataService()
