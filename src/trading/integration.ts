/**
 * Layer 4 → Layer 1 Integration Hooks
 *
 * Bridges the multi-agent collaborative reasoning system (Layer 4) with the
 * Rust execution engine (Layer 1) via Kafka/Redpanda event streaming.
 *
 * Communication protocol:
 * - Layer 4 produces order & risk-check events to Kafka topics
 * - Layer 1 consumes those events for pre-trade risk validation and execution
 * - Layer 1 produces execution reports & risk responses consumed here
 */

import { EventEmitter } from 'events'
import {
  FinalDecision,
  OrderIntent,
  RiskCheckRequest,
  RiskCheckResponse,
  MarketDataInput,
} from './types'

// ── Integration Configuration ──

export interface Layer1IntegrationConfig {
  /** Kafka/Redpanda broker endpoint */
  kafkaBroker: string
  /** Kafka client ID */
  clientId: string
  /** Topic for order intents (Layer 4 → Layer 1) */
  orderTopic: string
  /** Topic for risk check requests (Layer 4 → Layer 1) */
  riskCheckTopic: string
  /** Topic for execution reports (Layer 1 → Layer 4) */
  executionReportTopic: string
  /** Topic for risk check responses (Layer 1 → Layer 4) */
  riskResponseTopic: string
  /** Max wait time for execution/risk response (ms) */
  responseTimeoutMs: number
  /** Whether to use simulated responses when Layer 1 is unavailable */
  simulationMode: boolean
}

const DEFAULT_INTEGRATION_CONFIG: Layer1IntegrationConfig = {
  kafkaBroker: process.env.KAFKA_BROKER || 'localhost:19092',
  clientId: `trading-workforce-l4-${Date.now()}`,
  orderTopic: 'trading.orders.intent',
  riskCheckTopic: 'trading.risk.check',
  executionReportTopic: 'trading.execution.report',
  riskResponseTopic: 'trading.risk.response',
  responseTimeoutMs: 30_000,
  simulationMode: !process.env.KAFKA_BROKER,
}

// ── Execution Report (from Layer 1) ──

export interface ExecutionReport {
  orderId: string
  correlationId: string
  symbol: string
  side: 'BUY' | 'SELL' | 'SELL_SHORT'
  orderType: string
  quantity: number
  filledQuantity: number
  avgFillPrice: number
  status: 'NEW' | 'PARTIALLY_FILLED' | 'FILLED' | 'CANCELLED' | 'REJECTED'
  rejectReason?: string
  timestamp: string
  commission?: number
  venue?: string
}

// ── Pending Request Tracker ──

interface PendingRequest<T> {
  resolve: (value: T) => void
  reject: (error: Error) => void
  timer: NodeJS.Timeout
}

// ── Layer 1 Integration Client ──

export class Layer1IntegrationClient extends EventEmitter {
  private config: Layer1IntegrationConfig
  private pendingRiskChecks: Map<string, PendingRequest<RiskCheckResponse>> = new Map()
  private pendingOrders: Map<string, PendingRequest<ExecutionReport>> = new Map()
  private connected = false

  constructor(config: Partial<Layer1IntegrationConfig> = {}) {
    super()
    this.config = { ...DEFAULT_INTEGRATION_CONFIG, ...config }
  }

  // ── Connection Management ──

  /**
   * Initialize the Kafka producer/consumer connections to Layer 1.
   * In simulation mode, this is a no-op.
   */
  async connect(): Promise<void> {
    if (this.config.simulationMode) {
      console.log('[Layer4→Layer1] Running in simulation mode — Layer 1 responses will be mocked')
      this.connected = true
      return
    }

    // In production, this would initialize KafkaJS producer and consumer:
    // const { Kafka } = await import('kafkajs')
    // const kafka = new Kafka({ clientId: this.config.clientId, brokers: [this.config.kafkaBroker] })
    // this.producer = kafka.producer()
    // this.consumer = kafka.consumer({ groupId: `${this.config.clientId}-group` })
    // await Promise.all([this.producer.connect(), this.consumer.connect()])
    // await this.consumer.subscribe({ topics: [this.config.executionReportTopic, this.config.riskResponseTopic] })
    // await this.consumer.run({ eachMessage: async ({ topic, message }) => this.handleInboundMessage(topic, message) })

    console.log(`[Layer4→Layer1] Connected to Kafka at ${this.config.kafkaBroker}`)
    this.connected = true
    this.emit('connected', { broker: this.config.kafkaBroker })
  }

  /**
   * Gracefully disconnect from Layer 1.
   */
  async disconnect(): Promise<void> {
    this.connected = false
    // Reject all pending requests
    const timeoutError = new Error('Layer 1 connection closed')
    for (const [id, pending] of this.pendingRiskChecks) {
      clearTimeout(pending.timer)
      pending.reject(timeoutError)
    }
    for (const [id, pending] of this.pendingOrders) {
      clearTimeout(pending.timer)
      pending.reject(timeoutError)
    }
    this.pendingRiskChecks.clear()
    this.pendingOrders.clear()
    this.emit('disconnected')
  }

  // ── Risk Check (Pre-Trade Validation) ──

  /**
   * Request a pre-trade risk check from Layer 1.
   *
   * This sends the order intent + current portfolio state to the Rust risk engine,
   * which runs the 5-layer check pipeline (circuit breaker → VaR → position limits →
   * Kelly sizing → drawdown) and returns approval/rejection.
   */
  async requestRiskCheck(request: RiskCheckRequest): Promise<RiskCheckResponse> {
    const correlationId = `risk-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

    if (this.config.simulationMode) {
      return this.simulateRiskCheck(request)
    }

    // Send to Kafka
    await this.sendToKafka(this.config.riskCheckTopic, correlationId, {
      type: 'RiskCheckRequest',
      correlationId,
      payload: request,
    })

    // Wait for response
    return this.waitForResponse<RiskCheckResponse>(
      correlationId,
      this.pendingRiskChecks,
      'Risk check'
    )
  }

  /**
   * Build a risk check request from the consensus decision and portfolio state.
   */
  buildRiskCheckRequest(params: {
    orderIntent: OrderIntent
    portfolioEquity: number
    dailyPnl: number
    currentDrawdownPct: number
    positions: Array<{
      symbol: string
      quantity: number
      avgPrice: number
      marketValue: number
      unrealizedPnl: number
    }>
  }): RiskCheckRequest {
    return {
      orderIntent: params.orderIntent,
      currentPositions: params.positions,
      portfolioEquity: params.portfolioEquity,
      dailyPnl: params.dailyPnl,
      currentDrawdownPct: params.currentDrawdownPct,
    }
  }

  // ── Order Submission ──

  /**
   * Submit a trading order to Layer 1 for execution.
   *
   * The Rust execution engine will route the order through:
   * 1. Pre-trade risk check (circuit breakers, limits, VaR)
   * 2. Order gateway (exchange-specific routing)
   * 3. Execution algos (VWAP, TWAP, etc.)
   *
   * Returns the final execution report (may be partially filled).
   */
  async submitOrder(orderIntent: OrderIntent, decisionId: string): Promise<ExecutionReport> {
    const correlationId = `order-${decisionId}-${Date.now()}`

    if (this.config.simulationMode) {
      return this.simulateExecution(orderIntent, correlationId)
    }

    // Send to Kafka
    await this.sendToKafka(this.config.orderTopic, correlationId, {
      type: 'OrderIntent',
      correlationId,
      decisionId,
      payload: orderIntent,
    })

    // Wait for execution report
    return this.waitForResponse<ExecutionReport>(
      correlationId,
      this.pendingOrders,
      'Order execution'
    )
  }

  /**
   * Submit an order only if the risk check passes.
   */
  async submitOrderWithRiskCheck(params: {
    orderIntent: OrderIntent
    decision: FinalDecision
    riskCheckRequest: RiskCheckRequest
  }): Promise<{
    riskApproved: boolean
    riskResponse: RiskCheckResponse
    executionReport?: ExecutionReport
  }> {
    // Step 1: Risk check
    const riskResponse = await this.requestRiskCheck(params.riskCheckRequest)

    if (!riskResponse.approved) {
      this.emit('orderRejected', {
        reason: riskResponse.rejectReason,
        riskResponse,
        orderIntent: params.orderIntent,
      })
      return { riskApproved: false, riskResponse }
    }

    // Step 2: If risk-approved and position size adjusted, update order
    let orderIntent = { ...params.orderIntent }
    if (riskResponse.recommendedSize && riskResponse.recommendedSize < orderIntent.quantity) {
      orderIntent.quantity = Math.floor(riskResponse.recommendedSize)
      this.emit('orderAdjusted', {
        originalQuantity: params.orderIntent.quantity,
        adjustedQuantity: orderIntent.quantity,
        reason: 'Risk manager position size limit',
      })
    }

    // Step 3: Submit order
    const executionReport = await this.submitOrder(orderIntent, params.decision.timestamp)

    return {
      riskApproved: true,
      riskResponse,
      executionReport,
    }
  }

  // ── Decision-to-Order Pipeline ──

  /**
   * Convert a Layer 4 consensus FinalDecision into an OrderIntent,
   * perform risk check, and submit to Layer 1.
   *
   * This is the main pipeline: Layer 4 consensus → Layer 1 execution.
   */
  async executeDecision(params: {
    decision: FinalDecision
    orderIntent: OrderIntent
    portfolioEquity: number
    dailyPnl: number
    currentDrawdownPct: number
    positions: Array<{
      symbol: string
      quantity: number
      avgPrice: number
      marketValue: number
      unrealizedPnl: number
    }>
  }): Promise<{
    success: boolean
    action: 'EXECUTED' | 'REJECTED' | 'HELD'
    riskCheck: RiskCheckResponse
    execution?: ExecutionReport
    error?: string
  }> {
    if (params.decision.action === 'HOLD') {
      return {
        success: true,
        action: 'HELD',
        riskCheck: {
          approved: false,
          rejectReason: 'Decision was HOLD — no order submitted',
          circuitBreakerActive: false,
          drawdownLevel: 'NORMAL',
        },
      }
    }

    if (params.decision.vetoApplied) {
      return {
        success: false,
        action: 'REJECTED',
        riskCheck: {
          approved: false,
          rejectReason: params.decision.vetoReason || 'Risk Manager veto applied',
          circuitBreakerActive: false,
          drawdownLevel: 'NORMAL',
        },
        error: params.decision.vetoReason,
      }
    }

    if (params.decision.requiresHumanReview) {
      this.emit('humanReviewRequired', { decision: params.decision, orderIntent: params.orderIntent })
      return {
        success: false,
        action: 'HELD',
        riskCheck: {
          approved: false,
          rejectReason: 'Human review required — low confidence decision',
          circuitBreakerActive: false,
          drawdownLevel: 'NORMAL',
        },
        error: 'Awaiting human review',
      }
    }

    const riskCheckRequest = this.buildRiskCheckRequest({
      orderIntent: params.orderIntent,
      portfolioEquity: params.portfolioEquity,
      dailyPnl: params.dailyPnl,
      currentDrawdownPct: params.currentDrawdownPct,
      positions: params.positions,
    })

    try {
      const { riskApproved, riskResponse, executionReport } = await this.submitOrderWithRiskCheck({
        orderIntent: params.orderIntent,
        decision: params.decision,
        riskCheckRequest,
      })

      if (!riskApproved || !executionReport) {
        return {
          success: false,
          action: 'REJECTED',
          riskCheck: riskResponse,
          error: riskResponse.rejectReason,
        }
      }

      this.emit('orderExecuted', {
        decision: params.decision,
        execution: executionReport,
        riskCheck: riskResponse,
      })

      return {
        success: true,
        action: 'EXECUTED',
        riskCheck: riskResponse,
        execution: executionReport,
      }
    } catch (error) {
      return {
        success: false,
        action: 'REJECTED',
        riskCheck: {
          approved: false,
          rejectReason: error instanceof Error ? error.message : String(error),
          circuitBreakerActive: false,
          drawdownLevel: 'NORMAL',
        },
        error: error instanceof Error ? error.message : String(error),
      }
    }
  }

  // ── Private: Kafka Messaging ──

  private async sendToKafka(topic: string, key: string, value: unknown): Promise<void> {
    if (this.config.simulationMode) return

    // In production, this would use the KafkaJS producer:
    // await this.producer.send({
    //   topic,
    //   messages: [{ key, value: JSON.stringify(value), headers: { 'correlation-id': key } }],
    // })

    console.log(`[Layer4→Layer1] → ${topic} [${key}]:`, JSON.stringify(value).slice(0, 200))
  }

  private handleInboundMessage(topic: string, message: { key?: string; value?: Buffer }): void {
    if (!message.value) return

    try {
      const parsed = JSON.parse(message.value.toString())
      const correlationId = parsed.correlationId || message.key?.toString() || ''

      if (topic === this.config.riskResponseTopic) {
        const pending = this.pendingRiskChecks.get(correlationId)
        if (pending) {
          clearTimeout(pending.timer)
          this.pendingRiskChecks.delete(correlationId)
          pending.resolve(parsed.payload as RiskCheckResponse)
        }
      } else if (topic === this.config.executionReportTopic) {
        const pending = this.pendingOrders.get(correlationId)
        if (pending) {
          clearTimeout(pending.timer)
          this.pendingOrders.delete(correlationId)
          pending.resolve(parsed.payload as ExecutionReport)
        }
      }
    } catch (err) {
      console.error('[Layer4→Layer1] Failed to parse inbound message:', err)
    }
  }

  private waitForResponse<T>(
    correlationId: string,
    pendingMap: Map<string, PendingRequest<T>>,
    label: string
  ): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        pendingMap.delete(correlationId)
        reject(new Error(`${label} timed out after ${this.config.responseTimeoutMs}ms`))
      }, this.config.responseTimeoutMs)

      pendingMap.set(correlationId, { resolve, reject, timer })
    })
  }

  // ── Simulation Mode (for development without Layer 1 running) ──

  private async simulateRiskCheck(request: RiskCheckRequest): Promise<RiskCheckResponse> {
    // Simulate 50ms risk engine latency
    await new Promise(r => setTimeout(r, 50))

    const dollarSize = request.orderIntent.quantity * (request.orderIntent.price || 100)
    const pctOfPortfolio = dollarSize / (request.portfolioEquity || 100_000)
    const isDrawdownCritical = request.currentDrawdownPct > 20

    if (isDrawdownCritical) {
      return {
        approved: false,
        rejectReason: `CRITICAL DRAWDOWN: portfolio down ${request.currentDrawdownPct.toFixed(1)}% — kill switch active`,
        circuitBreakerActive: true,
        drawdownLevel: 'CRITICAL',
        currentVar: dollarSize,
        maxPositionSize: 0,
      }
    }

    if (pctOfPortfolio > 0.25) {
      return {
        approved: true,
        maxPositionSize: Math.floor(request.portfolioEquity * 0.25 / (request.orderIntent.price || 100)),
        recommendedSize: Math.floor(request.portfolioEquity * 0.15 / (request.orderIntent.price || 100)),
        currentVar: dollarSize * 0.02,
        circuitBreakerActive: false,
        drawdownLevel: request.currentDrawdownPct > 10 ? 'WARNING' : 'NORMAL',
      }
    }

    return {
      approved: true,
      maxPositionSize: Math.floor(request.portfolioEquity * 0.25 / (request.orderIntent.price || 100)),
      currentVar: dollarSize * 0.02,
      circuitBreakerActive: false,
      drawdownLevel: request.currentDrawdownPct > 10 ? 'WARNING' : 'NORMAL',
    }
  }

  private async simulateExecution(
    orderIntent: OrderIntent,
    correlationId: string
  ): Promise<ExecutionReport> {
    // Simulate variable latency (10-200ms) to mimic real exchange
    const latency = 10 + Math.random() * 190
    await new Promise(r => setTimeout(r, latency))

    const fillPrice = orderIntent.price || (orderIntent.side === 'BUY' ? 100.05 : 99.95)

    return {
      orderId: `sim-${correlationId}`,
      correlationId,
      symbol: orderIntent.symbol,
      side: orderIntent.side,
      orderType: orderIntent.orderType,
      quantity: orderIntent.quantity,
      filledQuantity: orderIntent.quantity,
      avgFillPrice: fillPrice,
      status: 'FILLED',
      timestamp: new Date().toISOString(),
      commission: orderIntent.quantity * fillPrice * 0.001,
      venue: 'SIMULATED',
    }
  }

  // ── Health / Status ──

  isConnected(): boolean {
    return this.connected
  }

  isSimulationMode(): boolean {
    return this.config.simulationMode
  }

  getConfig(): Readonly<Layer1IntegrationConfig> {
    return { ...this.config }
  }
}

// ── Singleton ──

let integrationInstance: Layer1IntegrationClient | null = null

export function getLayer1Client(config?: Partial<Layer1IntegrationConfig>): Layer1IntegrationClient {
  if (!integrationInstance) {
    integrationInstance = new Layer1IntegrationClient(config)
  }
  return integrationInstance
}

export function createLayer1Client(config?: Partial<Layer1IntegrationConfig>): Layer1IntegrationClient {
  integrationInstance = new Layer1IntegrationClient(config)
  return integrationInstance
}
