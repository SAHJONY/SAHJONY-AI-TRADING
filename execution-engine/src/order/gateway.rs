// ─────────────────────────────────────────────────────────────
// Exchange Gateway - Abstract exchange API for order submission
// ─────────────────────────────────────────────────────────────

use std::sync::Arc;
use tokio::sync::mpsc;

use crate::types::*;

/// Gateway trait - abstract interface to exchange APIs
pub trait ExchangeGateway: Send + Sync {
    /// Submit a new order
    fn submit_order(&self, order: &NewOrderRequest) -> Result<GatewayResponse, GatewayError>;

    /// Cancel an order
    fn cancel_order(
        &self,
        exchange_order_id: &ExchangeOrderId,
        symbol: &Symbol,
    ) -> Result<GatewayResponse, GatewayError>;

    /// Replace/modify an order
    fn replace_order(
        &self,
        exchange_order_id: &ExchangeOrderId,
        new_price: Option<Decimal>,
        new_quantity: Option<f64>,
    ) -> Result<GatewayResponse, GatewayError>;

    /// Check gateway health
    fn health_check(&self) -> GatewayHealth;

    /// Get gateway name
    fn name(&self) -> &str;

    /// Get supported symbols
    fn supported_symbols(&self) -> &[Symbol];
}

use rust_decimal::Decimal;

/// Gateway response
#[derive(Debug, Clone)]
pub struct GatewayResponse {
    pub success: bool,
    pub exchange_order_id: Option<ExchangeOrderId>,
    pub reject_reason: Option<String>,
    pub timestamp: NanosTimestamp,
}

/// Gateway errors
#[derive(Debug, thiserror::Error)]
pub enum GatewayError {
    #[error("Connection error: {0}")]
    ConnectionError(String),
    #[error("Order rejected: {0}")]
    OrderRejected(String),
    #[error("Rate limit exceeded")]
    RateLimitExceeded,
    #[error("Gateway timeout")]
    Timeout,
    #[error("Symbol not supported: {0}")]
    SymbolNotSupported(Symbol),
    #[error("Gateway offline")]
    Offline,
    #[error("Internal error: {0}")]
    Internal(String),
}

/// Gateway health status
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GatewayHealth {
    Healthy,
    Degraded { reason: String },
    Unhealthy { reason: String },
    Offline,
}

impl GatewayHealth {
    pub fn is_healthy(&self) -> bool {
        matches!(self, GatewayHealth::Healthy)
    }
}

// ─────────────────────────────────────────────────────────
// Simulated Gateway (for testing)
// ─────────────────────────────────────────────────────────

/// Simulated exchange gateway for testing and development
pub struct SimulatedGateway {
    name: String,
    symbols: Vec<Symbol>,
    /// Order sender channel (simulates sending to exchange)
    order_tx: mpsc::UnboundedSender<(NewOrderRequest, tokio::sync::oneshot::Sender<GatewayResponse>)>,
    /// Fill rate (0.0–1.0) for simulation
    fill_rate: f64,
    /// Fill latency in milliseconds
    fill_latency_ms: u64,
    /// Running counter for exchange order IDs
    order_counter: std::sync::atomic::AtomicU64,
}

impl SimulatedGateway {
    pub fn new(
        name: &str,
        symbols: Vec<Symbol>,
        fill_rate: f64,
        fill_latency_ms: u64,
    ) -> (Self, mpsc::UnboundedReceiver<(NewOrderRequest, tokio::sync::oneshot::Sender<GatewayResponse>)>) {
        let (tx, rx) = mpsc::unbounded_channel();

        let gateway = Self {
            name: name.to_string(),
            symbols,
            order_tx: tx,
            fill_rate: fill_rate.clamp(0.0, 1.0),
            fill_latency_ms,
            order_counter: std::sync::atomic::AtomicU64::new(0),
        };

        (gateway, rx)
    }

    /// Generate next exchange order ID
    fn next_exchange_id(&self) -> ExchangeOrderId {
        let id = self
            .order_counter
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        ExchangeOrderId(format!("{}-{}", self.name, id))
    }
}

impl ExchangeGateway for SimulatedGateway {
    fn submit_order(&self, order: &NewOrderRequest) -> Result<GatewayResponse, GatewayError> {
        let exchange_id = self.next_exchange_id();

        let (response_tx, response_rx) = tokio::sync::oneshot::channel();

        self.order_tx
            .send((order.clone(), response_tx))
            .map_err(|_| GatewayError::Internal("Order channel closed".into()))?;

        // In simulation, immediately acknowledge
        Ok(GatewayResponse {
            success: true,
            exchange_order_id: Some(exchange_id),
            reject_reason: None,
            timestamp: NanosTimestamp::now(),
        })
    }

    fn cancel_order(
        &self,
        exchange_order_id: &ExchangeOrderId,
        _symbol: &Symbol,
    ) -> Result<GatewayResponse, GatewayError> {
        Ok(GatewayResponse {
            success: true,
            exchange_order_id: Some(exchange_order_id.clone()),
            reject_reason: None,
            timestamp: NanosTimestamp::now(),
        })
    }

    fn replace_order(
        &self,
        exchange_order_id: &ExchangeOrderId,
        _new_price: Option<Decimal>,
        _new_quantity: Option<f64>,
    ) -> Result<GatewayResponse, GatewayError> {
        Ok(GatewayResponse {
            success: true,
            exchange_order_id: Some(exchange_order_id.clone()),
            reject_reason: None,
            timestamp: NanosTimestamp::now(),
        })
    }

    fn health_check(&self) -> GatewayHealth {
        GatewayHealth::Healthy
    }

    fn name(&self) -> &str {
        &self.name
    }

    fn supported_symbols(&self) -> &[Symbol] {
        &self.symbols
    }
}

/// Gateway pool - manages multiple exchange gateways
pub struct GatewayPool {
    gateways: Vec<Box<dyn ExchangeGateway>>,
    default_index: usize,
}

impl GatewayPool {
    pub fn new() -> Self {
        Self {
            gateways: Vec::new(),
            default_index: 0,
        }
    }

    /// Add a gateway to the pool
    pub fn add_gateway(&mut self, gateway: Box<dyn ExchangeGateway>) {
        self.gateways.push(gateway);
    }

    /// Get a gateway by name
    pub fn get(&self, name: &str) -> Option<&dyn ExchangeGateway> {
        self.gateways
            .iter()
            .find(|g| g.name() == name)
            .map(|g| g.as_ref())
    }

    /// Get a gateway by exchange
    pub fn get_for_exchange(&self, exchange: &Exchange) -> Option<&dyn ExchangeGateway> {
        self.gateways
            .iter()
            .find(|g| g.name() == exchange.0)
            .map(|g| g.as_ref())
    }

    /// Check all gateways' health
    pub fn health_check_all(&self) -> Vec<(&str, GatewayHealth)> {
        self.gateways
            .iter()
            .map(|g| (g.name(), g.health_check()))
            .collect()
    }

    /// Are all gateways healthy?
    pub fn all_healthy(&self) -> bool {
        self.gateways
            .iter()
            .all(|g| g.health_check().is_healthy())
    }
}
