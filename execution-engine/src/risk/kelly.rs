// ─────────────────────────────────────────────────────────────
// Kelly Criterion - Optimal position sizing for long-term growth
// ─────────────────────────────────────────────────────────────

/// Kelly Criterion calculator for position sizing
pub struct KellyCriterion {
    /// Fraction of full Kelly to use (0.0–1.0)
    /// Full Kelly = 1.0, Half Kelly = 0.5, Quarter Kelly = 0.25
    fraction: f64,
    /// Minimum bet size (to avoid zero-size bets from estimation errors)
    min_bet_pct: f64,
    /// Maximum bet size (cap on position size)
    max_bet_pct: f64,
}

/// Kelly result
#[derive(Debug, Clone)]
pub struct KellyResult {
    /// Optimal fraction of capital to allocate
    pub optimal_fraction: f64,
    /// Adjusted fraction (with our fraction multiplier)
    pub adjusted_fraction: f64,
    /// Dollar amount to allocate
    pub dollar_amount: f64,
    /// Expected growth rate per bet
    pub expected_growth: f64,
    /// Win probability used
    pub win_probability: f64,
    /// Win/loss ratio (avg_win / avg_loss)
    pub win_loss_ratio: f64,
    /// Whether the bet has positive edge
    pub has_edge: bool,
}

impl KellyCriterion {
    pub fn new(fraction: f64, min_bet_pct: f64, max_bet_pct: f64) -> Self {
        Self {
            fraction: fraction.clamp(0.0, 1.0),
            min_bet_pct,
            max_bet_pct,
        }
    }

    /// Calculate Kelly fraction for a single bet
    ///
    /// Arguments:
    /// - win_probability: probability of winning (0-1)
    /// - win_loss_ratio: ratio of average win to average loss (must be > 0)
    /// - capital: total available capital for position sizing
    pub fn calculate(
        &self,
        win_probability: f64,
        win_loss_ratio: f64,
        capital: f64,
    ) -> KellyResult {
        let b = win_loss_ratio; // Net odds
        let p = win_probability.clamp(0.0, 1.0);
        let q = 1.0 - p; // Loss probability

        // Kelly formula: f* = (bp - q) / b = p - q/b
        let optimal_fraction = if b > 0.0 {
            (b * p - q) / b
        } else {
            0.0
        };

        let has_edge = optimal_fraction > 0.0;

        // Apply fractional Kelly and caps
        let mut adjusted = optimal_fraction * self.fraction;
        adjusted = adjusted.clamp(self.min_bet_pct, self.max_bet_pct);

        if !has_edge {
            adjusted = 0.0; // No positive expected value = don't bet
        }

        // Expected growth: g = p*ln(1 + b*f) + q*ln(1 - f)
        let expected_growth = if adjusted > 0.0 && adjusted < 1.0 && b > 0.0 {
            p * (1.0 + b * adjusted).ln() + q * (1.0 - adjusted).ln()
        } else {
            0.0
        };

        KellyResult {
            optimal_fraction,
            adjusted_fraction: adjusted,
            dollar_amount: capital * adjusted,
            expected_growth,
            win_probability: p,
            win_loss_ratio: b,
            has_edge,
        }
    }

    /// Calculate Kelly based on historical trade outcomes
    pub fn calculate_from_history(
        &self,
        trade_pnls: &[f64],
        capital: f64,
    ) -> KellyResult {
        if trade_pnls.is_empty() {
            return KellyResult {
                optimal_fraction: 0.0,
                adjusted_fraction: 0.0,
                dollar_amount: 0.0,
                expected_growth: 0.0,
                win_probability: 0.0,
                win_loss_ratio: 0.0,
                has_edge: false,
            };
        }

        let wins: Vec<f64> = trade_pnls.iter().copied().filter(|&x| x > 0.0).collect();
        let losses: Vec<f64> = trade_pnls.iter().copied().filter(|&x| x < 0.0).collect();

        let win_probability = wins.len() as f64 / trade_pnls.len() as f64;

        let avg_win = if wins.is_empty() {
            0.0
        } else {
            wins.iter().sum::<f64>() / wins.len() as f64
        };

        let avg_loss = if losses.is_empty() {
            1.0 // Avoid division by zero
        } else {
            losses.iter().map(|x| x.abs()).sum::<f64>() / losses.len() as f64
        };

        let win_loss_ratio = if avg_loss > 0.0 {
            avg_win / avg_loss
        } else {
            0.0
        };

        self.calculate(win_probability, win_loss_ratio, capital)
    }

    /// Calculate position size for a specific trade
    pub fn position_size(
        &self,
        win_probability: f64,
        expected_return: f64,
        risk_per_trade: f64,
        capital: f64,
    ) -> f64 {
        if risk_per_trade <= 0.0 || capital <= 0.0 {
            return 0.0;
        }

        let win_loss_ratio = expected_return / risk_per_trade;
        let result = self.calculate(win_probability, win_loss_ratio, capital);
        result.dollar_amount
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kelly_positive_edge() {
        let kelly = KellyCriterion::new(0.5, 0.01, 0.25);

        // 60% win rate, 2:1 win/loss ratio
        let result = kelly.calculate(0.6, 2.0, 100_000.0);

        assert!(result.has_edge);
        assert!(result.optimal_fraction > 0.0);
        assert!(result.adjusted_fraction > 0.0);
        assert!(result.dollar_amount > 0.0);

        // Optimal Kelly for p=0.6, b=2.0: f* = (2*0.6 - 0.4)/2 = 0.4
        assert!((result.optimal_fraction - 0.4).abs() < 0.01);
        // Half Kelly = 0.2
        assert!((result.adjusted_fraction - 0.2).abs() < 0.01);
    }

    #[test]
    fn test_kelly_no_edge() {
        let kelly = KellyCriterion::new(0.5, 0.01, 0.25);

        // 50% win rate, 1:1 win/loss ratio = no edge
        let result = kelly.calculate(0.5, 1.0, 100_000.0);

        assert!(!result.has_edge);
        assert_eq!(result.adjusted_fraction, 0.0);
        assert_eq!(result.dollar_amount, 0.0);
    }

    #[test]
    fn test_kelly_from_history() {
        let kelly = KellyCriterion::new(0.5, 0.01, 0.25);

        // Simulate profitable trader: 60 wins, 40 losses, avg win > avg loss
        let pnls: Vec<f64> = (0..60)
            .map(|_| 2.0) // Wins
            .chain((0..40).map(|_| -1.0)) // Losses
            .collect();

        let result = kelly.calculate_from_history(&pnls, 100_000.0);
        assert!(result.has_edge);
        assert!(result.dollar_amount > 0.0);
    }
}
