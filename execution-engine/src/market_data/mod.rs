// ─────────────────────────────────────────────────────────────
// Market Data Module
// Real-time market data ingestion, normalization, and order book management
// ─────────────────────────────────────────────────────────────

pub mod feed_handler;
pub mod order_book;
pub mod tick_store;
pub mod normalizer;

use dashmap::DashMap;
use parking_lot::RwLock;
use std::sync::Arc;

use crate::config::MarketDataConfig;
use crate::types::{NanosTimestamp, Symbol};

/// Aggregated market data state across all symbols
pub struct MarketDataHub {
    /// Order book pool (one per symbol)
    pub order_books: DashMap<Symbol, Arc<RwLock<order_book::OrderBook>>>,
    /// Tick store for historical queries
    pub tick_store: Arc<RwLock<tick_store::TickStore>>,
    /// Feed handler manager
    pub feed_handler: feed_handler::FeedHandlerManager,
    /// Configuration
    pub config: MarketDataConfig,
    /// Last update timestamp per symbol (used for stale detection)
    pub last_update: DashMap<Symbol, NanosTimestamp>,
}

impl MarketDataHub {
    pub fn new(config: MarketDataConfig) -> Self {
        // Pre-allocate order books for subscribed symbols
        let order_books = DashMap::with_capacity(config.symbols.len());
        for symbol_str in &config.symbols {
            let symbol = Symbol::from(symbol_str.as_str());
            order_books.insert(
                symbol.clone(),
                Arc::new(RwLock::new(order_book::OrderBook::new(
                    symbol,
                    config.order_book_depth,
                ))),
            );
        }

        Self {
            order_books,
            tick_store: Arc::new(RwLock::new(tick_store::TickStore::new(
                config.tick_store_capacity,
            ))),
            feed_handler: feed_handler::FeedHandlerManager::new(),
            config,
            last_update: DashMap::new(),
        }
    }

    /// Check if a symbol's data is stale (no update within threshold)
    pub fn is_stale(&self, symbol: &Symbol) -> bool {
        if let Some(last_ts) = self.last_update.get(symbol) {
            let now = NanosTimestamp::now();
            let age_ns = now.as_nanos() - last_ts.as_nanos();
            let threshold_ns = self.config.stale_threshold_ms as i64 * 1_000_000;
            age_ns > threshold_ns
        } else {
            true // No data ever received = stale
        }
    }

    /// Get or create an order book for a symbol
    pub fn get_order_book(&self, symbol: &Symbol) -> Arc<RwLock<order_book::OrderBook>> {
        self.order_books
            .entry(symbol.clone())
            .or_insert_with(|| {
                Arc::new(RwLock::new(order_book::OrderBook::new(
                    symbol.clone(),
                    self.config.order_book_depth,
                )))
            })
            .clone()
    }
}
