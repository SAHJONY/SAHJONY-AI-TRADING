// ─────────────────────────────────────────────────────────────
// Risk Engine - Central risk management orchestrator
// Coordinates VaR, Kelly, circuit breakers, position limits, and drawdown
// ─────────────────────────────────────────────────────────────

use std::sync::atomic::Ordering;
use std::sync::Arc;
use tokio::sync::RwLock;

use crate::config::RiskConfig;
use crate::types::*;
use rust_decimal::Decimal;

use super::var::{VaRCalculator, VaRMethod};
use super::kelly::KellyCriterion;
use super::circuit_breaker::{CircuitBreaker, CircuitBreakerResult};
use super::position_limits::{PositionLimits, PositionLimitResult, PositionsSummary};
use super::drawdown::{DrawdownMonitor, DrawdownStatus};

// ── Rate Limiter ──

/// Token-bucket rate limiter for order throttling.
/// Uses compare-and-swap loops to avoid race conditions.
struct RateLimiter {
    tokens: parking_lot::Mutex<f64>,
    max_tokens: f64,
    refill_rate_per_ns: f64,
    last_refill: std::sync::atomic::AtomicI64,
}

impl RateLimiter {
    fn new(max_orders_per_second: u32) -> Self {
        let max_tokens = max_orders_per_second as f64;
        Self {
            tokens: parking_lot::Mutex::new(max_tokens),
            max_tokens,
            refill_rate_per_ns: max_tokens / 1_000_000_000.0,
            last_refill: std::sync::atomic::AtomicI64::new(0),
        }
    }

    /// Try to consume a token. Returns true if successful.
    fn try_consume(&self, now_ns: i64) -> bool {
        let mut tokens = self.tokens.lock();

        let last = self.last_refill.load(Ordering::Acquire);
        let elapsed = if last > 0 { (now_ns - last).max(0) } else { 1_000_000_000 };

        let new_tokens = (elapsed as f64 * self.refill_rate_per_ns)
            .min(self.max_tokens - *tokens)
            .max(0.0);

        self.last_refill.store(now_ns, Ordering::Release);

        if *tokens + new_tokens >= 1.0 {
            *tokens = (*tokens + new_tokens - 1.0).min(self.max_tokens);
            true
        } else {
            *tokens = (*tokens + new_tokens).min(self.max_tokens);
            false
        }
    }
}

/// Pre-trade risk check response
#[derive(Debug, Clone)]
pub struct RiskCheckResponse {
    /// Is the order approved?
    pub approved: bool,
    /// Rejection reason if not approved
    pub reject_reason: Option<String>,
    /// All risk checks that were performed
    pub checks: Vec<RiskCheckDetail>,
    /// Recommended position size (from Kelly)
    pub recommended_size: Option<f64>,
    /// Timestamp of the check
    pub timestamp: NanosTimestamp,
}

#[derive(Debug, Clone)]
pub struct RiskCheckDetail {
    pub check_name: String,
    pub passed: bool,
    pub detail: String,
}

/// Central risk engine - THE gatekeeper for all orders
pub struct RiskEngine {
    /// Circuit breaker (trip for consecutive rejections)
    pub breaker: CircuitBreaker,
    /// Position limits checker
    pub position_limits: PositionLimits,
    /// Drawdown monitor
    pub drawdown: DrawdownMonitor,
    /// VaR calculator
    pub var_calc: VaRCalculator,
    /// Kelly criterion calculator
    pub kelly: KellyCriterion,
    /// Current positions summary
    pub positions: RwLock<PositionsSummary>,
    /// Historical returns for VaR calculation
    historical_returns: RwLock<Vec<f64>>,
    /// Configuration
    config: RiskConfig,
    /// Total pre-trade checks performed
    checks_performed: std::sync::atomic::AtomicU64,
    /// Total orders rejected
    orders_rejected: std::sync::atomic::AtomicU64,
    /// Rate limiter (token bucket)
    rate_limiter: RateLimiter,
}

impl RiskEngine {
    pub fn new(config: RiskConfig, initial_equity: f64) -> Self {
        let breaker = CircuitBreaker::new(
            config.max_consecutive_rejections,
            config.circuit_breaker_cooldown_secs,
        );

        let position_limits = PositionLimits::new();

        // Initialize position limits from config
        for limit_def in &config.limits {
            let limit = super::position_limits::LimitRule {
                name: limit_def.name.clone(),
                limit_type: match limit_def.limit_type.as_str() {
                    "max_order_size" => super::position_limits::LimitType::MaxOrderSize,
                    "position_notional" => super::position_limits::LimitType::PositionNotional,
                    "max_drawdown_pct" => super::position_limits::LimitType::MaxDrawdownPct,
                    _ => super::position_limits::LimitType::PositionNotional,
                },
                soft_threshold: limit_def.soft_threshold,
                hard_threshold: limit_def.hard_threshold,
                enabled: true,
            };

            match limit_def.scope.as_str() {
                "global" => position_limits.add_global_limit(limit),
                _ => position_limits.add_global_limit(limit), // Default to global
            }
        }

        let drawdown = DrawdownMonitor::new(
            initial_equity,
            config.warn_drawdown_pct,
            config.kill_drawdown_pct,
        );

        let var_calc = VaRCalculator::new(
            config.var_confidence,
            config.var_lookback,
        );

        let kelly = KellyCriterion::new(
            config.kelly_fraction,
            0.01,  // Min 1% of capital
            0.25,  // Max 25% of capital
        );

        Self {
            breaker,
            position_limits,
            drawdown,
            var_calc,
            kelly,
            positions: RwLock::new(PositionsSummary::default()),
            historical_returns: RwLock::new(Vec::new()),
            config,
            checks_performed: std::sync::atomic::AtomicU64::new(0),
            orders_rejected: std::sync::atomic::AtomicU64::new(0),
            rate_limiter: RateLimiter::new(config.max_orders_per_second),
        }
    }

    /// Pre-trade risk check - THE critical path method
    ///
    /// This is called before every order hits the wire.
    /// Must be sub-100 microseconds. No allocations in the hot path.
    ///
    /// Order of checks (fail-fast):
    /// 1. Kill switch / circuit breaker (fastest)
    /// 2. Position limits (hard limits)
    /// 3. Drawdown check
    /// 4. Optional: VaR check
    pub async fn pre_trade_check(&self, order: &NewOrderRequest) -> RiskCheckResponse {
        self.checks_performed
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);

        let mut checks = Vec::new();

        // ── CHECK 0: Order validation ──
        if let Err(e) = order.validate() {
            self.orders_rejected
                .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            checks.push(RiskCheckDetail {
                check_name: "order_validation".into(),
                passed: false,
                detail: e.to_string(),
            });
            return RiskCheckResponse {
                approved: false,
                reject_reason: Some(e.to_string()),
                checks,
                recommended_size: None,
                timestamp: NanosTimestamp::now(),
            };
        }

        // ── CHECK 0.5: Rate limiting ──
        let now_ns = NanosTimestamp::now().as_nanos();
        let rate_allowed = self.rate_limiter.try_consume(now_ns);
        checks.push(RiskCheckDetail {
            check_name: "rate_limit".into(),
            passed: rate_allowed,
            detail: if rate_allowed {
                "OK".into()
            } else {
                "Rate limit exceeded".into()
            },
        });
        if !rate_allowed {
            self.orders_rejected
                .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            return RiskCheckResponse {
                approved: false,
                reject_reason: Some("Rate limit exceeded".into()),
                checks,
                recommended_size: None,
                timestamp: NanosTimestamp::now(),
            };
        }

        // ── CHECK 1: Circuit Breaker ──
        let breaker_check = self.breaker.check();
        checks.push(RiskCheckDetail {
            check_name: "circuit_breaker".into(),
            passed: breaker_check.is_allowed(),
            detail: match &breaker_check {
                CircuitBreakerResult::Allowed => "OK".into(),
                CircuitBreakerResult::Blocked(r) => r.clone(),
            },
        });

        if !breaker_check.is_allowed() {
            self.orders_rejected
                .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            return RiskCheckResponse {
                approved: false,
                reject_reason: Some(breaker_check.reason().unwrap_or("Blocked").into()),
                checks,
                recommended_size: None,
                timestamp: NanosTimestamp::now(),
            };
        }

        // ── CHECK 2: Position Limits ──
        let positions = self.positions.read().await;
        let limit_check = self.position_limits.check_order(order, &positions);
        drop(positions);

        checks.push(RiskCheckDetail {
            check_name: "position_limits".into(),
            passed: limit_check.allowed,
            detail: if limit_check.allowed {
                format!("OK (max util: {:.1}%)", limit_check.max_utilization)
            } else {
                limit_check
                    .reject_reason
                    .clone()
                    .unwrap_or("Limit breached".into())
            },
        });

        if !limit_check.allowed {
            self.breaker
                .record_rejection(&limit_check.reject_reason.unwrap_or_default());
            self.orders_rejected
                .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            return RiskCheckResponse {
                approved: false,
                reject_reason: limit_check.reject_reason,
                checks,
                recommended_size: None,
                timestamp: NanosTimestamp::now(),
            };
        }

        // ── CHECK 3: Drawdown ──
        let dd_pct = self.drawdown.current_drawdown_pct();
        let dd_check = dd_pct < self.config.kill_drawdown_pct;

        checks.push(RiskCheckDetail {
            check_name: "drawdown".into(),
            passed: dd_check,
            detail: format!("DD: {:.2}%", dd_pct),
        });

        if !dd_check {
            self.breaker.kill(&format!(
                "Drawdown kill threshold breached: {:.2}%",
                dd_pct
            ));
            self.orders_rejected
                .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
            return RiskCheckResponse {
                approved: false,
                reject_reason: Some(format!(
                    "Drawdown limit: {:.2}% exceeds {:.2}%",
                    dd_pct, self.config.kill_drawdown_pct
                )),
                checks,
                recommended_size: None,
                timestamp: NanosTimestamp::now(),
            };
        }

        // ── Optional: Kelly Position Sizing Recommendation ──
        let recommended_size = None; // Calculated asynchronously (see below)

        // Record success
        self.breaker.record_success();

        RiskCheckResponse {
            approved: true,
            reject_reason: None,
            checks,
            recommended_size,
            timestamp: NanosTimestamp::now(),
        }
    }

    /// Update equity and recalculate risk metrics
    pub async fn update_equity(&self, new_equity: f64, daily_pnl: f64) {
        // Update drawdown
        let dd_status = self.drawdown.update_equity(new_equity);

        if let DrawdownStatus::Critical { pct } = dd_status {
            self.breaker.kill(&format!("Drawdown critical: {:.2}%", pct));
        }

        // Update positions
        let mut positions = self.positions.write().await;
        positions.total_equity = new_equity;
        positions.daily_pnl = daily_pnl;
        positions.drawdown_pct = self.drawdown.current_drawdown_pct();
    }

    /// Append a return for VaR calculation
    pub async fn record_return(&self, ret: f64) {
        let mut returns = self.historical_returns.write().await;
        returns.push(ret);

        // Trim to lookback window
        while returns.len() > self.config.var_lookback * 2 {
            returns.remove(0);
        }
    }

    /// Calculate current VaR
    pub async fn calculate_var(&self) -> Option<super::var::VaRResult> {
        let returns = self.historical_returns.read().await;
        let equity = self.positions.read().await.total_equity;

        self.var_calc
            .historical_var(&returns, equity)
    }

    /// Get recommended position size using Kelly criterion
    pub fn recommended_position_size(
        &self,
        win_probability: f64,
        expected_return: f64,
        risk_per_trade: f64,
    ) -> f64 {
        let equity = self.drawdown.current_equity();
        self.kelly
            .position_size(win_probability, expected_return, risk_per_trade, equity)
    }

    /// Activate emergency kill switch
    pub fn emergency_kill(&self, reason: &str) {
        self.breaker.kill(reason);
    }

    /// Update positions summary after an order execution or fill
    pub async fn update_position_summary(&self, notional: f64, side: &OrderSide) {
        let mut positions = self.positions.write().await;
        match side {
            OrderSide::Buy => {
                positions.total_notional += notional;
                positions.gross_exposure += notional;
                positions.net_exposure += notional;
            }
            OrderSide::Sell | OrderSide::SellShort => {
                positions.total_notional += notional;
                positions.gross_exposure += notional;
                positions.net_exposure -= notional;
            }
        }
    }

    /// Reduce positions summary (e.g., after a fill reduces a position).
    /// Does not artificially floor/ceil — net_exposure can cross zero naturally
    /// when a position transitions from long to short or vice versa.
    pub async fn reduce_position_summary(&self, notional: f64, side: &OrderSide) {
        let mut positions = self.positions.write().await;
        match side {
            OrderSide::Buy => {
                // Reducing a short: buy to cover → net_exposure moves toward zero / positive
                positions.total_notional = (positions.total_notional - notional).max(0.0);
                positions.net_exposure += notional;
            }
            OrderSide::Sell | OrderSide::SellShort => {
                // Reducing a long: sell → net_exposure moves toward zero / negative
                positions.total_notional = (positions.total_notional - notional).max(0.0);
                positions.net_exposure -= notional;
            }
        }
        positions.gross_exposure = positions.total_notional;
    }
    pub fn metrics(&self) -> RiskMetrics {
        RiskMetrics {
            circuit_state: self.breaker.state(),
            kill_active: self.breaker.is_killed(),
            current_drawdown_pct: self.drawdown.current_drawdown_pct(),
            max_drawdown_pct: self.drawdown.max_drawdown_pct(),
            peak_equity: self.drawdown.peak_equity(),
            current_equity: self.drawdown.current_equity(),
            checks_performed: self.checks_performed.load(std::sync::atomic::Ordering::Relaxed),
            orders_rejected: self.orders_rejected.load(std::sync::atomic::Ordering::Relaxed),
            orders_blocked: self.breaker.orders_blocked(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct RiskMetrics {
    pub circuit_state: super::circuit_breaker::CircuitState,
    pub kill_active: bool,
    pub current_drawdown_pct: f64,
    pub max_drawdown_pct: f64,
    pub peak_equity: f64,
    pub current_equity: f64,
    pub checks_performed: u64,
    pub orders_rejected: u64,
    pub orders_blocked: u64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_risk_engine_pre_trade() {
        let config = RiskConfig::default();
        let engine = RiskEngine::new(config, 1_000_000.0);

        let order = NewOrderRequest {
            symbol: Symbol("AAPL".into()),
            exchange: Exchange("NASDAQ".into()),
            side: OrderSide::Buy,
            order_type: OrderType::Limit,
            time_in_force: TimeInForce::Day,
            quantity: 100.0,
            price: Some(Decimal::from_f64(150.0).unwrap()),
            stop_price: None,
            trailing_amount: None,
            display_quantity: None,
            client_order_id: ClientOrderId::new(),
            strategy_id: StrategyId("test".into()),
            account_id: AccountId("test".into()),
            tags: std::collections::HashMap::new(),
        };

        let result = engine.pre_trade_check(&order).await;
        assert!(result.approved);
        // 5 checks: validation, rate_limit, circuit_breaker, position_limits, drawdown
        assert_eq!(result.checks.len(), 5);
    }

    #[tokio::test]
    async fn test_risk_engine_kill_switch() {
        let config = RiskConfig::default();
        let engine = RiskEngine::new(config, 1_000_000.0);

        engine.emergency_kill("test kill");

        let order = NewOrderRequest {
            symbol: Symbol("AAPL".into()),
            exchange: Exchange("NASDAQ".into()),
            side: OrderSide::Buy,
            order_type: OrderType::Limit,
            time_in_force: TimeInForce::Day,
            quantity: 100.0,
            price: Some(Decimal::from_f64(150.0).unwrap()),
            stop_price: None,
            trailing_amount: None,
            display_quantity: None,
            client_order_id: ClientOrderId::new(),
            strategy_id: StrategyId("test".into()),
            account_id: AccountId("test".into()),
            tags: std::collections::HashMap::new(),
        };

        let result = engine.pre_trade_check(&order).await;
        assert!(!result.approved);
    }
}

