// ─────────────────────────────────────────────────────────────
// Order Book - Lock-free, cache-optimized multi-level order book
// ─────────────────────────────────────────────────────────────

use rust_decimal::Decimal;
use std::collections::BTreeMap;

use crate::types::{NanosTimestamp, OrderBookLevel, OrderBookSnapshot, Symbol};

/// A price level in the order book
#[derive(Debug, Clone, Copy)]
struct PriceLevel {
    price: Decimal,
    total_size: f64,
    order_count: u32,
}

/// │ bid side (sorted descending) │ asks side (sorted ascending) │
pub struct OrderBook {
    pub symbol: Symbol,
    /// Bid levels: highest price first (BTreeMap sorted in reverse)
    bids: BTreeMap<Decimal, PriceLevel>,
    /// Ask levels: lowest price first
    asks: BTreeMap<Decimal, PriceLevel>,
    /// Maximum depth to maintain per side
    max_depth: usize,
    /// Timestamp of last update
    pub last_update: NanosTimestamp,
    /// Sequence number of last update
    pub last_sequence: u64,
}

impl OrderBook {
    pub fn new(symbol: Symbol, max_depth: usize) -> Self {
        Self {
            symbol,
            bids: BTreeMap::new(),
            asks: BTreeMap::new(),
            max_depth,
            last_update: NanosTimestamp(0),
            last_sequence: 0,
        }
    }

    /// Update the entire order book from a snapshot
    pub fn apply_snapshot(&mut self, snapshot: &OrderBookSnapshot) {
        self.bids.clear();
        self.asks.clear();

        for level in &snapshot.bids {
            self.bids.insert(
                level.price,
                PriceLevel {
                    price: level.price,
                    total_size: level.size,
                    order_count: level.order_count,
                },
            );
        }

        for level in &snapshot.asks {
            self.asks.insert(
                level.price,
                PriceLevel {
                    price: level.price,
                    total_size: level.size,
                    order_count: level.order_count,
                },
            );
        }

        self.trim();
        self.last_update = snapshot.timestamp;
        self.last_sequence = snapshot.sequence_number;
    }

    /// Update a single price level (incremental update)
    pub fn update_level(&mut self, side: OrderBookSide, price: Decimal, size: f64, count: u32) {
        let book = match side {
            OrderBookSide::Bid => &mut self.bids,
            OrderBookSide::Ask => &mut self.asks,
        };

        if size.abs() < f64::EPSILON {
            // Remove level
            book.remove(&price);
        } else {
            // Upsert level
            book.insert(
                price,
                PriceLevel {
                    price,
                    total_size: size,
                    order_count: count,
                },
            );
        }

        self.trim();
    }

    /// Trim excess levels beyond max_depth
    fn trim(&mut self) {
        // Bids: keep highest N prices (largest keys)
        while self.bids.len() > self.max_depth {
            if let Some(&min_key) = self.bids.keys().next() {
                self.bids.remove(&min_key);
            }
        }

        // Asks: keep lowest N prices (smallest keys)
        while self.asks.len() > self.max_depth {
            if let Some(&max_key) = self.asks.keys().next_back() {
                self.asks.remove(&max_key);
            }
        }
    }

    /// Best bid price
    pub fn best_bid(&self) -> Option<&PriceLevel> {
        self.bids.values().next_back() // Highest bid (last in BTreeMap)
    }

    /// Best ask price
    pub fn best_ask(&self) -> Option<&PriceLevel> {
        self.asks.values().next() // Lowest ask (first in BTreeMap)
    }

    /// Mid price
    pub fn mid_price(&self) -> Option<Decimal> {
        match (self.best_bid(), self.best_ask()) {
            (Some(bid), Some(ask)) => {
                Some((bid.price + ask.price) / Decimal::from(2))
            }
            _ => None,
        }
    }

    /// Spread in price units
    pub fn spread(&self) -> Option<Decimal> {
        match (self.best_bid(), self.best_ask()) {
            (Some(bid), Some(ask)) => Some(ask.price - bid.price),
            _ => None,
        }
    }

    /// Spread in basis points
    pub fn spread_bps(&self) -> Option<f64> {
        let mid = self.mid_price()?;
        let spread = self.spread()?;
        if mid.is_zero() {
            return None;
        }
        let bps = (spread / mid).to_f64().unwrap_or(0.0) * 10_000.0;
        Some(bps)
    }

    /// Calculate market impact (in price units) for a given size
    /// Positive size = buy (walks up asks), negative = sell (walks down bids)
    /// Calculate market impact (in price units) for executing a given size.
    /// Positive size = buy (walks up asks), negative = sell (walks down bids).
    /// Returns `None` if there is insufficient liquidity to fill the full size.
    pub fn market_impact(&self, size: f64) -> Option<Decimal> {
        if size.abs() < f64::EPSILON {
            return Some(Decimal::ZERO);
        }

        let is_buy = size > 0.0;
        let mut remaining = size.abs();
        let mut total_cost = Decimal::ZERO;
        let mut filled = 0.0;

        // Walk up asks (buy) or down bids (sell) until filled
        if is_buy {
            for (_, level) in self.asks.iter() {
                if remaining <= 0.0 {
                    break;
                }
                let take = remaining.min(level.total_size);
                remaining -= take;
                filled += take;
                total_cost += level.price
                    * Decimal::from_f64(take).unwrap_or(Decimal::ZERO);
            }
        } else {
            for (_, level) in self.bids.iter().rev() {
                if remaining <= 0.0 {
                    break;
                }
                let take = remaining.min(level.total_size);
                remaining -= take;
                filled += take;
                total_cost += level.price
                    * Decimal::from_f64(take).unwrap_or(Decimal::ZERO);
            }
        }

        if remaining > 0.0 {
            return None; // Not enough liquidity
        }

        let avg_price =
            total_cost / Decimal::from_f64(filled).unwrap_or(Decimal::ONE);
        let mid = self.mid_price()?;

        let impact = if is_buy {
            avg_price - mid
        } else {
            mid - avg_price
        };

        Some(impact)
    }

    /// Get the top N levels as a snapshot
    pub fn snapshot(&self, depth: usize) -> OrderBookSnapshot {
        let depth = depth.min(self.max_depth);

        OrderBookSnapshot {
            symbol: self.symbol.clone(),
            exchange: crate::types::Exchange("".into()),
            timestamp: self.last_update,
            bids: self
                .bids
                .values()
                .rev()
                .take(depth)
                .map(|l| OrderBookLevel {
                    price: l.price,
                    size: l.total_size,
                    order_count: l.order_count,
                })
                .collect(),
            asks: self
                .asks
                .values()
                .take(depth)
                .map(|l| OrderBookLevel {
                    price: l.price,
                    size: l.total_size,
                    order_count: l.order_count,
                })
                .collect(),
            sequence_number: self.last_sequence,
        }
    }

    /// Number of levels on each side
    pub fn depth(&self) -> (usize, usize) {
        (self.bids.len(), self.asks.len())
    }

    /// Is the book crossed? (best bid >= best ask)
    pub fn is_crossed(&self) -> bool {
        match (self.best_bid(), self.best_ask()) {
            (Some(bid), Some(ask)) => bid.price >= ask.price,
            _ => false,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OrderBookSide {
    Bid,
    Ask,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::Exchange;

    fn make_level(price: f64, size: f64, count: u32) -> OrderBookLevel {
        OrderBookLevel {
            price: Decimal::from_f64(price).unwrap(),
            size,
            order_count: count,
        }
    }

    #[test]
    fn test_order_book_snapshot() {
        let mut ob = OrderBook::new(Symbol("AAPL".into()), 10);

        let snapshot = OrderBookSnapshot {
            symbol: Symbol("AAPL".into()),
            exchange: Exchange("NASDAQ".into()),
            timestamp: NanosTimestamp::now(),
            bids: vec![
                make_level(150.0, 100.0, 5),
                make_level(149.5, 200.0, 3),
                make_level(149.0, 500.0, 10),
            ],
            asks: vec![
                make_level(150.5, 150.0, 4),
                make_level(151.0, 300.0, 6),
                make_level(151.5, 100.0, 2),
            ],
            sequence_number: 1,
        };

        ob.apply_snapshot(&snapshot);

        assert_eq!(ob.best_bid().unwrap().price, Decimal::from_f64(150.0).unwrap());
        assert_eq!(ob.best_ask().unwrap().price, Decimal::from_f64(150.5).unwrap());
        assert!((ob.mid_price().unwrap().to_f64().unwrap() - 150.25).abs() < 0.001);
        assert!(!ob.is_crossed());
    }

    #[test]
    fn test_market_impact() {
        let mut ob = OrderBook::new(Symbol("AAPL".into()), 10);

        let snapshot = OrderBookSnapshot {
            symbol: Symbol("AAPL".into()),
            exchange: Exchange("NASDAQ".into()),
            timestamp: NanosTimestamp::now(),
            bids: vec![make_level(150.0, 100.0, 3), make_level(149.5, 500.0, 5)],
            asks: vec![make_level(150.5, 100.0, 3), make_level(151.0, 500.0, 5)],
            sequence_number: 1,
        };

        ob.apply_snapshot(&snapshot);

        // Buying 50 shares should be filled at 150.5
        let impact = ob.market_impact(50.0);
        assert!(impact.is_some());
        assert!((impact.unwrap().to_f64().unwrap() - 0.25).abs() < 0.01);

        // Buying 1000 shares: 100 @ 150.5 + 500 @ 151.0 = partial fill
        let impact = ob.market_impact(1000.0);
        assert!(impact.is_some());
    }
}
