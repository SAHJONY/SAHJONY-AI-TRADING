// ─────────────────────────────────────────────────────────────
// Event Consumer - Kafka/Redpanda event consumption
// ─────────────────────────────────────────────────────────────

use std::sync::Arc;
use tokio::sync::broadcast;

use crate::config::KafkaConfig;
use super::schema::SystemEvent;

/// Event handler trait - implement for different event consumers
pub trait EventHandler: Send + Sync {
    /// Handle a single event
    fn handle(&self, event: &SystemEvent) -> Result<(), EventHandlerError>;

    /// Events this handler is interested in
    fn interested_in(&self) -> Vec<&'static str>;
}

#[derive(Debug, thiserror::Error)]
pub enum EventHandlerError {
    #[error("Handler error: {0}")]
    HandlerError(String),
    #[error("Event ignored")]
    Ignored,
}

/// Event consumer - subscribes to events and dispatches to handlers
pub struct EventConsumer {
    /// Broadcast channel for in-process event distribution
    broadcast_tx: broadcast::Sender<SystemEvent>,
    /// Registered handlers
    handlers: parking_lot::RwLock<Vec<Box<dyn EventHandler>>>,
}

impl EventConsumer {
    /// Create a new event consumer
    pub fn new(buffer_size: usize) -> Self {
        let (tx, _) = broadcast::channel(buffer_size);

        Self {
            broadcast_tx: tx,
            handlers: parking_lot::RwLock::new(Vec::new()),
        }
    }

    /// Subscribe to all events (returns a receiver)
    pub fn subscribe(&self) -> broadcast::Receiver<SystemEvent> {
        self.broadcast_tx.subscribe()
    }

    /// Register an event handler
    pub fn register_handler(&self, handler: Box<dyn EventHandler>) {
        self.handlers.write().push(handler);
    }

    /// Dispatch an event to all registered handlers
    pub fn dispatch(&self, event: SystemEvent) {
        // Send to broadcast channel (non-blocking)
        let _ = self.broadcast_tx.send(event.clone());

        // Dispatch to registered handlers
        let handlers = self.handlers.read();
        for handler in handlers.iter() {
            let interested = handler.interested_in();
            if interested.contains(&event.event_type_tag()) || interested.is_empty() {
                if let Err(e) = handler.handle(&event) {
                    match e {
                        EventHandlerError::Ignored => {}
                        _ => tracing::warn!(
                            event_type = %event.event_type_tag(),
                            error = %e,
                            "Event handler error"
                        ),
                    }
                }
            }
        }
    }
}

// ── Built-in Handlers ──

/// Audit log handler - writes all events to persistent storage
pub struct AuditLogHandler {
    log_dir: std::path::PathBuf,
}

impl AuditLogHandler {
    pub fn new(log_dir: std::path::PathBuf) -> Self {
        // Create directory if not exists
        let _ = std::fs::create_dir_all(&log_dir);
        Self { log_dir }
    }
}

impl EventHandler for AuditLogHandler {
    fn handle(&self, event: &SystemEvent) -> Result<(), EventHandlerError> {
        let bytes = event.to_json_bytes();

        // Write to daily rotating log file
        let today = chrono::Utc::now().format("%Y-%m-%d");
        let filename = self.log_dir.join(format!("audit-{}.jsonl", today));

        use std::io::Write;
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&filename)
            .map_err(|e| EventHandlerError::HandlerError(e.to_string()))?;

        writeln!(file, "{}", String::from_utf8_lossy(&bytes))
            .map_err(|e| EventHandlerError::HandlerError(e.to_string()))?;

        Ok(())
    }

    fn interested_in(&self) -> Vec<&'static str> {
        vec![] // All events
    }
}

/// Metrics handler - updates Prometheus metrics from events
pub struct MetricsHandler;

impl EventHandler for MetricsHandler {
    fn handle(&self, event: &SystemEvent) -> Result<(), EventHandlerError> {
        // Update counters based on event type
        match event {
            SystemEvent::OrderCreated(_) => {
                // metrics::counter!("orders_created_total").increment(1);
            }
            SystemEvent::OrderFilled(_) => {
                // metrics::counter!("orders_filled_total").increment(1);
            }
            SystemEvent::OrderRejected(_) => {
                // metrics::counter!("orders_rejected_total").increment(1);
            }
            SystemEvent::KillSwitchActivated(_) => {
                // metrics::gauge!("kill_switch_active").set(1.0);
            }
            _ => {}
        }

        Ok(())
    }

    fn interested_in(&self) -> Vec<&'static str> {
        vec![
            "order.created",
            "order.filled",
            "order.rejected",
            "risk.kill_switch",
        ]
    }
}
