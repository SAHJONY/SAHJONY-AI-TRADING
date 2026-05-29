// ─────────────────────────────────────────────────────────────
// Core types shared across all modules
// ─────────────────────────────────────────────────────────────

use chrono::{DateTime, Utc};
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};
use std::fmt;
use uuid::Uuid;

// ── Identifiers ──

/// Unique order identifier (client-assigned)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ClientOrderId(pub Uuid);

impl ClientOrderId {
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl fmt::Display for ClientOrderId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// Exchange-assigned order identifier
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ExchangeOrderId(pub String);

impl fmt::Display for ExchangeOrderId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

/// Execution identifier
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ExecutionId(pub String);

/// Strategy identifier
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct StrategyId(pub String);

/// Account identifier
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct AccountId(pub String);

/// Trading symbol (e.g., "AAPL", "ESM4")
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Symbol(pub String);

impl fmt::Display for Symbol {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl From<&str> for Symbol {
    fn from(s: &str) -> Self {
        Symbol(s.to_uppercase())
    }
}

/// Exchange identifier
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Exchange(pub String);

// ── Order Enums ──

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OrderSide {
    Buy,
    Sell,
    SellShort,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OrderType {
    Market,
    Limit,
    Stop,
    StopLimit,
    TrailingStop,
    Iceberg,
    Pegged,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TimeInForce {
    Day,
    GoodTillCancelled,
    ImmediateOrCancel,
    FillOrKill,
    GoodTillDate(DateTime<Utc>),
    AtTheClose,
    ExtendedHours,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OrderStatus {
    PendingNew,
    New,
    PartiallyFilled,
    Filled,
    PendingCancel,
    Cancelled,
    Rejected,
    Expired,
    Suspended,
}

// ── Market Data Types ──

/// Nanosecond-precision timestamp (nanos since Unix epoch)
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct NanosTimestamp(pub i64);

impl NanosTimestamp {
    pub fn now() -> Self {
        Self(chrono::Utc::now().timestamp_nanos_opt().unwrap_or(0))
    }

    pub fn from_micros(micros: i64) -> Self {
        Self(micros.saturating_mul(1_000))
    }

    pub fn as_nanos(&self) -> i64 {
        self.0
    }

    pub fn as_micros(&self) -> i64 {
        self.0 / 1_000
    }

    pub fn duration_since(&self, earlier: NanosTimestamp) -> std::time::Duration {
        let nanos = (self.0 - earlier.0).max(0) as u64;
        std::time::Duration::from_nanos(nanos)
    }
}

/// Quote represents Level 1 market data
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Quote {
    pub symbol: Symbol,
    pub exchange: Exchange,
    pub timestamp: NanosTimestamp,
    pub bid_price: Decimal,
    pub bid_size: f64,
    pub ask_price: Decimal,
    pub ask_size: f64,
    pub condition: QuoteCondition,
    pub sequence_number: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum QuoteCondition {
    Normal,
    Closing,
    Halted,
    FastMarket,
    Crossed,
}

impl Quote {
    pub fn mid_price(&self) -> Decimal {
        (self.bid_price + self.ask_price) / Decimal::from(2)
    }

    pub fn spread(&self) -> Decimal {
        self.ask_price - self.bid_price
    }

    pub fn spread_bps(&self) -> f64 {
        let mid = self.mid_price();
        if mid.is_zero() {
            return 0.0;
        }
        let spread = self.spread();
        (spread / mid).to_f64().unwrap_or(0.0) * 10_000.0
    }
}

/// Trade tick
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Trade {
    pub symbol: Symbol,
    pub exchange: Exchange,
    pub timestamp: NanosTimestamp,
    pub price: Decimal,
    pub size: f64,
    pub condition: TradeCondition,
    pub sequence_number: u64,
    pub trade_id: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TradeCondition {
    Normal,
    FormT,
    OutOfSequence,
    IntermarketSweep,
    OddLot,
    Correction,
}

/// Order book level
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct OrderBookLevel {
    pub price: Decimal,
    pub size: f64,
    pub order_count: u32,
}

/// Full order book snapshot
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderBookSnapshot {
    pub symbol: Symbol,
    pub exchange: Exchange,
    pub timestamp: NanosTimestamp,
    pub bids: Vec<OrderBookLevel>,
    pub asks: Vec<OrderBookLevel>,
    pub sequence_number: u64,
}

/// OHLCV bar
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OHLCVBar {
    pub symbol: Symbol,
    pub timestamp: NanosTimestamp,
    pub open: Decimal,
    pub high: Decimal,
    pub low: Decimal,
    pub close: Decimal,
    pub volume: f64,
    pub vwap: Decimal,
    pub trade_count: u32,
    pub bar_duration_ns: i64,
}

// ── Order Types ──

/// New order request
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NewOrderRequest {
    pub symbol: Symbol,
    pub exchange: Exchange,
    pub side: OrderSide,
    pub order_type: OrderType,
    pub time_in_force: TimeInForce,
    pub quantity: f64,
    pub price: Option<Decimal>,
    pub stop_price: Option<Decimal>,
    pub trailing_amount: Option<Decimal>,
    pub display_quantity: Option<f64>,
    pub client_order_id: ClientOrderId,
    pub strategy_id: StrategyId,
    pub account_id: AccountId,
    pub tags: std::collections::HashMap<String, String>,
}

/// Order state (tracked internally)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderState {
    pub client_order_id: ClientOrderId,
    pub exchange_order_id: Option<ExchangeOrderId>,
    pub symbol: Symbol,
    pub exchange: Exchange,
    pub side: OrderSide,
    pub order_type: OrderType,
    pub time_in_force: TimeInForce,
    pub status: OrderStatus,
    pub quantity: f64,
    pub price: Option<Decimal>,
    pub stop_price: Option<Decimal>,
    pub executed_quantity: f64,
    pub executed_notional: Decimal,
    pub average_fill_price: Option<Decimal>,
    pub remaining_quantity: f64,
    pub created_at: NanosTimestamp,
    pub updated_at: NanosTimestamp,
    pub strategy_id: StrategyId,
    pub account_id: AccountId,
}

/// Execution report
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionReport {
    pub client_order_id: ClientOrderId,
    pub exchange_order_id: ExchangeOrderId,
    pub execution_id: ExecutionId,
    pub order_status: OrderStatus,
    pub symbol: Symbol,
    pub side: OrderSide,
    pub executed_quantity: f64,
    pub executed_price: Decimal,
    pub remaining_quantity: f64,
    pub commission: Option<Decimal>,
    pub commission_currency: Option<String>,
    pub timestamp: NanosTimestamp,
    pub exchange_timestamp: NanosTimestamp,
    pub liquidity_flag: Option<String>,
}

/// Position
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Position {
    pub symbol: Symbol,
    pub account_id: AccountId,
    pub quantity: f64,
    pub average_entry_price: Decimal,
    pub realized_pnl: Decimal,
    pub unrealized_pnl: Decimal,
    pub market_price: Decimal,
    pub market_value: Decimal,
    pub last_update: NanosTimestamp,
}

impl Position {
    pub fn total_pnl(&self) -> Decimal {
        self.realized_pnl + self.unrealized_pnl
    }

    pub fn side(&self) -> OrderSide {
        if self.quantity > 0.0 {
            OrderSide::Buy
        } else if self.quantity < 0.0 {
            OrderSide::SellShort
        } else {
            OrderSide::Buy // Flat
        }
    }
}

// ── Market State ──

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MarketState {
    PreOpen,
    Open,
    Paused,
    Halted,
    Closing,
    Closed,
    PostClose,
}
