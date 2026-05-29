// ─────────────────────────────────────────────────────────────
// Layer 1 - Execution & Risk Fabric - Main Entry Point
// ─────────────────────────────────────────────────────────────

use execution_engine::config::AppConfig;
use execution_engine::events::consumer::EventConsumer;
use execution_engine::events::producer::EventProducer;
use execution_engine::market_data::MarketDataHub;
use execution_engine::metrics::EngineMetrics;
use execution_engine::order::gateway::GatewayPool;
use execution_engine::order::{OrderManager, OrderRouter};
use execution_engine::risk::RiskEngine;
use execution_engine::types;

use std::sync::Arc;
use tokio::sync::RwLock;

/// Main execution engine state
struct ExecutionEngine {
    config: AppConfig,
    market_data: Arc<MarketDataHub>,
    order_manager: Arc<OrderManager>,
    order_router: Arc<OrderRouter>,
    risk_engine: Arc<RiskEngine>,
    gateway_pool: Arc<RwLock<GatewayPool>>,
    event_producer: Arc<EventProducer>,
    event_consumer: Arc<EventConsumer>,
    metrics: EngineMetrics,
}

impl ExecutionEngine {
    /// Initialize the execution engine from configuration
    async fn new(config: AppConfig) -> anyhow::Result<Self> {
        // Initialize tracing
        metrics::init_logging(&config.monitoring.log_level, config.monitoring.json_logging);

        tracing::info!(
            version = %execution_engine::VERSION,
            instance = %config.engine.instance_id,
            "Execution engine starting"
        );

        // Validate config
        let errors = config.validate();
        if !errors.is_empty() {
            for err in &errors {
                tracing::error!(error = %err, "Config validation failed");
            }
            anyhow::bail!("Configuration validation failed: {:?}", errors);
        }

        // Initialize market data hub
        let market_data = Arc::new(MarketDataHub::new(config.market_data.clone()));

        // Initialize order management
        let order_manager = Arc::new(OrderManager::new());

        // Initialize order router
        let order_router = Arc::new(OrderRouter::new(
            types::Exchange("SMART".into()),
            order::router::RoutingStrategy::Smart,
        ));

        // Initialize risk engine
        let initial_equity = 1_000_000.0; // Configure this from config or state
        let risk_engine = Arc::new(RiskEngine::new(
            config.risk.clone(),
            initial_equity,
        ));

        // Initialize gateway pool
        let gateway_pool = Arc::new(RwLock::new(GatewayPool::new()));

        // Initialize event system
        let producer_config = events::producer::ProducerConfig::default();
        let event_producer = Arc::new(EventProducer::new(
            config.kafka.as_ref(),
            producer_config,
        ));

        let event_consumer = Arc::new(EventConsumer::new(10_000));

        // Register audit log handler
        event_consumer.register_handler(Box::new(
            events::consumer::AuditLogHandler::new(
                config.engine.audit_path.clone(),
            ),
        ));

        // Register metrics handler
        event_consumer.register_handler(Box::new(
            events::consumer::MetricsHandler,
        ));

        let metrics = EngineMetrics::new();

        tracing::info!("Execution engine initialized successfully");

        Ok(Self {
            config,
            market_data,
            order_manager,
            order_router,
            risk_engine,
            gateway_pool,
            event_producer,
            event_consumer,
            metrics,
        })
    }

    /// Run the execution engine main loop
    async fn run(&self) -> anyhow::Result<()> {
        tracing::info!("Execution engine running");

        // Spawn heartbeat task — clone values out of `self` for 'static lifetime
        let heartbeat_interval = self.config.engine.heartbeat_interval_ms;
        let event_producer = Arc::clone(&self.event_producer);
        let config_clone = self.config.clone();
        let metrics_for_heartbeat = self.metrics.clone();

        let heartbeat_handle = tokio::spawn(async move {
            let mut interval = tokio::time::interval(
                std::time::Duration::from_millis(heartbeat_interval),
            );

            loop {
                interval.tick().await;

                let heartbeat = events::schema::SystemEvent::Heartbeat(
                    events::schema::HeartbeatEvent {
                        component_id: "execution_engine".into(),
                        instance_id: config_clone.engine.instance_id.clone(),
                        status: if config_clone.engine.trading_enabled {
                            "healthy"
                        } else {
                            "standby"
                        }
                        .into(),
                        uptime_secs: metrics_for_heartbeat.uptime_secs(),
                        active_orders: metrics_for_heartbeat.active_orders.load(
                            std::sync::atomic::Ordering::Relaxed,
                        ),
                        orders_processed: metrics_for_heartbeat
                            .orders_created
                            .load(std::sync::atomic::Ordering::Relaxed),
                        cpu_usage_pct: 0.0, // TODO: measure CPU
                        memory_usage_mb: 0.0, // TODO: measure memory
                        timestamp_ns: types::NanosTimestamp::now().as_nanos(),
                    },
                );

                let _ = event_producer.publish(heartbeat);
            }
        });

        // Spawn Prometheus metrics server — clone values out of `self` for 'static lifetime
        let prometheus_port = self.config.monitoring.prometheus_port;
        let metrics_flush_interval = self.config.monitoring.metrics_flush_interval_secs;
        let metrics_for_reporter = self.metrics.clone();

        let metrics_handle = tokio::spawn(async move {
            // Simple HTTP server for metrics
            // In production, use a proper HTTP framework like axum
            tracing::info!(
                port = prometheus_port,
                "Metrics endpoint ready (Prometheus text format available via stdout)"
            );

            let mut interval = tokio::time::interval(
                std::time::Duration::from_secs(metrics_flush_interval),
            );

            loop {
                interval.tick().await;
                let prom_metrics = metrics_for_reporter.prometheus_metrics();
                tracing::info!(metrics = %prom_metrics, "Metrics snapshot");
            }
        });

        // Wait for shutdown signal
        tracing::info!("Engine running. Press Ctrl+C to stop.");

        tokio::select! {
            _ = signal::ctrl_c() => {
                tracing::info!("Shutdown signal received (Ctrl+C)");
            }
            _ = tokio::signal::ctrl_c() => {
                // Handled above
            }
        }

        // Graceful shutdown
        tracing::info!("Initiating graceful shutdown...");

        // 1. Cancel all open orders
        let cancelled = self.order_manager.cancel_all();
        tracing::info!(count = cancelled, "Orders cancelled");

        // 2. Stop heartbeat
        heartbeat_handle.abort();
        metrics_handle.abort();

        // 3. Final metrics
        let final_metrics = self.metrics.prometheus_metrics();
        tracing::info!(final_metrics = %final_metrics, "Final metrics");

        tracing::info!(
            uptime_secs = self.metrics.uptime_secs(),
            orders_total = self.order_manager.total_order_count(),
            "Execution engine shutdown complete"
        );

        Ok(())
    }

    /// Emergency stop - immediate kill switch
    async fn emergency_stop(&self, reason: &str) {
        tracing::error!(reason = %reason, "EMERGENCY STOP");

        // Activate kill switch
        self.risk_engine.emergency_kill(reason);

        // Cancel all orders
        self.order_manager.cancel_all();

        // Publish kill switch event
        let _ = self.event_producer.publish(
            events::schema::SystemEvent::KillSwitchActivated(
                events::schema::KillSwitchActivatedEvent {
                    reason: reason.to_string(),
                    triggered_by: "system".into(),
                    current_drawdown_pct: self.risk_engine.metrics().current_drawdown_pct,
                    timestamp_ns: types::NanosTimestamp::now().as_nanos(),
                },
            ),
        );
    }
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Parse command line arguments
    let config_path = std::env::args()
        .nth(1)
        .unwrap_or_else(|| "config.toml".to_string());

    // Load configuration
    let config = AppConfig::from_file(&config_path)
        .unwrap_or_else(|e| {
            tracing::warn!(
                config_path = %config_path,
                error = %e,
                "Failed to load config, using defaults"
            );
            AppConfig::default_config()
        });

    // Create and run engine
    let engine = ExecutionEngine::new(config).await?;
    engine.run().await?;

    Ok(())
}
