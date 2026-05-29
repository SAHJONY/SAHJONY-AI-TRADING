// ─────────────────────────────────────────────────────────────
// Metrics & Observability Module
// Prometheus-compatible metrics, structured logging, and health checks
// ─────────────────────────────────────────────────────────────

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

/// Runtime metrics for the execution engine
#[derive(Clone)]
pub struct EngineMetrics {
    /// Total orders created
    pub orders_created: Arc<AtomicU64>,
    /// Total orders filled
    pub orders_filled: Arc<AtomicU64>,
    /// Total orders rejected
    pub orders_rejected: Arc<AtomicU64>,
    /// Total orders cancelled
    pub orders_cancelled: Arc<AtomicU64>,
    /// Total execution reports processed
    pub executions_processed: Arc<AtomicU64>,
    /// Total risk checks performed
    pub risk_checks: Arc<AtomicU64>,
    /// Total risk check rejections
    pub risk_rejections: Arc<AtomicU64>,
    /// Total quotes received
    pub quotes_received: Arc<AtomicU64>,
    /// Total trades received
    pub trades_received: Arc<AtomicU64>,
    /// Total events published
    pub events_published: Arc<AtomicU64>,
    /// Total audit entries written
    pub audit_entries: Arc<AtomicU64>,
    /// Kill switch activations
    pub kill_switches: Arc<AtomicU64>,
    /// Circuit breaker trips
    pub circuit_trips: Arc<AtomicU64>,
    /// Current active orders
    pub active_orders: Arc<AtomicU64>,
    /// Engine start time
    pub start_time: Instant,
}

impl EngineMetrics {
    pub fn new() -> Self {
        Self {
            orders_created: Arc::new(AtomicU64::new(0)),
            orders_filled: Arc::new(AtomicU64::new(0)),
            orders_rejected: Arc::new(AtomicU64::new(0)),
            orders_cancelled: Arc::new(AtomicU64::new(0)),
            executions_processed: Arc::new(AtomicU64::new(0)),
            risk_checks: Arc::new(AtomicU64::new(0)),
            risk_rejections: Arc::new(AtomicU64::new(0)),
            quotes_received: Arc::new(AtomicU64::new(0)),
            trades_received: Arc::new(AtomicU64::new(0)),
            events_published: Arc::new(AtomicU64::new(0)),
            audit_entries: Arc::new(AtomicU64::new(0)),
            kill_switches: Arc::new(AtomicU64::new(0)),
            circuit_trips: Arc::new(AtomicU64::new(0)),
            active_orders: Arc::new(AtomicU64::new(0)),
            start_time: Instant::now(),
        }
    }

    /// Increment a counter
    pub fn inc(&self, counter: &Arc<AtomicU64>) {
        counter.fetch_add(1, Ordering::Relaxed);
    }

    /// Decrement a counter
    pub fn dec(&self, counter: &Arc<AtomicU64>) {
        counter.fetch_sub(1, Ordering::Relaxed);
    }

    /// Get uptime in seconds
    pub fn uptime_secs(&self) -> u64 {
        self.start_time.elapsed().as_secs()
    }

    /// Get metrics as a key-value map for Prometheus
    pub fn prometheus_metrics(&self) -> String {
        let mut output = String::new();

        macro_rules! metric {
            ($name:expr, $type:expr, $value:expr) => {
                output.push_str(&format!(
                    "# HELP {} {}\n# TYPE {} {}\n{} {}\n",
                    $name, "", $name, $type, $name, $value
                ));
            };
        }

        let load = |c: &Arc<AtomicU64>| c.load(Ordering::Relaxed);

        metric!("execution_engine_orders_created_total", "counter", load(&self.orders_created));
        metric!("execution_engine_orders_filled_total", "counter", load(&self.orders_filled));
        metric!("execution_engine_orders_rejected_total", "counter", load(&self.orders_rejected));
        metric!("execution_engine_orders_cancelled_total", "counter", load(&self.orders_cancelled));
        metric!("execution_engine_executions_total", "counter", load(&self.executions_processed));
        metric!("execution_engine_risk_checks_total", "counter", load(&self.risk_checks));
        metric!("execution_engine_risk_rejections_total", "counter", load(&self.risk_rejections));
        metric!("execution_engine_quotes_received_total", "counter", load(&self.quotes_received));
        metric!("execution_engine_trades_received_total", "counter", load(&self.trades_received));
        metric!("execution_engine_events_published_total", "counter", load(&self.events_published));
        metric!("execution_engine_kill_switches_total", "counter", load(&self.kill_switches));
        metric!("execution_engine_circuit_trips_total", "counter", load(&self.circuit_trips));
        metric!("execution_engine_active_orders", "gauge", load(&self.active_orders));
        metric!("execution_engine_uptime_seconds", "gauge", self.uptime_secs());

        output
    }
}

/// Performance timing helper for latency measurement
pub struct LatencyTimer {
    start: Instant,
    label: String,
}

impl LatencyTimer {
    pub fn new(label: &str) -> Self {
        Self {
            start: Instant::now(),
            label: label.to_string(),
        }
    }

    /// Record the elapsed time and log it
    pub fn record(self) -> Duration {
        let elapsed = self.start.elapsed();
        tracing::debug!(
            label = %self.label,
            elapsed_us = elapsed.as_micros(),
            "Timer recorded"
        );
        elapsed
    }

    /// Record with a specific threshold for warnings
    pub fn record_with_threshold(self, warn_threshold_us: u64) -> Duration {
        let elapsed = self.start.elapsed();
        if elapsed.as_micros() > warn_threshold_us as u128 {
            tracing::warn!(
                label = %self.label,
                elapsed_us = elapsed.as_micros(),
                threshold_us = warn_threshold_us,
                "Latency threshold exceeded"
            );
        }
        elapsed
    }
}

impl Drop for LatencyTimer {
    fn drop(&mut self) {
        let elapsed = self.start.elapsed();
        tracing::trace!(
            label = %self.label,
            elapsed_us = elapsed.as_micros(),
            "Timer dropped"
        );
    }
}

/// Initialize the tracing/logging subsystem
pub fn init_logging(log_level: &str, json: bool) {
    use tracing_subscriber::{fmt, EnvFilter};

    let env_filter = EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| EnvFilter::new(log_level));

    if json {
        tracing_subscriber::fmt()
            .with_env_filter(env_filter)
            .json()
            .with_current_span(true)
            .with_span_list(true)
            .init();
    } else {
        fmt()
            .with_env_filter(env_filter)
            .with_target(false)
            .with_thread_ids(true)
            .with_thread_names(true)
            .init();
    }
}
