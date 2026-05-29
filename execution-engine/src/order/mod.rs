// ─────────────────────────────────────────────────────────────
// Order Management Module
// Order lifecycle, smart routing, and exchange gateway abstraction
// ─────────────────────────────────────────────────────────────

pub mod types;
pub mod manager;
pub mod router;
pub mod gateway;

pub use manager::OrderManager;
pub use router::OrderRouter;
pub use gateway::{ExchangeGateway, GatewayError};
