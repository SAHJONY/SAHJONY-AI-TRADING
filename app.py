#!/usr/bin/env python3

import time
from datetime import datetime
from trading_system import TradingSystem
from simulator import TradingSimulator
from performance import PerformanceMonitor

def main():
    print("Sahjony Capital LLC - AI Trading Firm")
    print("==================================")
    
    # Initialize system components
    trading_system = TradingSystem()
    simulator = TradingSimulator()
    performance = PerformanceMonitor()
    
    # Display system status
    status = trading_system.get_status()
    print("\nSystem Status:")
    for component, status in status.items():
        print(f"{component}: {status}")
    
    # Run a simulation
    print("\nRunning trading simulation...")
    simulator.simulate_trading_day()
    
    # Display performance metrics
    perf_summary = performance.get_performance_summary()
    print("\nPerformance Summary:")
    for metric, value in perf_summary.items():
        print(f"{metric}: {value}")
    
    print("\nAI Trading Firm is operational and ready for trading.")

if __name__ == "__main__":
    main()