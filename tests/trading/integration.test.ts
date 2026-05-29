/**
 * Layer 1 Integration Client Tests
 * Tests for Layer4→Layer1 integration in simulation mode
 */

import {
  Layer1IntegrationClient,
  getLayer1Client,
  createLayer1Client,
} from '../../src/trading/integration'
import { OrderIntent, RiskCheckRequest, FinalDecision } from '../../src/trading/types'

function makeOrderIntent(overrides: Partial<OrderIntent> = {}): OrderIntent {
  return {
    symbol: 'AAPL',
    side: 'BUY',
    orderType: 'LIMIT',
    quantity: 100,
    price: 150.0,
    timeInForce: 'DAY',
    strategyId: 'test-strategy',
    ...overrides,
  }
}

function makeDecision(overrides: Partial<FinalDecision> = {}): FinalDecision {
  return {
    action: 'BUY',
    overallConfidence: 0.85,
    reasoningSummary: 'Strong buy signal',
    vetoApplied: false,
    roundsRequired: 3,
    allAnalyses: [],
    votingBreakdown: [],
    requiresHumanReview: false,
    timestamp: new Date().toISOString(),
    ...overrides,
  }
}

function makeRiskCheckRequest(overrides: Partial<RiskCheckRequest> = {}): RiskCheckRequest {
  return {
    orderIntent: makeOrderIntent(),
    currentPositions: [],
    portfolioEquity: 100000,
    dailyPnl: 500,
    currentDrawdownPct: 5,
    ...overrides,
  }
}

describe('Layer1IntegrationClient', () => {
  let client: Layer1IntegrationClient

  beforeEach(() => {
    // Always use simulation mode for tests
    client = new Layer1IntegrationClient({ simulationMode: true })
  })

  afterEach(async () => {
    if (client.isConnected()) {
      await client.disconnect()
    }
  })

  describe('Initialization', () => {
    it('should create client with default config', () => {
      expect(client).toBeDefined()
      expect(client.isConnected()).toBe(false)
      expect(client.isSimulationMode()).toBe(true)
    })

    it('should return config', () => {
      const config = client.getConfig()
      expect(config.simulationMode).toBe(true)
      expect(config.orderTopic).toBe('trading.orders.intent')
    })
  })

  describe('Connection', () => {
    it('should connect in simulation mode', async () => {
      await client.connect()
      expect(client.isConnected()).toBe(true)
    })

    it('should disconnect gracefully', async () => {
      await client.connect()
      await client.disconnect()
      expect(client.isConnected()).toBe(false)
    })

    it('should emit connected event', async () => {
      const events: any[] = []
      client.on('connected', (data) => events.push(data))
      await client.connect()
      expect(events.length).toBe(1)
    })

    it('should emit disconnected event', async () => {
      await client.connect()
      const events: any[] = []
      client.on('disconnected', () => events.push({}))
      await client.disconnect()
      expect(events.length).toBe(1)
    })
  })

  describe('Risk Check', () => {
    it('should approve a normal risk check', async () => {
      await client.connect()
      const request = makeRiskCheckRequest()
      const response = await client.requestRiskCheck(request)

      expect(response.approved).toBe(true)
    })

    it('should reject when drawdown is critical', async () => {
      await client.connect()
      const request = makeRiskCheckRequest({ currentDrawdownPct: 25 })
      const response = await client.requestRiskCheck(request)

      expect(response.approved).toBe(false)
      expect(response.circuitBreakerActive).toBe(true)
    })

    it('should cap position size for large orders', async () => {
      await client.connect()
      const request = makeRiskCheckRequest({
        orderIntent: makeOrderIntent({ quantity: 10000, price: 100 }),
        portfolioEquity: 50000,
      })
      const response = await client.requestRiskCheck(request)

      expect(response.approved).toBe(true)
      expect(response.recommendedSize).toBeDefined()
    })
  })

  describe('Build Risk Check Request', () => {
    it('should build correct risk check request structure', () => {
      const orderIntent = makeOrderIntent()
      const params = {
        orderIntent,
        portfolioEquity: 100000,
        dailyPnl: 1000,
        currentDrawdownPct: 3,
        positions: [
          { symbol: 'MSFT', quantity: 50, avgPrice: 300, marketValue: 15000, unrealizedPnl: 500 },
        ],
      }

      const request = client.buildRiskCheckRequest(params)
      expect(request.orderIntent).toBe(orderIntent)
      expect(request.portfolioEquity).toBe(100000)
      expect(request.currentPositions.length).toBe(1)
    })
  })

  describe('Order Submission', () => {
    it('should simulate order execution', async () => {
      await client.connect()
      const orderIntent = makeOrderIntent()
      const report = await client.submitOrder(orderIntent, 'decision-1')

      expect(report).toBeDefined()
      expect(report.symbol).toBe('AAPL')
      expect(report.status).toBe('FILLED')
    })

    it('should fill order at appropriate price', async () => {
      await client.connect()
      const orderIntent = makeOrderIntent({ price: 150 })
      const report = await client.submitOrder(orderIntent, 'decision-2')

      expect(report.avgFillPrice).toBe(150)
    })
  })

  describe('Submit Order with Risk Check', () => {
    it('should submit order when risk check passes', async () => {
      await client.connect()
      const result = await client.submitOrderWithRiskCheck({
        orderIntent: makeOrderIntent(),
        decision: makeDecision(),
        riskCheckRequest: makeRiskCheckRequest(),
      })

      expect(result.riskApproved).toBe(true)
      expect(result.executionReport).toBeDefined()
    })

    it('should reject order when risk check fails', async () => {
      await client.connect()
      const result = await client.submitOrderWithRiskCheck({
        orderIntent: makeOrderIntent(),
        decision: makeDecision(),
        riskCheckRequest: makeRiskCheckRequest({ currentDrawdownPct: 25 }),
      })

      expect(result.riskApproved).toBe(false)
      expect(result.executionReport).toBeUndefined()
    })
  })

  describe('Execute Decision Pipeline', () => {
    it('should handle HOLD decision', async () => {
      await client.connect()
      const decision = makeDecision({ action: 'HOLD' })
      const result = await client.executeDecision({
        decision,
        orderIntent: makeOrderIntent(),
        portfolioEquity: 100000,
        dailyPnl: 0,
        currentDrawdownPct: 2,
        positions: [],
      })

      expect(result.action).toBe('HELD')
      expect(result.success).toBe(true)
    })

    it('should handle VETO decision', async () => {
      await client.connect()
      const decision = makeDecision({
        action: 'BUY',
        vetoApplied: true,
        vetoReason: 'Risk manager override',
      })
      const result = await client.executeDecision({
        decision,
        orderIntent: makeOrderIntent(),
        portfolioEquity: 100000,
        dailyPnl: 0,
        currentDrawdownPct: 2,
        positions: [],
      })

      expect(result.action).toBe('REJECTED')
      expect(result.success).toBe(false)
      expect(result.error).toBeDefined()
    })

    it('should handle human review required', async () => {
      await client.connect()
      const decision = makeDecision({
        action: 'BUY',
        requiresHumanReview: true,
      })
      const result = await client.executeDecision({
        decision,
        orderIntent: makeOrderIntent(),
        portfolioEquity: 100000,
        dailyPnl: 0,
        currentDrawdownPct: 2,
        positions: [],
      })

      expect(result.action).toBe('HELD')
      expect(result.success).toBe(false)
    })

    it('should execute a valid BUY decision', async () => {
      await client.connect()
      const result = await client.executeDecision({
        decision: makeDecision({ action: 'BUY' }),
        orderIntent: makeOrderIntent(),
        portfolioEquity: 100000,
        dailyPnl: 0,
        currentDrawdownPct: 2,
        positions: [],
      })

      expect(result.action).toBe('EXECUTED')
      expect(result.success).toBe(true)
      expect(result.execution).toBeDefined()
    })

    it('should execute a valid SELL decision', async () => {
      await client.connect()
      const result = await client.executeDecision({
        decision: makeDecision({ action: 'SELL' }),
        orderIntent: makeOrderIntent({ side: 'SELL' }),
        portfolioEquity: 100000,
        dailyPnl: 0,
        currentDrawdownPct: 2,
        positions: [],
      })

      expect(result.action).toBe('EXECUTED')
      expect(result.success).toBe(true)
    })

    it('should emit orderExecuted event', async () => {
      await client.connect()
      const events: any[] = []
      client.on('orderExecuted', (data) => events.push(data))

      await client.executeDecision({
        decision: makeDecision({ action: 'BUY' }),
        orderIntent: makeOrderIntent(),
        portfolioEquity: 100000,
        dailyPnl: 0,
        currentDrawdownPct: 2,
        positions: [],
      })

      expect(events.length).toBe(1)
      expect(events[0].execution).toBeDefined()
    })
  })

  describe('Health / Status', () => {
    it('should report connected status', async () => {
      expect(client.isConnected()).toBe(false)
      await client.connect()
      expect(client.isConnected()).toBe(true)
    })

    it('should report simulation mode', () => {
      expect(client.isSimulationMode()).toBe(true)
    })

    it('should support non-simulation config', () => {
      const nonSimClient = new Layer1IntegrationClient({
        simulationMode: false,
        kafkaBroker: 'localhost:9092',
      })
      expect(nonSimClient.isSimulationMode()).toBe(false)
    })
  })
})

describe('Singleton', () => {
  it('should get same instance from getLayer1Client', () => {
    const client1 = getLayer1Client({ simulationMode: true })
    const client2 = getLayer1Client()
    expect(client1).toBe(client2)
  })

  it('should replace instance with createLayer1Client', () => {
    const client1 = createLayer1Client({ simulationMode: true, clientId: 'test-1' })
    const client2 = getLayer1Client()
    expect(client1).toBe(client2)
  })
})
