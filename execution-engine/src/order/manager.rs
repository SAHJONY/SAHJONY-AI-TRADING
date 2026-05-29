// ─────────────────────────────────────────────────────────────
// Order Manager - full order lifecycle management
// ─────────────────────────────────────────────────────────────

use dashmap::DashMap;
use std::sync::Arc;

use crate::types::*;

use super::types::{is_valid_transition, OrderValidationError};

/// Central order manager - tracks all orders through their lifecycle
pub struct OrderManager {
    /// Active orders by client order ID
    orders: DashMap<ClientOrderId, Arc<OrderState>>,
    /// Orders by exchange order ID (for lookups from execution reports)
    exchange_orders: DashMap<ExchangeOrderId, ClientOrderId>,
    /// Orders by symbol (for cancellation by symbol)
    symbol_index: DashMap<Symbol, Vec<ClientOrderId>>,
    /// Total number of orders processed
    total_orders: std::sync::atomic::AtomicU64,
    /// Total number of orders currently active
    active_orders: std::sync::atomic::AtomicU64,
}

impl OrderManager {
    pub fn new() -> Self {
        Self {
            orders: DashMap::new(),
            exchange_orders: DashMap::new(),
            symbol_index: DashMap::new(),
            total_orders: std::sync::atomic::AtomicU64::new(0),
            active_orders: std::sync::atomic::AtomicU64::new(0),
        }
    }

    /// Register a new order
    pub fn create_order(&self, request: &NewOrderRequest) -> Result<Arc<OrderState>, OrderValidationError> {
        request.validate()?;

        let order = Arc::new(OrderState {
            client_order_id: request.client_order_id,
            exchange_order_id: None,
            symbol: request.symbol.clone(),
            exchange: request.exchange.clone(),
            side: request.side,
            order_type: request.order_type,
            time_in_force: request.time_in_force,
            status: OrderStatus::PendingNew,
            quantity: request.quantity,
            price: request.price,
            stop_price: request.stop_price,
            executed_quantity: 0.0,
            executed_notional: Decimal::ZERO,
            average_fill_price: None,
            remaining_quantity: request.quantity,
            created_at: NanosTimestamp::now(),
            updated_at: NanosTimestamp::now(),
            strategy_id: request.strategy_id.clone(),
            account_id: request.account_id.clone(),
        });

        self.orders
            .insert(request.client_order_id, Arc::clone(&order));

        self.symbol_index
            .entry(request.symbol.clone())
            .or_default()
            .push(request.client_order_id);

        self.total_orders
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        self.active_orders
            .fetch_add(1, std::sync::atomic::Ordering::Relaxed);

        tracing::info!(
            order_id = %request.client_order_id,
            symbol = %request.symbol,
            side = ?request.side,
            qty = request.quantity,
            "Order created"
        );

        Ok(order)
    }

    /// Acknowledge an order (received exchange order ID)
    pub fn acknowledge(
        &self,
        client_order_id: &ClientOrderId,
        exchange_order_id: ExchangeOrderId,
    ) -> Result<(), OrderManagerError> {
        let mut order = self
            .orders
            .get_mut(client_order_id)
            .ok_or(OrderManagerError::OrderNotFound(*client_order_id))?;

        order.exchange_order_id = Some(exchange_order_id.clone());
        order.status = OrderStatus::New;
        order.updated_at = NanosTimestamp::now();

        self.exchange_orders
            .insert(exchange_order_id, *client_order_id);

        Ok(())
    }

    /// Reject an order
    pub fn reject(
        &self,
        client_order_id: &ClientOrderId,
        reason: String,
    ) -> Result<(), OrderManagerError> {
        let mut order = self
            .orders
            .get_mut(client_order_id)
            .ok_or(OrderManagerError::OrderNotFound(*client_order_id))?;

        order.status = OrderStatus::Rejected;
        order.updated_at = NanosTimestamp::now();

        self.active_orders
            .fetch_sub(1, std::sync::atomic::Ordering::Relaxed);

        tracing::warn!(
            order_id = %client_order_id,
            reason = %reason,
            "Order rejected"
        );

        Ok(())
    }

    /// Process an execution report
    pub fn process_execution(&self, report: &ExecutionReport) -> Result<(), OrderManagerError> {
        let mut order = self
            .orders
            .get_mut(&report.client_order_id)
            .ok_or(OrderManagerError::OrderNotFound(report.client_order_id))?;

        let new_status = report.order_status;
        if !is_valid_transition(order.status, new_status) {
            return Err(OrderManagerError::InvalidStateTransition {
                from: order.status,
                to: new_status,
            });
        }

        order.status = new_status;
        order.executed_quantity = report.executed_quantity;
        order.executed_notional += rust_decimal::Decimal::from_f64(report.executed_quantity)
            .unwrap_or(rust_decimal::Decimal::ZERO)
            * report.executed_price;
        order.remaining_quantity = report.remaining_quantity;
        order.updated_at = report.timestamp;

        // Update average fill price
        if report.executed_quantity > 0.0 {
            order.average_fill_price = Some(
                (order.average_fill_price.unwrap_or(rust_decimal::Decimal::ZERO)
                    * rust_decimal::Decimal::from_f64(order.executed_quantity - report.executed_quantity).unwrap_or(rust_decimal::Decimal::ZERO)
                    + report.executed_price
                        * rust_decimal::Decimal::from_f64(report.executed_quantity).unwrap_or(rust_decimal::Decimal::ZERO))
                    / rust_decimal::Decimal::from_f64(order.executed_quantity).unwrap_or(rust_decimal::Decimal::ONE),
            );
        }

        // If terminal state, decrement active count
        match new_status {
            OrderStatus::Filled
            | OrderStatus::Cancelled
            | OrderStatus::Rejected
            | OrderStatus::Expired => {
                self.active_orders
                    .fetch_sub(1, std::sync::atomic::Ordering::Relaxed);
            }
            _ => {}
        }

        tracing::info!(
            order_id = %report.client_order_id,
            exec_id = %report.execution_id,
            status = ?new_status,
            executed = report.executed_quantity,
            price = %report.executed_price,
            "Execution processed"
        );

        Ok(())
    }

    /// Cancel an order
    pub fn cancel_order(&self, client_order_id: &ClientOrderId) -> Result<(), OrderManagerError> {
        let mut order = self
            .orders
            .get_mut(client_order_id)
            .ok_or(OrderManagerError::OrderNotFound(*client_order_id))?;

        match order.status {
            OrderStatus::New | OrderStatus::PartiallyFilled | OrderStatus::PendingNew => {
                order.status = OrderStatus::PendingCancel;
                order.updated_at = NanosTimestamp::now();
                Ok(())
            }
            _ => Err(OrderManagerError::InvalidStateTransition {
                from: order.status,
                to: OrderStatus::Cancelled,
            }),
        }
    }

    /// Cancel all orders for a symbol
    pub fn cancel_all_for_symbol(&self, symbol: &Symbol) -> usize {
        let mut cancelled = 0;

        if let Some(order_ids) = self.symbol_index.get(symbol) {
            for order_id in order_ids.iter() {
                if self.cancel_order(order_id).is_ok() {
                    cancelled += 1;
                }
            }
        }

        cancelled
    }

    /// Cancel all orders globally
    pub fn cancel_all(&self) -> usize {
        let mut cancelled = 0;
        for entry in self.orders.iter() {
            if self.cancel_order(entry.key()).is_ok() {
                cancelled += 1;
            }
        }
        cancelled
    }

    /// Get an order by client order ID
    pub fn get_order(&self, client_order_id: &ClientOrderId) -> Option<Arc<OrderState>> {
        self.orders.get(client_order_id).map(|r| Arc::clone(r.value()))
    }

    /// Get all active orders for a symbol
    pub fn get_orders_for_symbol(&self, symbol: &Symbol) -> Vec<Arc<OrderState>> {
        self.symbol_index
            .get(symbol)
            .map(|ids| {
                ids.iter()
                    .filter_map(|id| self.orders.get(id).map(|r| Arc::clone(r.value())))
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Get a count of active orders
    pub fn active_order_count(&self) -> u64 {
        self.active_orders.load(std::sync::atomic::Ordering::Relaxed)
    }

    /// Get total orders processed
    pub fn total_order_count(&self) -> u64 {
        self.total_orders.load(std::sync::atomic::Ordering::Relaxed)
    }
}

#[derive(Debug, thiserror::Error)]
pub enum OrderManagerError {
    #[error("Order not found: {0}")]
    OrderNotFound(ClientOrderId),
    #[error("Invalid state transition: {from:?} -> {to:?}")]
    InvalidStateTransition {
        from: OrderStatus,
        to: OrderStatus,
    },
    #[error(transparent)]
    Validation(#[from] OrderValidationError),
}

use rust_decimal::Decimal;

#[cfg(test)]
mod tests {
    use super::*;

    fn make_test_order() -> NewOrderRequest {
        NewOrderRequest {
            symbol: Symbol("AAPL".into()),
            exchange: Exchange("NASDAQ".into()),
            side: OrderSide::Buy,
            order_type: OrderType::Limit,
            time_in_force: TimeInForce::Day,
            quantity: 100.0,
            price: Some(Decimal::from_f64(150.0).unwrap()),
            stop_price: None,
            trailing_amount: None,
            display_quantity: None,
            client_order_id: ClientOrderId::new(),
            strategy_id: StrategyId("test".into()),
            account_id: AccountId("test_account".into()),
            tags: std::collections::HashMap::new(),
        }
    }

    #[test]
    fn test_order_lifecycle() {
        let manager = OrderManager::new();
        let request = make_test_order();
        let client_id = request.client_order_id;

        // Create
        let order = manager.create_order(&request).unwrap();
        assert_eq!(order.status, OrderStatus::PendingNew);
        assert_eq!(manager.active_order_count(), 1);

        // Acknowledge
        let exchange_id = ExchangeOrderId("EXCH-001".into());
        manager.acknowledge(&client_id, exchange_id.clone()).unwrap();

        let order = manager.get_order(&client_id).unwrap();
        assert_eq!(order.status, OrderStatus::New);

        // Fill
        let report = ExecutionReport {
            client_order_id: client_id,
            exchange_order_id: exchange_id,
            execution_id: ExecutionId("EXEC-001".into()),
            order_status: OrderStatus::Filled,
            symbol: Symbol("AAPL".into()),
            side: OrderSide::Buy,
            executed_quantity: 100.0,
            executed_price: Decimal::from_f64(150.0).unwrap(),
            remaining_quantity: 0.0,
            commission: None,
            commission_currency: None,
            timestamp: NanosTimestamp::now(),
            exchange_timestamp: NanosTimestamp::now(),
            liquidity_flag: None,
        };

        manager.process_execution(&report).unwrap();
        let order = manager.get_order(&client_id).unwrap();
        assert_eq!(order.status, OrderStatus::Filled);
        assert_eq!(manager.active_order_count(), 0);
    }
}
