// ─────────────────────────────────────────────────────────────
// Feed Handler - Kafka/Redpanda market data ingestion
// ─────────────────────────────────────────────────────────────

use std::sync::Arc;
use tokio::sync::broadcast;

use crate::config::KafkaConfig;
use crate::types::{Quote, Trade};

/// Represents parsed market data from a feed
#[derive(Debug, Clone)]
pub enum MarketDataEvent {
    Quote(Quote),
    Trade(Trade),
}

/// Feed handler manager - coordinates multiple feed sources
pub struct FeedHandlerManager {
    /// Broadcast channel for parsed market data events
    market_data_tx: Option<broadcast::Sender<MarketDataEvent>>,
    /// Is the feed handler running?
    running: bool,
}

impl FeedHandlerManager {
    pub fn new() -> Self {
        Self {
            market_data_tx: None,
            running: false,
        }
    }

    /// Create a new broadcast channel for market data
    pub fn create_channel(&mut self, capacity: usize) -> broadcast::Receiver<MarketDataEvent> {
        let (tx, rx) = broadcast::channel(capacity);
        self.market_data_tx = Some(tx);
        rx
    }

    /// Simulated market data feed (for testing/development)
    #[cfg(feature = "kafka")]
    pub async fn start_kafka_feed(
        &mut self,
        config: &KafkaConfig,
    ) -> anyhow::Result<()> {
        use rdkafka::config::ClientConfig;
        use rdkafka::consumer::{Consumer, StreamConsumer};
        use rdkafka::Message;

        self.running = true;

        let consumer: StreamConsumer = ClientConfig::new()
            .set("bootstrap.servers", &config.brokers)
            .set("group.id", &config.group_id)
            .set("auto.offset.reset", &config.auto_offset_reset)
            .set("enable.auto.commit", "false")
            .set("session.timeout.ms", &config.session_timeout_ms.to_string())
            .set("max.poll.interval.ms", &config.max_poll_interval_ms.to_string())
            .set("fetch.min.bytes", &config.fetch_min_bytes.to_string())
            .set("fetch.wait.max.ms", &config.fetch_max_wait_ms.to_string())
            .create()?;

        consumer.subscribe(&[&config.market_data_topic])?;

        tracing::info!(
            "Kafka feed handler started: topic={}, brokers={}",
            config.market_data_topic,
            config.brokers
        );

        // This would be spawned as a background task
        // For now, return the consumer for the caller to drive
        Ok(())
    }

    /// Check if feed handler is running
    pub fn is_running(&self) -> bool {
        self.running
    }
}

/// Simulated market data feed for testing
pub struct SimulatedFeed {
    symbols: Vec<String>,
    base_prices: std::collections::HashMap<String, f64>,
}

impl SimulatedFeed {
    pub fn new(symbols: Vec<String>) -> Self {
        use rand::Rng;
        let mut rng = rand::thread_rng();

        let base_prices: std::collections::HashMap<String, f64> = symbols
            .iter()
            .map(|s| (s.clone(), rng.gen_range(50.0..500.0)))
            .collect();

        Self {
            symbols,
            base_prices,
        }
    }

    /// Generate a random quote for testing
    pub fn generate_quote(&self, symbol: &str) -> Quote {
        use rand::Rng;
        let mut rng = rand::thread_rng();

        let base = self.base_prices.get(symbol).copied().unwrap_or(100.0);
        let jitter = rng.gen_range(-0.5..0.5);
        let mid = base + jitter;
        let spread = base * rng.gen_range(0.0001..0.001);

        Quote {
            symbol: crate::types::Symbol::from(symbol),
            exchange: crate::types::Exchange("SIM".into()),
            timestamp: crate::types::NanosTimestamp::now(),
            bid_price: rust_decimal::Decimal::from_f64(mid - spread / 2.0).unwrap(),
            bid_size: rng.gen_range(100.0..1000.0),
            ask_price: rust_decimal::Decimal::from_f64(mid + spread / 2.0).unwrap(),
            ask_size: rng.gen_range(100.0..1000.0),
            condition: crate::types::QuoteCondition::Normal,
            sequence_number: rng.gen_range(1..1_000_000),
        }
    }

    /// Generate a random trade for testing
    pub fn generate_trade(&self, symbol: &str) -> Trade {
        use rand::Rng;
        let mut rng = rand::thread_rng();

        let base = self.base_prices.get(symbol).copied().unwrap_or(100.0);
        let price = base + rng.gen_range(-0.5..0.5);

        Trade {
            symbol: crate::types::Symbol::from(symbol),
            exchange: crate::types::Exchange("SIM".into()),
            timestamp: crate::types::NanosTimestamp::now(),
            price: rust_decimal::Decimal::from_f64(price).unwrap(),
            size: rng.gen_range(10.0..500.0),
            condition: crate::types::TradeCondition::Normal,
            sequence_number: rng.gen_range(1..1_000_000),
            trade_id: rng.gen_range(1..1_000_000),
        }
    }
}
