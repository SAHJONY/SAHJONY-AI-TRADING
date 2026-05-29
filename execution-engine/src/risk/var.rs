// ─────────────────────────────────────────────────────────────
// Value at Risk (VaR) Calculator
// Historical simulation, parametric (variance-covariance), and Monte Carlo methods
// ─────────────────────────────────────────────────────────────

use ndarray::Array1;
use ndarray_stats::QuantileExt;
use statrs::distribution::{ContinuousCDF, Normal};

/// VaR calculation method
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum VaRMethod {
    /// Historical simulation (non-parametric)
    Historical,
    /// Parametric (assumes normal distribution)
    Parametric,
    /// Monte Carlo simulation
    MonteCarlo { simulations: usize },
}

/// VaR result
#[derive(Debug, Clone)]
pub struct VaRResult {
    /// VaR at the specified confidence level (positive = loss)
    pub var: f64,
    /// Expected shortfall (CVaR) - average loss beyond VaR
    pub expected_shortfall: f64,
    /// Confidence level used
    pub confidence: f64,
    /// Method used
    pub method: VaRMethod,
    /// Lookback window size
    pub lookback: usize,
    /// Current portfolio value
    pub portfolio_value: f64,
    /// VaR as percentage of portfolio
    pub var_pct: f64,
}

/// VaR Calculator
pub struct VaRCalculator {
    /// Default confidence level (e.g., 0.95, 0.99)
    confidence: f64,
    /// Lookback window
    lookback: usize,
}

impl VaRCalculator {
    pub fn new(confidence: f64, lookback: usize) -> Self {
        assert!(confidence > 0.0 && confidence < 1.0, "Confidence must be in (0, 1)");
        Self {
            confidence,
            lookback,
        }
    }

    /// Calculate VaR using historical simulation
    pub fn historical_var(
        &self,
        returns: &[f64],
        portfolio_value: f64,
    ) -> Option<VaRResult> {
        if returns.is_empty() {
            return None;
        }

        let n = returns.len();
        let window = self.lookback.min(n);
        let recent_returns = &returns[n - window..];

        // Sort returns ascending
        let mut sorted = recent_returns.to_vec();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        // VaR is the (1 - confidence) percentile
        let var_idx = ((1.0 - self.confidence) * window as f64).floor() as usize;
        let var_idx = var_idx.min(window.saturating_sub(1));

        let var_return = sorted[var_idx]; // This is negative for a loss
        let var = (-var_return) * portfolio_value;

        // Expected shortfall: average of returns worse than VaR
        let es_returns: Vec<f64> = sorted
            .iter()
            .take(var_idx + 1)
            .copied()
            .collect();

        let es_return = if es_returns.is_empty() {
            var_return
        } else {
            es_returns.iter().sum::<f64>() / es_returns.len() as f64
        };
        let expected_shortfall = (-es_return) * portfolio_value;

        Some(VaRResult {
            var,
            expected_shortfall,
            confidence: self.confidence,
            method: VaRMethod::Historical,
            lookback: window,
            portfolio_value,
            var_pct: var / portfolio_value,
        })
    }

    /// Calculate VaR using parametric method (assumes normal distribution)
    pub fn parametric_var(
        &self,
        returns: &[f64],
        portfolio_value: f64,
    ) -> Option<VaRResult> {
        if returns.is_empty() {
            return None;
        }

        let n = returns.len();
        let window = self.lookback.min(n);
        let recent_returns = &returns[n - window..];

        let mean = recent_returns.iter().sum::<f64>() / window as f64;
        let variance = recent_returns
            .iter()
            .map(|r| (r - mean).powi(2))
            .sum::<f64>()
            / (window as f64 - 1.0);
        let std_dev = variance.sqrt();

        // Z-score for the confidence level
        let normal = Normal::new(0.0, 1.0).unwrap();
        let alpha = 1.0 - self.confidence;
        let z_score = -normal.inverse_cdf(alpha);

        let var_return = mean - z_score * std_dev;
        let var = (-var_return) * portfolio_value;

        // Expected shortfall for normal distribution
        let pdf_at_z = Normal::new(0.0, 1.0).unwrap().pdf(z_score);
        let es_return = mean - std_dev * pdf_at_z / alpha;
        let expected_shortfall = (-es_return) * portfolio_value;

        Some(VaRResult {
            var,
            expected_shortfall,
            confidence: self.confidence,
            method: VaRMethod::Parametric,
            lookback: window,
            portfolio_value,
            var_pct: var / portfolio_value,
        })
    }

    /// Calculate VaR using Monte Carlo simulation
    pub fn monte_carlo_var(
        &self,
        returns: &[f64],
        portfolio_value: f64,
        simulations: usize,
    ) -> Option<VaRResult> {
        if returns.is_empty() {
            return None;
        }

        let n = returns.len();
        let window = self.lookback.min(n);

        // Correlated returns approach: sample with replacement from historical returns
        // and bootstrap the distribution
        use rand::Rng;
        let mut rng = rand::thread_rng();
        let recent_returns = &returns[n - window..];

        let mut simulated_returns: Vec<f64> = Vec::with_capacity(simulations);
        for _ in 0..simulations {
            // Bootstrap: randomly sample returns and compound them
            let n_draws = 21; // ~1 month
            let mut sim_return = 0.0;
            for _ in 0..n_draws {
                let idx = rng.gen_range(0..window);
                sim_return += recent_returns[idx];
            }
            simulated_returns.push(sim_return);
        }

        simulated_returns.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        let var_idx = ((1.0 - self.confidence) * simulations as f64).floor() as usize;
        let var_idx = var_idx.min(simulations.saturating_sub(1));

        let var_return = simulated_returns[var_idx];
        let var = (-var_return) * portfolio_value;

        let es_returns: f64 = simulated_returns
            .iter()
            .take(var_idx + 1)
            .sum::<f64>()
            / (var_idx + 1) as f64;

        let expected_shortfall = (-es_returns) * portfolio_value;

        Some(VaRResult {
            var,
            expected_shortfall,
            confidence: self.confidence,
            method: VaRMethod::MonteCarlo { simulations },
            lookback: window,
            portfolio_value,
            var_pct: var / portfolio_value,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_historical_var() {
        let calculator = VaRCalculator::new(0.95, 100);
        // Generate some daily returns with a few large negative ones
        let returns: Vec<f64> = (0..100)
            .map(|_| 0.001 + (rand::random::<f64>() - 0.5) * 0.02)
            .collect();

        let result = calculator.historical_var(&returns, 1_000_000.0).unwrap();
        assert!(result.var > 0.0);
        assert!(result.var_pct > 0.0);
        assert!(result.expected_shortfall >= result.var);
    }

    #[test]
    fn test_parametric_var() {
        let calculator = VaRCalculator::new(0.95, 100);
        let returns: Vec<f64> = (0..100)
            .map(|_| 0.001 + (rand::random::<f64>() - 0.5) * 0.02)
            .collect();

        let result = calculator.parametric_var(&returns, 1_000_000.0).unwrap();
        assert!(result.var > 0.0);
    }
}
