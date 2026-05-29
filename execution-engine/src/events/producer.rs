// ─────────────────────────────────────────────────────────────
// Event Producer - Kafka/Redpanda event publishing with batching
// ─────────────────────────────────────────────────────────────

use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;

use crate::config::KafkaConfig;
use super::schema::SystemEvent;

/// Event producer configuration
#[derive(Debug, Clone)]
pub struct ProducerConfig {
    pub batch_size: usize,
    pub flush_interval: Duration,
    pub buffer_size: usize,
    pub enable: bool,
}

impl Default for ProducerConfig {
    fn default() -> Self {
        Self {
            batch_size: 1000,
            flush_interval: Duration::from_millis(10),
            buffer_size: 100_000,
            enable: true,
        }
    }
}

/// Event producer that batches and publishes events to Kafka/Redpanda
pub struct EventProducer {
    /// Channel to send events to the async worker
    tx: mpsc::Sender<SystemEvent>,
    /// Configuration
    config: ProducerConfig,
}

impl EventProducer {
    /// Create a new event producer and spawn the background publishing task
    pub fn new(kafka_config: Option<&KafkaConfig>, producer_config: ProducerConfig) -> Self {
        let (tx, rx) = mpsc::channel(producer_config.buffer_size);

        let config = producer_config.clone();

        // Spawn background task
        tokio::spawn(async move {
            if config.enable {
                run_producer_worker(rx, kafka_config, config).await;
            }
        });

        Self {
            tx,
            config: producer_config,
        }
    }

    /// Publish an event (non-blocking)
    pub fn publish(&self, event: SystemEvent) -> Result<(), ProducerError> {
        self.tx
            .try_send(event)
            .map_err(|e| match e {
                mpsc::error::TrySendError::Full(_) => ProducerError::BufferFull,
                mpsc::error::TrySendError::Closed(_) => ProducerError::ChannelClosed,
            })
    }

    /// Publish multiple events at once
    pub fn publish_batch(&self, events: Vec<SystemEvent>) -> Result<(), ProducerError> {
        for event in events {
            self.publish(event)?;
        }
        Ok(())
    }
}

/// Producer worker - batches and sends events
async fn run_producer_worker(
    mut rx: mpsc::Receiver<SystemEvent>,
    kafka_config: Option<&KafkaConfig>,
    config: ProducerConfig,
) {
    let mut buffer: Vec<SystemEvent> = Vec::with_capacity(config.batch_size);
    let mut tick = tokio::time::interval(config.flush_interval);

    loop {
        tokio::select! {
            // Receive events
            maybe_event = rx.recv() => {
                match maybe_event {
                    Some(event) => {
                        buffer.push(event);
                        if buffer.len() >= config.batch_size {
                            flush_batch(&mut buffer, kafka_config).await;
                        }
                    }
                    None => {
                        // Channel closed - final flush
                        if !buffer.is_empty() {
                            flush_batch(&mut buffer, kafka_config).await;
                        }
                        tracing::info!("Event producer worker shutting down");
                        return;
                    }
                }
            }
            // Periodic flush
            _ = tick.tick() => {
                if !buffer.is_empty() {
                    flush_batch(&mut buffer, kafka_config).await;
                }
            }
        }
    }
}

/// Flush accumulated events to Kafka/Redpanda
async fn flush_batch(buffer: &mut Vec<SystemEvent>, kafka_config: Option<&KafkaConfig>) {
    let count = buffer.len();
    if count == 0 {
        return;
    }

    // In production, this serializes and sends to Kafka
    // For now, log the batch
    tracing::debug!(
        event_count = count,
        event_types = ?buffer.iter().map(|e| e.event_type_tag()).collect::<Vec<_>>(),
        "Flushing event batch"
    );

    // If Kafka is configured, publish there
    if let Some(cfg) = kafka_config {
        // Publish to appropriate topics based on event type
        for event in buffer.iter() {
            let topic = match event.event_type_tag() {
                t if t.starts_with("order.") => &cfg.order_events_topic,
                t if t.starts_with("market_data.") => &cfg.market_data_topic,
                t if t.starts_with("risk.") => &cfg.risk_events_topic,
                t if t.starts_with("system.") => &cfg.audit_topic,
                _ => &cfg.audit_topic,
            };

            let _payload = event.to_json_bytes();
            // In production: kafka_producer.send(topic, payload)
            let _ = topic;
        }
    }

    buffer.clear();
}

#[derive(Debug, thiserror::Error)]
pub enum ProducerError {
    #[error("Event buffer full")]
    BufferFull,
    #[error("Producer channel closed")]
    ChannelClosed,
}

/// Synchronous (blocking) producer for latency-critical paths
pub struct SyncEventProducer {
    events: parking_lot::Mutex<Vec<SystemEvent>>,
    batch_size: usize,
}

impl SyncEventProducer {
    pub fn new(batch_size: usize) -> Self {
        Self {
            events: parking_lot::Mutex::new(Vec::with_capacity(batch_size)),
            batch_size,
        }
    }

    /// Add event - extremely fast, no allocation on most calls
    pub fn push(&self, event: SystemEvent) {
        let mut events = self.events.lock();
        events.push(event);
    }

    /// Drain and get all events
    pub fn drain(&self) -> Vec<SystemEvent> {
        let mut events = self.events.lock();
        std::mem::replace(&mut *events, Vec::with_capacity(self.batch_size))
    }
}
