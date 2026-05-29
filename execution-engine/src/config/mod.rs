// ─────────────────────────────────────────────────────────────
// Configuration module - typed configuration with validation
// ─────────────────────────────────────────────────────────────

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Root application configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppConfig {
    pub engine: EngineConfig,
    pub market_data: MarketDataConfig,
    pub risk: RiskConfig,
    pub kafka: Option<KafkaConfig>,
    pub questdb: Option<QuestDbConfig>,
    pub monitoring: MonitoringConfig,
}

impl AppConfig {
    /// Load configuration from file
    pub fn from_file(path: &str) -> anyhow::Result<Self> {
        let config_builder = config::Config::builder()
            .add_source(config::File::with_name(path).required(true))
            .add_source(config::Environment::with_prefix("EXEC_ENGINE").separator("__"))
            .build()?;

        Ok(config_builder.try_deserialize()?)
    }

    /// Create default configuration
    pub fn default_config() -> Self {
        Self {
            engine: EngineConfig::default(),
            market_data: MarketDataConfig::default(),
            risk: RiskConfig::default(),
            kafka: Some(KafkaConfig::default()),
            questdb: Some(QuestDbConfig::default()),
            monitoring: MonitoringConfig::default(),
        }
    }

    /// Validate configuration
    pub fn validate(&self) -> Vec<String> {
        let mut errors = Vec::new();

        if self.engine.max_orders_per_second == 0 {
            errors.push("max_orders_per_second must be > 0".into());
        }
        if self.engine.reconnect_attempts == 0 {
            errors.push("reconnect_attempts must be > 0".into());
        }

        for limit in &self.risk.limits {
            if limit.soft_threshold > limit.hard_threshold {
                errors.push(format!(
                    "Risk limit '{}': soft_threshold ({}) exceeds hard_threshold ({})",
                    limit.name, limit.soft_threshold, limit.hard_threshold
                ));
            }
        }

        errors
    }
}

// ── Engine Configuration ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EngineConfig {
    /// Unique instance identifier
    pub instance_id: String,
    /// CPU core to pin the main trading thread to (-1 = no pinning)
    pub cpu_pin: i32,
    /// Maximum orders per second (rate limiter)
    pub max_orders_per_second: u32,
    /// Enable audit logging
    pub audit_enabled: bool,
    /// Audit log output path
    pub audit_path: PathBuf,
    /// Heartbeat interval in milliseconds
    pub heartbeat_interval_ms: u64,
    /// Heartbeat miss threshold before triggering kill switch
    pub heartbeat_miss_threshold: u32,
    /// Reconnect attempts for exchange connections
    pub reconnect_attempts: u32,
    /// Reconnect backoff base (milliseconds)
    pub reconnect_backoff_ms: u64,
    /// Trading enabled flag
    pub trading_enabled: bool,
}

impl Default for EngineConfig {
    fn default() -> Self {
        Self {
            instance_id: format!("exec-engine-{}", uuid::Uuid::new_v4()),
            cpu_pin: -1,
            max_orders_per_second: 1000,
            audit_enabled: true,
            audit_path: PathBuf::from("./audit_logs"),
            heartbeat_interval_ms: 100,
            heartbeat_miss_threshold: 5,
            reconnect_attempts: 10,
            reconnect_backoff_ms: 100,
            trading_enabled: false,
        }
    }
}

// ── Market Data Configuration ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketDataConfig {
    /// Subscribed symbols
    pub symbols: Vec<String>,
    /// Subscribed exchanges
    pub exchanges: Vec<String>,
    /// Order book depth to maintain
    pub order_book_depth: usize,
    /// Max tickers to track concurrently
    pub max_symbols: usize,
    /// Tick store capacity (max ticks per symbol in memory)
    pub tick_store_capacity: usize,
    /// Stale data threshold (milliseconds) - if no update within this, mark as stale
    pub stale_threshold_ms: u64,
    /// Whether to build OHLCV bars
    pub build_bars: bool,
    /// Bar durations to build (e.g., 1 min, 5 min, 15 min, 1 hour, 1 day)
    pub bar_durations_ns: Vec<i64>,
}

impl Default for MarketDataConfig {
    fn default() -> Self {
        Self {
            symbols: vec![],
            exchanges: vec!["NASDAQ".into(), "NYSE".into()],
            order_book_depth: 10,
            max_symbols: 10_000,
            tick_store_capacity: 100_000,
            stale_threshold_ms: 5_000,
            build_bars: true,
            bar_durations_ns: vec![
                60_000_000_000,       // 1 minute
                300_000_000_000,      // 5 minutes
                900_000_000_000,      // 15 minutes
                3_600_000_000_000,    // 1 hour
                86_400_000_000_000,   // 1 day
            ],
        }
    }
}

// ── Kafka/Redpanda Configuration ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KafkaConfig {
    /// Bootstrap servers (comma-separated)
    pub brokers: String,
    /// Consumer group ID
    pub group_id: String,
    /// Topics
    pub market_data_topic: String,
    pub order_events_topic: String,
    pub risk_events_topic: String,
    pub audit_topic: String,
    pub heartbeat_topic: String,
    /// Auto offset reset ("earliest" or "latest")
    pub auto_offset_reset: String,
    /// Enable auto commit
    pub enable_auto_commit: bool,
    /// Session timeout (ms)
    pub session_timeout_ms: u32,
    /// Max poll interval (ms)
    pub max_poll_interval_ms: u32,
    /// Fetch min bytes
    pub fetch_min_bytes: i32,
    /// Fetch max wait (ms)
    pub fetch_max_wait_ms: i32,
    /// Producer linger (ms)
    pub linger_ms: i32,
    /// Producer batch size
    pub batch_size: i32,
    /// Producer acks ("0", "1", "all")
    pub acks: String,
    /// Enable idempotent producer
    pub enable_idempotence: bool,
}

impl Default for KafkaConfig {
    fn default() -> Self {
        Self {
            brokers: "localhost:9092".into(),
            group_id: "execution-engine".into(),
            market_data_topic: "market.data".into(),
            order_events_topic: "order.events".into(),
            risk_events_topic: "risk.events".into(),
            audit_topic: "audit.log".into(),
            heartbeat_topic: "system.heartbeat".into(),
            auto_offset_reset: "latest".into(),
            enable_auto_commit: false,
            session_timeout_ms: 10_000,
            max_poll_interval_ms: 300_000,
            fetch_min_bytes: 1,
            fetch_max_wait_ms: 10,
            linger_ms: 0,           // Send immediately
            batch_size: 16_384,     // 16KB batches
            acks: "all".into(),
            enable_idempotence: true,
        }
    }
}

// ── QuestDB Configuration ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuestDbConfig {
    /// Host URL for ILP (InfluxDB Line Protocol)
    pub ilp_host: String,
    /// ILP port
    pub ilp_port: u16,
    /// REST API endpoint (for queries)
    pub rest_url: String,
    /// Batch size for ILP writes
    pub batch_size: usize,
    /// Flush interval (ms)
    pub flush_interval_ms: u64,
    /// Enable for historical data store
    pub enabled: bool,
}

impl Default for QuestDbConfig {
    fn default() -> Self {
        Self {
            ilp_host: "http://localhost".into(),
            ilp_port: 9009,
            rest_url: "http://localhost:9000".into(),
            batch_size: 10_000,
            flush_interval_ms: 1_000,
            enabled: true,
        }
    }
}

// ── Risk Configuration ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskConfig {
    /// Risk limits
    pub limits: Vec<RiskLimitDef>,
    /// Kelly criterion: fraction of full Kelly to use (0.0–1.0)
    pub kelly_fraction: f64,
    /// VaR confidence level (e.g., 0.95, 0.99)
    pub var_confidence: f64,
    /// VaR lookback window (number of periods)
    pub var_lookback: usize,
    /// Drawdown kill switch threshold (fraction of peak equity)
    pub kill_drawdown_pct: f64,
    /// Soft drawdown threshold (warning only)
    pub warn_drawdown_pct: f64,
    /// Circuit breaker: max consecutive rejections before trip
    pub max_consecutive_rejections: u32,
    /// Circuit breaker: cooldown period after trip (seconds)
    pub circuit_breaker_cooldown_secs: u64,
    /// Risk check timeout (microseconds) - if slower, fail-safe
    pub risk_check_timeout_us: u64,
}

impl Default for RiskConfig {
    fn default() -> Self {
        Self {
            limits: vec![
                RiskLimitDef {
                    name: "max_order_size".into(),
                    limit_type: "max_order_size".into(),
                    soft_threshold: 1000.0,
                    hard_threshold: 5000.0,
                    scope: "global".into(),
                },
                RiskLimitDef {
                    name: "max_position_notional".into(),
                    limit_type: "position_notional".into(),
                    soft_threshold: 1_000_000.0,
                    hard_threshold: 5_000_000.0,
                    scope: "global".into(),
                },
                RiskLimitDef {
                    name: "max_drawdown".into(),
                    limit_type: "max_drawdown_pct".into(),
                    soft_threshold: 10.0,
                    hard_threshold: 25.0,
                    scope: "global".into(),
                },
            ],
            kelly_fraction: 0.25,       // Quarter-Kelly
            var_confidence: 0.99,
            var_lookback: 252,          // 1 year of trading days
            kill_drawdown_pct: 25.0,
            warn_drawdown_pct: 15.0,
            max_consecutive_rejections: 10,
            circuit_breaker_cooldown_secs: 60,
            risk_check_timeout_us: 100, // 100 microseconds max
        }
    }
}

/// Individual risk limit definition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskLimitDef {
    /// Display name
    pub name: String,
    /// Type of limit
    pub limit_type: String,
    /// Soft threshold (warning level)
    pub soft_threshold: f64,
    /// Hard threshold (hard reject)
    pub hard_threshold: f64,
    /// Scope ("global", "symbol", "strategy", "account")
    pub scope: String,
}

// ── Monitoring Configuration ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MonitoringConfig {
    /// Prometheus metrics port
    pub prometheus_port: u16,
    /// Log level
    pub log_level: String,
    /// Enable JSON logging
    pub json_logging: bool,
    /// Metrics flush interval (seconds)
    pub metrics_flush_interval_secs: u64,
}

impl Default for MonitoringConfig {
    fn default() -> Self {
        Self {
            prometheus_port: 9090,
            log_level: "info".into(),
            json_logging: false,
            metrics_flush_interval_secs: 10,
        }
    }
}
