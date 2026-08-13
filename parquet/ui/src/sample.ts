import type { AgentScore, ParquetSnapshot } from './types'

const identities = [
  ['Citadel Systematic','CITADEL','MACD / trend'],['Two Sigma Backtest','2SIGMA','expectancy / Sharpe'],
  ['Bridgewater Risk','BRIDGE','volatility / risk parity'],['Renaissance Patterns','REN PAT','mean reversion / z-score'],
  ['Goldman Technical','GS TECH','RSI / MACD'],['JPMorgan Fundamental','JPM FUND','valuation / trend'],
  ['D.E. Shaw Options','DESHAW','IV rank / premium'],['AQR Factor','AQR','momentum / quality'],
  ['Citadel Securities MM','CIT MM','order-flow toxicity'],['Millennium Pod','MLN POD','residual alpha'],
  ['Renaissance Medallion','MEDALLION','regime / cointegration'],['Sovereign Wealth','SWF','secular macro'],
]
export const agents: AgentScore[] = identities.map(([name,shortName,focus], i) => ({
  name, shortName, focus, score: Math.sin(i * 1.7) * .72, confidence: .52 + (i % 4) * .1,
  rationale: `${focus}: deterministic estimator supports a ${i % 3 === 0 ? 'defensive' : 'measured'} posture.`,
  alphaContribution: (i % 2 ? -1 : 1) * (i + 1) * .03, profitable: 8 + i, losing: 4 + (i % 5),
}))

export const fallbackSnapshot: ParquetSnapshot = {
  schemaVersion: 1, desk: 'live', cycle: 914, ts: new Date().toISOString(), mode: 'LIVE', broker: 'robinhood_crypto',
  account: { equity: 49.89, equityStart: 50, cash: 44.66, deployed: 5.23, nav: .9978 },
  pnl: { returnPct: -.22, realized: 0, benchmarkPct: -.97, alphaPct: .75 },
  health: { marketOpen: true, brokerOnline: true, liveArmed: true, halted: false, haltReason: '', dataIntegrity: 94, reconciliation: 'RECONCILED' },
  brain: { posture: 'neutral', globalRiskMultiplier: .52, commentary: 'Mixed momentum with elevated dispersion. Maintain small sizing while the council waits for cross-agent confirmation.', model: 'deterministic fallback', used: false },
  council: ['BTC/USD','ETH/USD','DOGE/USD','BCH/USD','ETC/USD'].map((symbol, row) => ({ symbol, price: [63740,1891,.07,215,6.28][row], conviction: .48 + row * .03, direction: row % 2 ? 'long' : 'flat', agents: agents.map((a,i) => ({...a, score: Math.max(-1,Math.min(1,a.score + Math.sin(row+i)*.16))})) })),
  positions: [
    {symbol:'BTC/USD',strategy:'ladder',shares:.000015,price:63740,marketValue:.96,unrealized:-.03},
    {symbol:'ETH/USD',strategy:'ladder',shares:.000531,price:1891,marketValue:1,unrealized:-.02},
    {symbol:'DOGE/USD',strategy:'ladder',shares:10,price:.07,marketValue:.70,unrealized:.01},
  ], blotter: [],
  equityCurve: Array.from({length:32},(_,i)=>({cycle:883+i,nav:100+Math.sin(i/4)*.32-i*.006,benchmark:100+Math.sin(i/5)*.65-i*.026,expected:100+i*.018})),
  allocation: [{name:'Cash',value:44.66,color:'#6b7280'},{name:'Crypto',value:5.23,color:'#00ff88'}], attribution: agents,
  drift: {actualSharpe:.18,expectedSharpe:.42,deviation:-.24,alert:true,observations:914},
  incubation: {active:true,deployedCapital:50,capitalCeiling:100,positiveSharpeCycles:23,requiredCycles:100,scaleEligible:false}, traces: {},
}
