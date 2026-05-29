// ─────────────────────────────────────────────────────────────
// Order-specific type extensions
// ─────────────────────────────────────────────────────────────

use rust_decimal::Decimal;

use crate::types::{NewOrderRequest, OrderSide, OrderStatus, OrderType};

impl NewOrderRequest {
    /// Validate the order request
    pub fn validate(&self) -> Result<(), OrderValidationError> {
        // Quantity must be positive
        if self.quantity <= 0.0 {
            return Err(OrderValidationError::InvalidQuantity(self.quantity));
        }

        // Limit/stop orders require a price
        match self.order_type {
            OrderType::Limit | OrderType::StopLimit | OrderType::Iceberg | OrderType::Pegged => {
                match self.price {
                    Some(p) if p > Decimal::ZERO => {}
                    _ => {
                        return Err(OrderValidationError::MissingPrice);
                    }
                }
            }
            OrderType::Stop | OrderType::TrailingStop => {
                match self.stop_price {
                    Some(p) if p > Decimal::ZERO => {}
                    _ => {
                        return Err(OrderValidationError::MissingStopPrice);
                    }
                }
            }
            OrderType::Market => {
                // Market orders don't need price
            }
        }

        // Side must be valid
        match self.side {
            OrderSide::Buy | OrderSide::Sell | OrderSide::SellShort => {}
        }

        Ok(())
    }

    /// Estimated notional value
    pub fn estimated_notional(&self) -> Decimal {
        let price = self.price.unwrap_or(Decimal::ZERO);
        Decimal::from_f64(self.quantity).unwrap_or(Decimal::ZERO) * price
    }

    /// Is this a buy order?
    pub fn is_buy(&self) -> bool {
        matches!(self.side, OrderSide::Buy)
    }

    /// Is this a sell order?
    pub fn is_sell(&self) -> bool {
        matches!(self.side, OrderSide::Sell | OrderSide::SellShort)
    }
}

#[derive(Debug, Clone, thiserror::Error)]
pub enum OrderValidationError {
    #[error("Invalid quantity: {0}")]
    InvalidQuantity(f64),
    #[error("Missing price for limit/stop order")]
    MissingPrice,
    #[error("Missing stop price for stop order")]
    MissingStopPrice,
    #[error("Invalid order state transition: {from:?} -> {to:?}")]
    InvalidStateTransition {
        from: OrderStatus,
        to: OrderStatus,
    },
}

/// Valid state transitions for an order
pub fn is_valid_transition(from: OrderStatus, to: OrderStatus) -> bool {
    use OrderStatus::*;
    matches!(
        (from, to),
        (PendingNew, New)
            | (PendingNew, Rejected)
            | (New, PartiallyFilled)
            | (New, Filled)
            | (New, PendingCancel)
            | (New, Expired)
            | (New, Suspended)
            | (PartiallyFilled, Filled)
            | (PartiallyFilled, PendingCancel)
            | (PartiallyFilled, Suspended)
            | (PendingCancel, Cancelled)
            | (PendingCancel, PartiallyFilled) // Cancel request lost a race
            | (PendingCancel, Filled) // Cancel request lost a race
            | (Suspended, New) // Resume
    )
}
