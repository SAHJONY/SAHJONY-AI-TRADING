// ─────────────────────────────────────────────────────────────
// Order Router - Smart order routing across venues
// ─────────────────────────────────────────────────────────────

use dashmap::DashMap;
use rust_decimal::Decimal;
use std::collections::HashMap;

use crate::types::*;

/// Represents a trading venue
#[derive(Debug, Clone)]
pub struct Venue {
    pub name: Exchange,
    /// Fee rate in bps (basis points)
    pub fee_bps: f64,
    /// Rebate in bps (for adding liquidity)
    pub rebate_bps: f64,
    /// Estimated fill probability (0.0–1.0)
    pub fill_probability: f64,
    /// Average latency in microseconds
    pub avg_latency_us: u64,
    /// Is this venue currently available?
    pub available: bool,
    /// Supported symbols
    pub symbols: Vec<Symbol>,
}

/// Venue ranking score (higher = better for this order)
#[derive(Debug, Clone, PartialEq)]
pub struct VenueScore {
    pub venue: Exchange,
    pub score: f64,
    pub estimated_cost: Decimal,
    pub reasoning: String,
}

/// Order Router - routes orders to optimal venues
pub struct OrderRouter {
    /// Available venues
    venues: DashMap<Exchange, Venue>,
    /// Default venue (fallback)
    default_venue: Exchange,
    /// Routing strategy
    strategy: RoutingStrategy,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RoutingStrategy {
    /// Lowest cost (fees - rebates)
    LowestCost,
    /// Highest fill probability
    HighestFill,
    /// Lowest latency
    LowestLatency,
    /// Smart routing: balances cost, fill rate, and latency
    Smart,
}

impl OrderRouter {
    pub fn new(default_venue: Exchange, strategy: RoutingStrategy) -> Self {
        Self {
            venues: DashMap::new(),
            default_venue,
            strategy,
        }
    }

    /// Register a venue
    pub fn register_venue(&self, venue: Venue) {
        self.venues.insert(venue.name.clone(), venue);
    }

    /// Route an order to the best venue
    pub fn route(&self, order: &NewOrderRequest) -> RouterDecision {
        // Check if preferred venue is available (from order)
        let candidate_venues: Vec<Venue> = self
            .venues
            .iter()
            .filter(|v| {
                v.available
                    && (v.symbols.is_empty() || v.symbols.contains(&order.symbol))
            })
            .map(|v| v.clone())
            .collect();

        if candidate_venues.is_empty() {
            return RouterDecision {
                venue: self.default_venue.clone(),
                strategy: self.strategy,
                estimated_cost: Decimal::ZERO,
                reasoning: "No venues available, using default".into(),
            };
        }

        // Score each venue
        let mut scores: Vec<VenueScore> = candidate_venues
            .iter()
            .map(|v| self.score_venue(v, order))
            .collect();

        // Sort by score descending
        scores.sort_by(|a, b| b.score.partial_cmp(&a.score).unwrap_or(std::cmp::Ordering::Equal));

        let best = &scores[0];

        RouterDecision {
            venue: best.venue.clone(),
            strategy: self.strategy,
            estimated_cost: best.estimated_cost,
            reasoning: best.reasoning.clone(),
        }
    }

    /// Score a venue for a given order
    fn score_venue(&self, venue: &Venue, order: &NewOrderRequest) -> VenueScore {
        let notional = order.estimated_notional();
        let notional_f64 = notional.to_f64().unwrap_or(0.0);

        let fee_cost = notional_f64 * venue.fee_bps / 10_000.0;
        let rebate = notional_f64 * venue.rebate_bps / 10_000.0;
        let net_cost = fee_cost - rebate;

        match self.strategy {
            RoutingStrategy::LowestCost => {
                let score = rebate - fee_cost; // Higher score = lower net cost
                VenueScore {
                    venue: venue.name.clone(),
                    score,
                    estimated_cost: Decimal::from_f64(net_cost).unwrap_or(Decimal::ZERO),
                    reasoning: format!(
                        "Cost: fee={:.2}bps rebate={:.2}bps net=${:.4}",
                        venue.fee_bps, venue.rebate_bps, net_cost
                    ),
                }
            }
            RoutingStrategy::HighestFill => {
                VenueScore {
                    venue: venue.name.clone(),
                    score: venue.fill_probability,
                    estimated_cost: Decimal::from_f64(net_cost).unwrap_or(Decimal::ZERO),
                    reasoning: format!(
                        "Fill probability: {:.1}%",
                        venue.fill_probability * 100.0
                    ),
                }
            }
            RoutingStrategy::LowestLatency => {
                let score = 1_000_000.0 / venue.avg_latency_us as f64;
                VenueScore {
                    venue: venue.name.clone(),
                    score,
                    estimated_cost: Decimal::from_f64(net_cost).unwrap_or(Decimal::ZERO),
                    reasoning: format!("Latency: {}us", venue.avg_latency_us),
                }
            }
            RoutingStrategy::Smart => {
                // Weighted combination: 40% cost, 35% fill, 25% latency
                let cost_score = (rebate - fee_cost) * 100.0;
                let fill_score = venue.fill_probability * 100.0;
                let latency_score = 50_000.0 / venue.avg_latency_us as f64;

                let score = cost_score * 0.4 + fill_score * 0.35 + latency_score * 0.25;

                VenueScore {
                    venue: venue.name.clone(),
                    score,
                    estimated_cost: Decimal::from_f64(net_cost).unwrap_or(Decimal::ZERO),
                    reasoning: format!(
                        "Smart: cost=${:.4} fill={:.0}% lat={}us → {:.1}",
                        net_cost,
                        venue.fill_probability * 100.0,
                        venue.avg_latency_us,
                        score
                    ),
                }
            }
        }
    }
}

/// Router decision output
#[derive(Debug, Clone)]
pub struct RouterDecision {
    pub venue: Exchange,
    pub strategy: RoutingStrategy,
    pub estimated_cost: Decimal,
    pub reasoning: String,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_order_routing() {
        let router = OrderRouter::new(
            Exchange("NASDAQ".into()),
            RoutingStrategy::Smart,
        );

        router.register_venue(Venue {
            name: Exchange("NASDAQ".into()),
            fee_bps: 0.3,
            rebate_bps: 0.2,
            fill_probability: 0.95,
            avg_latency_us: 500,
            available: true,
            symbols: vec![],
        });

        router.register_venue(Venue {
            name: Exchange("ARCA".into()),
            fee_bps: 0.2,
            rebate_bps: 0.3,
            fill_probability: 0.85,
            avg_latency_us: 300,
            available: true,
            symbols: vec![],
        });

        let order = NewOrderRequest {
            symbol: Symbol("AAPL".into()),
            exchange: Exchange("".into()),
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
            tags: HashMap::new(),
        };

        let decision = router.route(&order);
        assert!(!decision.venue.0.is_empty());
        assert!(!decision.reasoning.is_empty());
    }
}
