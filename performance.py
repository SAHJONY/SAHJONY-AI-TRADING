# Performance monitoring module for the trading system

import time
from datetime import datetime
from trading_system import TradingSystem

class PerformanceMonitor:
    def __init__(self):
        self.trading_system = TradingSystem()
        self.metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0
        }
        self.start_time = datetime.now()
    
    def update_metrics(self, trade_result):
        """Update performance metrics based on trade results"""
        self.metrics['total_trades'] += 1
        
        if trade_result > 0:
            self.metrics['winning_trades'] += 1
            self.metrics['total_pnl'] += trade_result
        else:
            self.metrics['losing_trades'] += 1
            self.metrics['total_pnl'] += trade_result
        
        # Update drawdown if necessary
        if trade_result < 0 and abs(trade_result) > self.metrics['max_drawdown']:
            self.metrics['max_drawdown'] = abs(trade_result)
    
    def calculate_sharpe_ratio(self):
        """Calculate the Sharpe ratio based on current performance"""
        # Simplified Sharpe ratio calculation
        if self.metrics['total_trades'] > 0:
            avg_return = self.metrics['total_pnl'] / self.metrics['total_trades']
            self.metrics['sharpe_ratio'] = avg_return / 0.02  # Simplified risk-free rate
        return self.metrics['sharpe_ratio']
    
    def get_performance_summary(self):
        """Get a summary of the current performance metrics"""
        return {
            'total_trades': self.metrics['total_trades'],
            'win_rate': self.metrics['winning_trades'] / max(1, self.metrics['total_trades']),
            'total_pnl': self.metrics['total_pnl'],
            'max_drawdown': self.metrics['max_drawdown'],
            'sharpe_ratio': self.calculate_sharpe_ratio(),
            'uptime': str(datetime.now() - self.start_time)
        }
    
    def reset_metrics(self):
        """Reset all performance metrics"""
        self.metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0
        }
        self.start_time = datetime.now()

# Initialize the performance monitor
pm = PerformanceMonitor()
print("Performance monitor initialized")