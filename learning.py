# Self-learning module for the trading system

import json
import os
from datetime import datetime
from performance import PerformanceMonitor
from strategy import TradingStrategy

class AdaptiveLearning:
    def __init__(self, config_file="learning_config.json"):
        self.config_file = config_file
        self.performance_history = []
        self.strategy = TradingStrategy()
        self.performance = PerformanceMonitor()
        self.load_config()
    
    def load_config(self):
        """Load the learning configuration"""
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f:
                self.config = json.load(f)
        else:
            self.config = {
                "learning_rate": 0.01,
                "exploration_rate": 0.1,
                "max_position_size": 0.02,
                "risk_tolerance": 0.02,
                "min_confidence": 0.7
            }
            self.save_config()
    
    def save_config(self):
        """Save the learning configuration"""
        with open(self.config_file, "w") as f:
            json.dump(self.config, f, indent=2)
    
    def update_performance_history(self, metrics):
        """Update the performance history with new metrics"""
        self.performance_history.append({
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics
        })
        
        # Keep only the last 30 days of performance data
        if len(self.performance_history) > 30:
            self.performance_history = self.performance_history[-30:]
        
        # Save to file
        with open("performance_history.json", "w") as f:
            json.dump(self.performance_history, f, indent=2)
    
    def analyze_performance(self):
        """Analyze performance and adjust configuration"""
        perf_summary = self.performance.get_performance_summary()
        self.update_performance_history(perf_summary)
        
        # Simple learning algorithm:
        # If we're winning more than 55% of the time, increase position size
        # If we're winning less than 45% of the time, decrease position size
        if perf_summary['win_rate'] > 0.55:
            self.config["max_position_size"] = min(0.05, self.config["max_position_size"] * 1.1)
        elif perf_summary['win_rate'] < 0.45:
            self.config["max_position_size"] = max(0.005, self.config["max_position_size"] * 0.9)
        
        # Adjust risk tolerance based on Sharpe ratio
        if perf_summary['sharpe_ratio'] > 1.0:
            self.config["risk_tolerance"] = min(0.05, self.config["risk_tolerance"] * 1.05)
        elif perf_summary['sharpe_ratio'] < 0.5:
            self.config["risk_tolerance"] = max(0.01, self.config["risk_tolerance"] * 0.95)
        
        self.save_config()
        return self.config

# Initialize the adaptive learning module
al = AdaptiveLearning()
print("Adaptive learning module initialized")