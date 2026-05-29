// ─────────────────────────────────────────────────────────────
// Risk Management Framework
// Pre-trade risk checks, VaR, Kelly position sizing, circuit breakers
// ─────────────────────────────────────────────────────────────

pub mod var;
pub mod kelly;
pub mod circuit_breaker;
pub mod position_limits;
pub mod drawdown;
pub mod risk_engine;

pub use risk_engine::RiskEngine;
pub use circuit_breaker::CircuitBreaker;
pub use drawdown::DrawdownMonitor;
