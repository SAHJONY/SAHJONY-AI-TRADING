// ─────────────────────────────────────────────────────────────
// Utilities - Common helpers across the engine
// ─────────────────────────────────────────────────────────────

use rust_decimal::Decimal;

/// Round a decimal to a given number of decimal places
pub fn round_decimal(value: Decimal, places: u32) -> Decimal {
    let factor = Decimal::from(10_i64.pow(places));
    (value * factor).round() / factor
}

/// Clamp a value between min and max
pub fn clamp<T: PartialOrd>(value: T, min: T, max: T) -> T {
    if value < min {
        min
    } else if value > max {
        max
    } else {
        value
    }
}

/// Calculate logarithmic return: ln(P_t / P_{t-1})
pub fn log_return(current: Decimal, previous: Decimal) -> f64 {
    if current.is_zero() || previous.is_zero() {
        return 0.0;
    }
    let ratio = (current / previous).to_f64().unwrap_or(1.0);
    ratio.ln()
}

/// Calculate simple return: (P_t - P_{t-1}) / P_{t-1}
pub fn simple_return(current: Decimal, previous: Decimal) -> f64 {
    if previous.is_zero() {
        return 0.0;
    }
    ((current - previous) / previous)
        .to_f64()
        .unwrap_or(0.0)
}

/// Calculate rolling mean of a slice
pub fn rolling_mean(data: &[f64], window: usize) -> Vec<f64> {
    if data.is_empty() || window == 0 || window > data.len() {
        return data.to_vec();
    }

    let mut result = Vec::with_capacity(data.len());
    let mut sum: f64 = data[..window].iter().sum();

    for i in 0..data.len() {
        if i < window {
            result.push(data[..i + 1].iter().sum::<f64>() / (i + 1) as f64);
        } else {
            sum = sum - data[i - window] + data[i];
            result.push(sum / window as f64);
        }
    }

    result
}

/// Calculate rolling standard deviation
pub fn rolling_std(data: &[f64], window: usize) -> Vec<f64> {
    let mean = rolling_mean(data, window);
    let mut result = Vec::with_capacity(data.len());

    for i in 0..data.len() {
        let start = if i >= window { i - window + 1 } else { 0 };
        let slice = &data[start..=i];
        let m = mean[i];
        let variance = slice.iter().map(|x| (x - m).powi(2)).sum::<f64>() / slice.len() as f64;
        result.push(variance.sqrt());
    }

    result
}

/// Sharper ratio: (mean - risk_free) / std_dev, annualized
pub fn sharpe_ratio(returns: &[f64], risk_free_rate: f64, periods_per_year: f64) -> f64 {
    if returns.is_empty() {
        return 0.0;
    }

    let mean = returns.iter().sum::<f64>() / returns.len() as f64;
    let variance = returns
        .iter()
        .map(|r| (r - mean).powi(2))
        .sum::<f64>()
        / (returns.len() - 1) as f64;
    let std_dev = variance.sqrt();

    if std_dev.abs() < f64::EPSILON {
        return 0.0;
    }

    ((mean - risk_free_rate) / std_dev) * periods_per_year.sqrt()
}

/// Sortino ratio: uses only downside deviation
pub fn sortino_ratio(returns: &[f64], risk_free_rate: f64, periods_per_year: f64) -> f64 {
    if returns.is_empty() {
        return 0.0;
    }

    let mean = returns.iter().sum::<f64>() / returns.len() as f64;
    let downside_variance = returns
        .iter()
        .filter(|&&r| r < 0.0)
        .map(|r| r.powi(2))
        .sum::<f64>()
        / returns.len() as f64;

    let downside_std = downside_variance.sqrt();

    if downside_std.abs() < f64::EPSILON {
        return if mean > 0.0 { f64::INFINITY } else { 0.0 };
    }

    ((mean - risk_free_rate) / downside_std) * periods_per_year.sqrt()
}

/// Maximum drawdown from peak
pub fn max_drawdown(equity_curve: &[f64]) -> f64 {
    if equity_curve.is_empty() {
        return 0.0;
    }

    let mut peak = equity_curve[0];
    let mut max_dd = 0.0;

    for &value in equity_curve.iter().skip(1) {
        if value > peak {
            peak = value;
        }
        let dd = (peak - value) / peak;
        if dd > max_dd {
            max_dd = dd;
        }
    }

    max_dd
}

/// Profit factor: sum(gains) / sum(losses)
pub fn profit_factor(pnls: &[f64]) -> f64 {
    let gains: f64 = pnls.iter().filter(|&&x| x > 0.0).sum();
    let losses: f64 = pnls.iter().filter(|&&x| x < 0.0).map(|x| x.abs()).sum();

    if losses.abs() < f64::EPSILON {
        return if gains > 0.0 { f64::INFINITY } else { 0.0 };
    }

    gains / losses
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sharpe_ratio() {
        let returns = vec![0.01, 0.02, -0.01, 0.015, -0.005, 0.01];
        let sharpe = sharpe_ratio(&returns, 0.0, 252.0);
        assert!(sharpe > 0.0);
    }

    #[test]
    fn test_max_drawdown() {
        let equity = vec![100.0, 110.0, 95.0, 105.0, 120.0, 80.0, 90.0];
        let dd = max_drawdown(&equity);
        assert!((dd - 0.333).abs() < 0.01); // (120-80)/120 = 0.333
    }

    #[test]
    fn test_profit_factor() {
        let pnls = vec![10.0, -5.0, 15.0, -3.0, 7.0];
        let pf = profit_factor(&pnls);
        assert!((pf - 4.0).abs() < 0.1); // (10+15+7)/(5+3) = 32/8 = 4.0
    }
}
