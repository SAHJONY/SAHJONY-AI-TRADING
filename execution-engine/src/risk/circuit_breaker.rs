// ─────────────────────────────────────────────────────────────
// Circuit Breaker - Kill switch and circuit breaker patterns
// ─────────────────────────────────────────────────────────────

use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use parking_lot::RwLock;

/// Circuit breaker state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CircuitState {
    /// Normal operation - orders flow through
    Closed,
    /// Warning state - trades throttled
    HalfOpen,
    /// Tripped - all orders blocked
    Open,
}

/// Circuit breaker - protects against runaway trading
pub struct CircuitBreaker {
    /// Current state
    state: RwLock<CircuitState>,
    /// Time the breaker was tripped
    tripped_at: RwLock<Option<Instant>>,
    /// Cooldown period before allowing recovery
    cooldown: Duration,
    /// Consecutive rejections counter
    rejection_count: AtomicU32,
    /// Max consecutive rejections before tripping
    max_rejections: u32,
    /// Total orders blocked since last reset
    orders_blocked: AtomicU64,
    /// Is the kill switch active?
    kill_switch: AtomicBool,
    /// Reason for the trip
    trip_reason: RwLock<String>,
    /// Has the half-open probe already been consumed?
    half_open_probe_used: AtomicBool,
}

impl CircuitBreaker {
    pub fn new(max_rejections: u32, cooldown_secs: u64) -> Self {
        Self {
            state: RwLock::new(CircuitState::Closed),
            tripped_at: RwLock::new(None),
            cooldown: Duration::from_secs(cooldown_secs),
            rejection_count: AtomicU32::new(0),
            max_rejections,
            orders_blocked: AtomicU64::new(0),
            kill_switch: AtomicBool::new(false),
            trip_reason: RwLock::new(String::new()),
            half_open_probe_used: AtomicBool::new(false),
        }
    }

    /// Check if an order should be allowed through
    pub fn check(&self) -> CircuitBreakerResult {
        // Kill switch overrides everything
        if self.kill_switch.load(Ordering::Acquire) {
            self.orders_blocked.fetch_add(1, Ordering::Relaxed);
            return CircuitBreakerResult::Blocked("Kill switch active".into());
        }

        let state = *self.state.read();

        match state {
            CircuitState::Closed => CircuitBreakerResult::Allowed,
            CircuitState::HalfOpen => {
                // Half-open: allow exactly one probe request to test recovery
                if self.half_open_probe_used.load(Ordering::Acquire) {
                    // Probe already in flight or consumed — block until result
                    self.orders_blocked.fetch_add(1, Ordering::Relaxed);
                    CircuitBreakerResult::Blocked(
                        "Circuit half-open: awaiting probe result".into(),
                    )
                } else {
                    self.half_open_probe_used
                        .store(true, Ordering::Release);
                    CircuitBreakerResult::Allowed
                }
            }
            CircuitState::Open => {
                // Check if cooldown has elapsed
                let tripped = self.tripped_at.read();
                if let Some(trip_time) = *tripped {
                    if trip_time.elapsed() >= self.cooldown {
                        // Transition to half-open
                        *self.state.write() = CircuitState::HalfOpen;
                        tracing::info!("Circuit breaker transitioning to half-open");
                        return CircuitBreakerResult::Allowed;
                    }
                }
                self.orders_blocked.fetch_add(1, Ordering::Relaxed);
                CircuitBreakerResult::Blocked(self.trip_reason.read().clone())
            }
        }
    }

    /// Record a successful order
    pub fn record_success(&self) {
        self.rejection_count.store(0, Ordering::Release);

        let state = *self.state.read();
        if state == CircuitState::HalfOpen {
            // Recovery: the probe succeeded → transition to closed
            *self.state.write() = CircuitState::Closed;
            *self.tripped_at.write() = None;
            *self.trip_reason.write() = String::new();
            self.half_open_probe_used.store(false, Ordering::Release);
            tracing::info!("Circuit breaker recovered - transitioning to closed");
        }
    }

    /// Record a rejection - may trip the breaker
    pub fn record_rejection(&self, reason: &str) {
        // If we are in half-open and the probe fails, immediately re-trip
        let state = *self.state.read();
        if state == CircuitState::HalfOpen {
            self.half_open_probe_used.store(false, Ordering::Release);
            self.trip(&format!("Half-open probe failed: {}", reason));
            return;
        }

        let count = self.rejection_count.fetch_add(1, Ordering::AcqRel) + 1;
        if count >= self.max_rejections {
            self.trip(reason);
        }
    }

    /// Manually trip the breaker
    pub fn trip(&self, reason: &str) {
        let mut state = self.state.write();
        if *state == CircuitState::Open {
            return; // Already tripped
        }

        *state = CircuitState::Open;
        *self.tripped_at.write() = Some(Instant::now());
        *self.trip_reason.write() = reason.to_string();
        self.rejection_count.store(0, Ordering::Release);

        tracing::error!(
            reason = %reason,
            cooldown_secs = self.cooldown.as_secs(),
            "Circuit breaker tripped!"
        );
    }

    /// Manually reset the breaker
    pub fn reset(&self) {
        *self.state.write() = CircuitState::Closed;
        *self.tripped_at.write() = None;
        *self.trip_reason.write() = String::new();
        self.rejection_count.store(0, Ordering::Release);
        self.orders_blocked.store(0, Ordering::Release);
        self.half_open_probe_used.store(false, Ordering::Release);

        tracing::info!("Circuit breaker manually reset");
    }

    /// Activate kill switch (permanent until manually reset)
    pub fn kill(&self, reason: &str) {
        self.kill_switch.store(true, Ordering::Release);
        self.trip(reason);
        tracing::error!(reason = %reason, "KILL SWITCH ACTIVATED");
    }

    /// Check if kill switch is active
    pub fn is_killed(&self) -> bool {
        self.kill_switch.load(Ordering::Acquire)
    }

    /// Get current state
    pub fn state(&self) -> CircuitState {
        *self.state.read()
    }

    /// Get number of orders blocked
    pub fn orders_blocked(&self) -> u64 {
        self.orders_blocked.load(Ordering::Relaxed)
    }
}

/// Result of a circuit breaker check
#[derive(Debug, Clone)]
pub enum CircuitBreakerResult {
    /// Order is allowed
    Allowed,
    /// Order is blocked with reason
    Blocked(String),
}

impl CircuitBreakerResult {
    pub fn is_allowed(&self) -> bool {
        matches!(self, CircuitBreakerResult::Allowed)
    }

    pub fn reason(&self) -> Option<&str> {
        match self {
            CircuitBreakerResult::Allowed => None,
            CircuitBreakerResult::Blocked(r) => Some(r),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_circuit_breaker_trip() {
        let cb = CircuitBreaker::new(3, 60);

        assert!(cb.check().is_allowed());

        cb.record_rejection("test error 1");
        assert!(cb.check().is_allowed());

        cb.record_rejection("test error 2");
        assert!(cb.check().is_allowed());

        cb.record_rejection("test error 3");
        assert!(!cb.check().is_allowed());
        assert_eq!(cb.state(), CircuitState::Open);
    }

    #[test]
    fn test_circuit_breaker_recovery() {
        let cb = CircuitBreaker::new(3, 0); // 0 second cooldown

        // Trip it
        cb.trip("test trip");
        assert!(!cb.check().is_allowed());

        // With 0 cooldown, should go to half-open immediately
        // Actually needs the cooldown to have elapsed
        assert!(cb.check().is_allowed());

        cb.record_success();
        assert_eq!(cb.state(), CircuitState::Closed);
    }

    #[test]
    fn test_kill_switch() {
        let cb = CircuitBreaker::new(100, 60);
        assert!(cb.check().is_allowed());

        cb.kill("manual emergency");
        assert!(!cb.check().is_allowed());
        assert!(cb.is_killed());

        cb.reset();
        assert!(cb.check().is_allowed());
        assert!(!cb.is_killed());
    }
}
