// ─────────────────────────────────────────────────────────────
// Layer 1 - Execution & Risk Fabric
// Ultra-low latency trading execution engine with integrated risk management
// ─────────────────────────────────────────────────────────────

pub mod config;
pub mod market_data;
pub mod order;
pub mod risk;
pub mod events;
pub mod metrics;
pub mod types;
pub mod utils;

/// Library version
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Re-export commonly used types
pub use types::*;
