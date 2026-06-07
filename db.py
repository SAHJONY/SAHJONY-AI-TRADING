# Simple database implementation for the trading firm

import sqlite3
import os

class TradingFirmDB:
    def __init__(self, db_path="./data/trading_firm.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                quantity REAL NOT NULL,
                avg_price REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS risk_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def record_trade(self, symbol, quantity, price):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (symbol, quantity, price)
            VALUES (?, ?, ?)
        ''', (symbol, quantity, price))
        conn.commit()
        conn.close()
    
    def update_position(self, symbol, quantity, avg_price):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO positions (id, symbol, quantity, avg_price)
            VALUES (
                (SELECT id FROM positions WHERE symbol = ?),
                ?, ?, ?
            )
        ''', (symbol, symbol, quantity, avg_price))
        conn.commit()
        conn.close()
    
    def record_risk_metric(self, metric_name, value):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO risk_metrics (metric_name, value)
            VALUES (?, ?)
        ''', (metric_name, value))
        conn.commit()
        conn.close()

# Initialize the database
db = TradingFirmDB()
print("Database initialized successfully")