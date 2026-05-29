// ─────────────────────────────────────────────────────────────
// Position Limits - Pre-trade position and exposure checks
// ─────────────────────────────────────────────────────────────

use dashmap::DashMap;
use rust_decimal::Decimal;
use std::sync::Arc;

use crate::types::*;

/// Position limit check result
#[derive(Debug, Clone)]
pub struct PositionLimitResult {
    pub allowed: bool,
    pub reject_reason: Option<String>,
    /// Current utilization of the most constrained limit (0.0–1.0+)
    pub max_utilization: f64,
    /// All violations found
    pub violations: Vec<LimitViolation>,
}

#[derive(Debug, Clone)]
pub struct LimitViolation {
    pub limit_name: String,
    pub limit_value: f64,
    pub current_value: f64,
    pub utilization_pct: f64,
}

/// Position limits manager
pub struct PositionLimits {
    /// Limits by scope
    global_limits: dashmap::DashMap<String, LimitRule>,
    /// Per-symbol limits
    symbol_limits: dashmap::DashMap<Symbol, Vec<LimitRule>>,
    /// Per-strategy limits
    strategy_limits: dashmap::DashMap<StrategyId, Vec<LimitRule>>,
    /// Per-account limits
    account_limits: dashmap::DashMap<AccountId, Vec<LimitRule>>,
}

#[derive(Debug, Clone)]
pub struct LimitRule {
    pub name: String,
    pub limit_type: LimitType,
    pub soft_threshold: f64,
    pub hard_threshold: f64,
    pub enabled: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LimitType {
    PositionNotional,
    MaxOrderSize,
    MaxOrderRate,
    MaxDailyPnl,
    MaxDrawdownPct,
    VaRLimit,
    ConcentrationPct,
    SectorExposure,
    MaxGrossExposure,
    MaxNetExposure,
}

impl PositionLimits {
    pub fn new() -> Self {
        Self {
            global_limits: DashMap::new(),
            symbol_limits: DashMap::new(),
            strategy_limits: DashMap::new(),
            account_limits: DashMap::new(),
        }
    }

    /// Add a global limit
    pub fn add_global_limit(&self, limit: LimitRule) {
        self.global_limits.insert(limit.name.clone(), limit);
    }

    /// Add a per-symbol limit
    pub fn add_symbol_limit(&self, symbol: Symbol, limit: LimitRule) {
        self.symbol_limits
            .entry(symbol)
            .or_default()
            .push(limit);
    }

    /// Add a per-strategy limit
    pub fn add_strategy_limit(&self, strategy: StrategyId, limit: LimitRule) {
        self.strategy_limits
            .entry(strategy)
            .or_default()
            .push(limit);
    }

    /// Add a per-account limit
    pub fn add_account_limit(&self, account: AccountId, limit: LimitRule) {
        self.account_limits
            .entry(account)
            .or_default()
            .push(limit);
    }

    /// Check an order against all applicable position limits
    pub fn check_order(
        &self,
        order: &NewOrderRequest,
        current_positions: &PositionsSummary,
    ) -> PositionLimitResult {
        let mut violations = Vec::new();
        let mut max_util = 0.0;

        let notional = order.estimated_notional()
            .to_f64()
            .unwrap_or(0.0);

        // Check global limits
        for limit in self.global_limits.iter() {
            if !limit.enabled {
                continue;
            }
            if let Some(violation) =
                self.check_limit(&limit, notional, current_positions)
            {
                max_util = max_util.max(violation.utilization_pct);
                violations.push(violation);
            }
        }

        // Check symbol limits
        if let Some(sym_limits) = self.symbol_limits.get(&order.symbol) {
            for limit in sym_limits.iter() {
                if !limit.enabled {
                    continue;
                }
                if let Some(violation) =
                    self.check_limit(limit, notional, current_positions)
                {
                    max_util = max_util.max(violation.utilization_pct);
                    violations.push(violation);
                }
            }
        }

        // Check strategy limits
        if let Some(strat_limits) = self.strategy_limits.get(&order.strategy_id) {
            for limit in strat_limits.iter() {
                if !limit.enabled {
                    continue;
                }
                if let Some(violation) =
                    self.check_limit(limit, notional, current_positions)
                {
                    max_util = max_util.max(violation.utilization_pct);
                    violations.push(violation);
                }
            }
        }

        // Check account limits
        if let Some(acct_limits) = self.account_limits.get(&order.account_id) {
            for limit in acct_limits.iter() {
                if !limit.enabled {
                    continue;
                }
                if let Some(violation) =
                    self.check_limit(limit, notional, current_positions)
                {
                    max_util = max_util.max(violation.utilization_pct);
                    violations.push(violation);
                }
            }
        }

        let has_hard_violation = violations.iter().any(|v| v.utilization_pct >= 1.0);

        PositionLimitResult {
            allowed: !has_hard_violation,
            reject_reason: if has_hard_violation {
                Some(format!(
                    "Position limit breached: {}",
                    violations
                        .iter()
                        .filter(|v| v.utilization_pct >= 1.0)
                        .map(|v| v.limit_name.as_str())
                        .collect::<Vec<_>>()
                        .join(", ")
                ))
            } else {
                None
            },
            max_utilization: max_util,
            violations,
        }
    }

    /// Check a single limit against current state
    fn check_limit(
        &self,
        limit: &LimitRule,
        order_notional: f64,
        positions: &PositionsSummary,
    ) -> Option<LimitViolation> {
        let current_value = match limit.limit_type {
            LimitType::PositionNotional => positions.total_notional + order_notional,
            LimitType::MaxOrderSize => order_notional,
            LimitType::MaxGrossExposure => positions.gross_exposure + order_notional,
            LimitType::MaxNetExposure => (positions.net_exposure + order_notional).abs(),
            LimitType::MaxDrawdownPct => positions.drawdown_pct,
            LimitType::ConcentrationPct => {
                if positions.total_notional > 0.0 {
                    (order_notional / positions.total_notional) * 100.0
                } else {
                    order_notional
                }
            }
            _ => order_notional, // Default to order notional
        };

        let utilization = if limit.hard_threshold > 0.0 {
            current_value / limit.hard_threshold
        } else {
            0.0
        };

        if utilization > 1.0 {
            Some(LimitViolation {
                limit_name: limit.name.clone(),
                limit_value: limit.hard_threshold,
                current_value,
                utilization_pct: utilization * 100.0,
            })
        } else {
            None
        }
    }

    /// Enable/disable a global limit
    pub fn set_limit_enabled(&self, name: &str, enabled: bool) -> bool {
        if let Some(mut limit) = self.global_limits.get_mut(name) {
            limit.enabled = enabled;
            true
        } else {
            false
        }
    }

    /// Update a limit's thresholds
    pub fn update_thresholds(&self, name: &str, soft: f64, hard: f64) -> bool {
        if let Some(mut limit) = self.global_limits.get_mut(name) {
            limit.soft_threshold = soft;
            limit.hard_threshold = hard;
            true
        } else {
            false
        }
    }
}

/// Summary of current positions for limit checks
#[derive(Debug, Clone)]
pub struct PositionsSummary {
    pub total_notional: f64,
    pub gross_exposure: f64,
    pub net_exposure: f64,
    pub drawdown_pct: f64,
    pub daily_pnl: f64,
    pub total_equity: f64,
}

impl Default for PositionsSummary {
    fn default() -> Self {
        Self {
            total_notional: 0.0,
            gross_exposure: 0.0,
            net_exposure: 0.0,
            drawdown_pct: 0.0,
            daily_pnl: 0.0,
            total_equity: 1_000_000.0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_position_limit_check() {
        let limits = PositionLimits::new();

        limits.add_global_limit(LimitRule {
            name: "max_position_notional".into(),
            limit_type: LimitType::PositionNotional,
            soft_threshold: 800_000.0,
            hard_threshold: 1_000_000.0,
            enabled: true,
        });

        let positions = PositionsSummary {
            total_notional: 500_000.0,
            ..Default::default()
        };

        // Order that would keep us under the limit
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

        let result = limits.check_order(&order, &positions);
        assert!(result.allowed); // 500k + 15k = 515k < 1M

        // Order that would breach the limit
        let big_order = NewOrderRequest {
            quantity: 5000.0,
            price: Some(Decimal::from_f64(150.0).unwrap()),
            ..order.clone()
        };

        let result = limits.check_order(&big_order, &positions);
        assert!(!result.allowed); // 500k + 750k = 1.25M > 1M
    }
}
