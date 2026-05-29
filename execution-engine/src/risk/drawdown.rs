// ─────────────────────────────────────────────────────────────
// Drawdown Monitor - Real-time drawdown tracking and kill switch
// ─────────────────────────────────────────────────────────────

use std::sync::atomic::{AtomicBool, AtomicF64, Ordering};

/// Tracks peak equity and current drawdown
pub struct DrawdownMonitor {
    /// Peak equity achieved (running maximum)
    peak_equity: AtomicF64,
    /// Current equity
    current_equity: AtomicF64,
    /// Current drawdown as a percentage (0.0–100.0)
    current_drawdown_pct: AtomicF64,
    /// Maximum drawdown experienced (0.0–100.0)
    max_drawdown_pct: AtomicF64,
    /// Kill switch threshold (drawdown % that triggers emergency)
    kill_threshold_pct: f64,
    /// Warning threshold (drawdown % that triggers alert)
    warn_threshold_pct: f64,
    /// Has the kill switch been triggered?
    killed: AtomicBool,
}

/// Drawdown status
#[derive(Debug, Clone, PartialEq)]
pub enum DrawdownStatus {
    /// Normal: below warning threshold
    Normal,
    /// Warning: above warning threshold but below kill
    Warning { pct: f64 },
    /// Critical: above kill threshold
    Critical { pct: f64 },
}

impl DrawdownMonitor {
    pub fn new(initial_equity: f64, warn_pct: f64, kill_pct: f64) -> Self {
        Self {
            peak_equity: AtomicF64::new(initial_equity),
            current_equity: AtomicF64::new(initial_equity),
            current_drawdown_pct: AtomicF64::new(0.0),
            max_drawdown_pct: AtomicF64::new(0.0),
            kill_threshold_pct: kill_pct,
            warn_threshold_pct: warn_pct,
            killed: AtomicBool::new(false),
        }
    }

    /// Update equity (e.g., after a trade closes)
    pub fn update_equity(&self, new_equity: f64) -> DrawdownStatus {
        self.current_equity.store(new_equity, Ordering::Release);

        // Update peak if new equity is higher
        let mut peak = self.peak_equity.load(Ordering::Acquire);
        if new_equity > peak {
            self.peak_equity
                .store(new_equity, Ordering::Release);
            self.current_drawdown_pct.store(0.0, Ordering::Release);
            return DrawdownStatus::Normal;
        }

        // Calculate drawdown
        if peak > 0.0 {
            let dd = ((peak - new_equity) / peak) * 100.0;
            self.current_drawdown_pct.store(dd, Ordering::Release);

            // Update max
            let mut max_dd = self.max_drawdown_pct.load(Ordering::Acquire);
            if dd > max_dd {
                self.max_drawdown_pct.store(dd, Ordering::Release);
            }

            // Check thresholds
            if dd >= self.kill_threshold_pct {
                self.killed.store(true, Ordering::Release);
                tracing::error!(
                    dd_pct = %dd,
                    peak = %peak,
                    current = %new_equity,
                    "DRAWDOWN KILL THRESHOLD BREACHED"
                );
                DrawdownStatus::Critical { pct: dd }
            } else if dd >= self.warn_threshold_pct {
                tracing::warn!(
                    dd_pct = %dd,
                    peak = %peak,
                    current = %new_equity,
                    "Drawdown warning threshold exceeded"
                );
                DrawdownStatus::Warning { pct: dd }
            } else {
                DrawdownStatus::Normal
            }
        } else {
            DrawdownStatus::Normal
        }
    }

    /// Get current equity
    pub fn current_equity(&self) -> f64 {
        self.current_equity.load(Ordering::Acquire)
    }

    /// Get peak equity
    pub fn peak_equity(&self) -> f64 {
        self.peak_equity.load(Ordering::Acquire)
    }

    /// Get current drawdown percentage
    pub fn current_drawdown_pct(&self) -> f64 {
        self.current_drawdown_pct.load(Ordering::Acquire)
    }

    /// Get maximum drawdown experienced
    pub fn max_drawdown_pct(&self) -> f64 {
        self.max_drawdown_pct.load(Ordering::Acquire)
    }

    /// Has the kill switch been triggered?
    pub fn is_killed(&self) -> bool {
        self.killed.load(Ordering::Acquire)
    }

    /// Reset the drawdown monitor
    pub fn reset(&self, new_equity: f64) {
        self.peak_equity.store(new_equity, Ordering::Release);
        self.current_equity.store(new_equity, Ordering::Release);
        self.current_drawdown_pct.store(0.0, Ordering::Release);
        self.max_drawdown_pct.store(0.0, Ordering::Release);
        self.killed.store(false, Ordering::Release);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_drawdown_tracking() {
        let monitor = DrawdownMonitor::new(100_000.0, 10.0, 25.0);

        // Initial state
        assert_eq!(monitor.peak_equity(), 100_000.0);
        assert_eq!(monitor.current_drawdown_pct(), 0.0);

        // Gain
        let status = monitor.update_equity(110_000.0);
        assert_eq!(status, DrawdownStatus::Normal);
        assert_eq!(monitor.peak_equity(), 110_000.0);

        // Small drawdown
        let status = monitor.update_equity(105_000.0);
        assert_eq!(status, DrawdownStatus::Normal);
        assert!((monitor.current_drawdown_pct() - 4.545).abs() < 0.1);

        // Warning drawdown (from peak 110k)
        let status = monitor.update_equity(95_000.0);
        assert_eq!(status, DrawdownStatus::Warning { pct: 13.636 });

        // Critical drawdown
        let status = monitor.update_equity(80_000.0);
        assert_eq!(status, DrawdownStatus::Critical { pct: 27.272 });
        assert!(monitor.is_killed());
    }
}
