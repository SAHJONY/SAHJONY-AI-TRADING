// ─────────────────────────────────────────────────────────────
// Data Normalizer - normalize market data from different sources
// ─────────────────────────────────────────────────────────────

use crate::types::{Quote, Trade};

/// Exchange-specific normalization rules
#[derive(Debug, Clone)]
pub struct ExchangeNormalizer {
    /// Multiplier to convert to standard lots
    pub lot_multiplier: f64,
    /// Price adjustment (e.g., for stock splits)
    pub price_multiplier: f64,
    /// Minimum price increment (tick size)
    pub tick_size: f64,
    /// Round lots (minimum trade quantity)
    pub round_lot: f64,
}

impl Default for ExchangeNormalizer {
    fn default() -> Self {
        Self {
            lot_multiplier: 1.0,
            price_multiplier: 1.0,
            tick_size: 0.01,
            round_lot: 1.0,
        }
    }
}

/// Main normalizer for cleaning and standardizing market data
pub struct Normalizer {
    /// Per-exchange normalizers
    exchange_rules: std::collections::HashMap<String, ExchangeNormalizer>,
    /// Max allowed price change per tick (circuit breaker for bad data)
    max_tick_change_pct: f64,
    /// Minimum valid price
    min_price: f64,
    /// Maximum valid price
    max_price: f64,
}

impl Normalizer {
    pub fn new() -> Self {
        Self {
            exchange_rules: std::collections::HashMap::new(),
            max_tick_change_pct: 10.0,
            min_price: 0.01,
            max_price: 1_000_000.0,
        }
    }

    /// Add exchange-specific normalization rules
    pub fn add_exchange(&mut self, exchange: &str, rules: ExchangeNormalizer) {
        self.exchange_rules.insert(exchange.to_string(), rules);
    }

    /// Normalize a quote (return None if the quote should be discarded)
    pub fn normalize_quote(&self, quote: &Quote) -> Option<Quote> {
        let mut q = quote.clone();
        let rules = self
            .exchange_rules
            .get(&quote.exchange.0)
            .cloned()
            .unwrap_or_default();

        // Apply price multiplier
        q.bid_price *= rust_decimal::Decimal::from_f64(rules.price_multiplier)?;
        q.ask_price *= rust_decimal::Decimal::from_f64(rules.price_multiplier)?;

        // Round to tick size
        if rules.tick_size > 0.0 {
            q.bid_price = round_to_tick(q.bid_price, rules.tick_size);
            q.ask_price = round_to_tick(q.ask_price, rules.tick_size);
        }

        // Validate
        if !self.is_valid_quote(&q) {
            return None;
        }

        Some(q)
    }

    /// Normalize a trade
    pub fn normalize_trade(&self, trade: &Trade) -> Option<Trade> {
        let mut t = trade.clone();
        let rules = self
            .exchange_rules
            .get(&trade.exchange.0)
            .cloned()
            .unwrap_or_default();

        t.price *= rust_decimal::Decimal::from_f64(rules.price_multiplier)?;

        if rules.tick_size > 0.0 {
            t.price = round_to_tick(t.price, rules.tick_size);
        }

        if !self.is_valid_trade(&t) {
            return None;
        }

        Some(t)
    }

    /// Validate a quote
    fn is_valid_quote(&self, quote: &Quote) -> bool {
        let bid = quote.bid_price.to_f64().unwrap_or(0.0);
        let ask = quote.ask_price.to_f64().unwrap_or(0.0);

        bid >= self.min_price
            && ask >= self.min_price
            && bid <= self.max_price
            && ask <= self.max_price
            && bid < ask // Not crossed
            && quote.bid_size > 0.0
            && quote.ask_size > 0.0
    }

    /// Validate a trade
    fn is_valid_trade(&self, trade: &Trade) -> bool {
        let price = trade.price.to_f64().unwrap_or(0.0);
        price >= self.min_price
            && price <= self.max_price
            && trade.size > 0.0
    }

    /// Check if a tick change is suspicious (potential bad data)
    pub fn is_suspicious_change(&self, prev_price: f64, new_price: f64) -> bool {
        if prev_price <= 0.0 {
            return false;
        }
        let change_pct = ((new_price - prev_price) / prev_price).abs() * 100.0;
        change_pct > self.max_tick_change_pct
    }
}

/// Round a decimal price to the nearest tick size
fn round_to_tick(price: rust_decimal::Decimal, tick_size: f64) -> rust_decimal::Decimal {
    let tick = rust_decimal::Decimal::from_f64(tick_size).unwrap_or(rust_decimal::Decimal::ONE);
    (price / tick).round() * tick
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_round_to_tick() {
        let price = rust_decimal::Decimal::from_f64(150.1234).unwrap();
        let rounded = round_to_tick(price, 0.01);
        assert_eq!(rounded, rust_decimal::Decimal::from_f64(150.12).unwrap());

        let price = rust_decimal::Decimal::from_f64(150.125).unwrap();
        let rounded = round_to_tick(price, 0.01);
        assert_eq!(rounded, rust_decimal::Decimal::from_f64(150.13).unwrap());
    }

    #[test]
    fn test_normalize_rejects_bad_data() {
        let normalizer = Normalizer::new();
        let bad_quote = Quote {
            symbol: crate::types::Symbol("AAPL".into()),
            exchange: crate::types::Exchange("NASDAQ".into()),
            timestamp: crate::types::NanosTimestamp::now(),
            bid_price: rust_decimal::Decimal::from_f64(150.0).unwrap(),
            ask_price: rust_decimal::Decimal::from_f64(149.0).unwrap(), // Crossed!
            bid_size: 100.0,
            ask_size: 200.0,
            condition: crate::types::QuoteCondition::Normal,
            sequence_number: 1,
        };

        assert!(normalizer.normalize_quote(&bad_quote).is_none());
    }
}
