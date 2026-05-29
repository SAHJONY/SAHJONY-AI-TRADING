// ─────────────────────────────────────────────────────────────
// Event Schemas - Type-safe event definitions for the event bus
// ─────────────────────────────────────────────────────────────

use serde::{Deserialize, Serialize};
use crate::types::*;

/// All event types that flow through the system
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum SystemEvent {
    // ── Order Events ──
    OrderCreated(OrderCreatedEvent),
    OrderAcknowledged(OrderAcknowledgedEvent),
    OrderRejected(OrderRejectedEvent),
    OrderFilled(OrderFilledEvent),
    OrderCancelled(OrderCancelledEvent),
    OrderExpired(OrderExpiredEvent),

    // ── Market Data Events ──
    QuoteUpdate(QuoteUpdateEvent),
    TradeUpdate(TradeUpdateEvent),
    OrderBookSnapshot(OrderBookSnapshotEvent),

    // ── Risk Events ──
    RiskCheckPassed(RiskCheckPassedEvent),
    RiskCheckFailed(RiskCheckFailedEvent),
    CircuitBreakerTripped(CircuitBreakerTrippedEvent),
    KillSwitchActivated(KillSwitchActivatedEvent),

    // ── System Events ──
    Heartbeat(HeartbeatEvent),
    AuditLog(AuditLogEvent),
    SystemAlert(SystemAlertEvent),
}

// ── Order Events ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderCreatedEvent {
    pub client_order_id: String,
    pub symbol: String,
    pub side: String,
    pub order_type: String,
    pub quantity: f64,
    pub price: Option<f64>,
    pub strategy_id: String,
    pub account_id: String,
    pub timestamp_ns: i64,
    pub request_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderAcknowledgedEvent {
    pub client_order_id: String,
    pub exchange_order_id: String,
    pub symbol: String,
    pub timestamp_ns: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderRejectedEvent {
    pub client_order_id: String,
    pub reason: String,
    pub timestamp_ns: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderFilledEvent {
    pub client_order_id: String,
    pub exchange_order_id: String,
    pub execution_id: String,
    pub symbol: String,
    pub side: String,
    pub executed_quantity: f64,
    pub executed_price: f64,
    pub remaining_quantity: f64,
    pub liquidity_flag: Option<String>,
    pub timestamp_ns: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderCancelledEvent {
    pub client_order_id: String,
    pub exchange_order_id: String,
    pub symbol: String,
    pub timestamp_ns: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderExpiredEvent {
    pub client_order_id: String,
    pub symbol: String,
    pub timestamp_ns: i64,
}

// ── Market Data Events ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuoteUpdateEvent {
    pub symbol: String,
    pub exchange: String,
    pub bid_price: f64,
    pub ask_price: f64,
    pub bid_size: f64,
    pub ask_size: f64,
    pub timestamp_ns: i64,
    pub sequence_number: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TradeUpdateEvent {
    pub symbol: String,
    pub exchange: String,
    pub price: f64,
    pub size: f64,
    pub timestamp_ns: i64,
    pub trade_id: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderBookSnapshotEvent {
    pub symbol: String,
    pub exchange: String,
    pub timestamp_ns: i64,
    pub best_bid: f64,
    pub best_ask: f64,
    pub spread_bps: f64,
    pub bid_depth: Vec<LevelEntry>,
    pub ask_depth: Vec<LevelEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LevelEntry {
    pub price: f64,
    pub size: f64,
}

// ── Risk Events ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskCheckPassedEvent {
    pub client_order_id: String,
    pub checks_passed: u32,
    pub timestamp_ns: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskCheckFailedEvent {
    pub client_order_id: String,
    pub reason: String,
    pub checks_failed: Vec<String>,
    pub severity: String,
    pub timestamp_ns: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CircuitBreakerTrippedEvent {
    pub reason: String,
    pub rejection_count: u32,
    pub cooldown_secs: u64,
    pub timestamp_ns: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KillSwitchActivatedEvent {
    pub reason: String,
    pub triggered_by: String,
    pub current_drawdown_pct: f64,
    pub timestamp_ns: i64,
}

// ── System Events ──

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeartbeatEvent {
    pub component_id: String,
    pub instance_id: String,
    pub status: String,
    pub uptime_secs: u64,
    pub active_orders: u64,
    pub orders_processed: u64,
    pub cpu_usage_pct: f64,
    pub memory_usage_mb: f64,
    pub timestamp_ns: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditLogEvent {
    pub entry_id: String,
    pub event_type: String,
    pub actor: String,
    pub action: String,
    pub target: String,
    pub details: String,
    pub trace_id: String,
    pub timestamp_ns: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemAlertEvent {
    pub alert_type: String,
    pub severity: String,
    pub message: String,
    pub component: String,
    pub timestamp_ns: i64,
}

// ── Serialization ──

impl SystemEvent {
    /// Serialize to JSON bytes (for Kafka/Redpanda)
    pub fn to_json_bytes(&self) -> Vec<u8> {
        serde_json::to_vec(self).unwrap_or_default()
    }

    /// Serialize to binary (bincode - compact)
    pub fn to_binary(&self) -> Vec<u8> {
        bincode::serialize(self).unwrap_or_default()
    }

    /// Deserialize from JSON bytes
    pub fn from_json_bytes(data: &[u8]) -> Option<Self> {
        serde_json::from_slice(data).ok()
    }

    /// Deserialize from binary
    pub fn from_binary(data: &[u8]) -> Option<Self> {
        bincode::deserialize(data).ok()
    }

    /// Get event type tag
    pub fn event_type_tag(&self) -> &'static str {
        match self {
            SystemEvent::OrderCreated(_) => "order.created",
            SystemEvent::OrderAcknowledged(_) => "order.acknowledged",
            SystemEvent::OrderRejected(_) => "order.rejected",
            SystemEvent::OrderFilled(_) => "order.filled",
            SystemEvent::OrderCancelled(_) => "order.cancelled",
            SystemEvent::OrderExpired(_) => "order.expired",
            SystemEvent::QuoteUpdate(_) => "market_data.quote",
            SystemEvent::TradeUpdate(_) => "market_data.trade",
            SystemEvent::OrderBookSnapshot(_) => "market_data.order_book",
            SystemEvent::RiskCheckPassed(_) => "risk.check_passed",
            SystemEvent::RiskCheckFailed(_) => "risk.check_failed",
            SystemEvent::CircuitBreakerTripped(_) => "risk.circuit_breaker",
            SystemEvent::KillSwitchActivated(_) => "risk.kill_switch",
            SystemEvent::Heartbeat(_) => "system.heartbeat",
            SystemEvent::AuditLog(_) => "system.audit",
            SystemEvent::SystemAlert(_) => "system.alert",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_event_serialization_roundtrip() {
        let event = SystemEvent::OrderCreated(OrderCreatedEvent {
            client_order_id: "test-1".into(),
            symbol: "AAPL".into(),
            side: "BUY".into(),
            order_type: "LIMIT".into(),
            quantity: 100.0,
            price: Some(150.0),
            strategy_id: "alpha_1".into(),
            account_id: "acct_1".into(),
            timestamp_ns: 123456789,
            request_id: "req-1".into(),
        });

        let bytes = event.to_json_bytes();
        let decoded = SystemEvent::from_json_bytes(&bytes).unwrap();

        match decoded {
            SystemEvent::OrderCreated(e) => {
                assert_eq!(e.symbol, "AAPL");
                assert_eq!(e.quantity, 100.0);
            }
            _ => panic!("Wrong event type"),
        }
    }
}
