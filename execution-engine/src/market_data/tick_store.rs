// ─────────────────────────────────────────────────────────────
// Tick Store - Ring-buffer based time-series tick storage
// ─────────────────────────────────────────────────────────────

use dashmap::DashMap;
use parking_lot::Mutex;
use rust_decimal::Decimal;

use crate::types::{NanosTimestamp, OHLCVBar, Quote, Symbol, Trade};

/// Compressed tick data stored per symbol
#[derive(Debug, Clone)]
pub struct TickData {
    pub symbol: Symbol,
    pub timestamp: NanosTimestamp,
    pub bid: Decimal,
    pub ask: Decimal,
    pub last_price: Decimal,
    pub last_size: f64,
    pub volume: f64,
    pub vwap: Decimal,
}

// TickData is composed of Send + Sync types (Symbol, NanosTimestamp, Decimal, f64),
// so Send + Sync are automatically derived by the compiler.

impl TickData {
    pub fn mid_price(&self) -> Decimal {
        (self.bid + self.ask) / Decimal::from(2)
    }
}

/// Ring-buffer based tick store for efficient time-series operations
pub struct TickStore {
    /// Ticks per symbol (ring buffer protected by a mutex)
    ticks: DashMap<Symbol, Mutex<RingBuffer<TickData>>>,
    /// OHLCV bar builders per symbol (protected by mutex)
    bar_builders: DashMap<Symbol, Mutex<Vec<BarBuilder>>>,
    /// Default capacity per symbol
    capacity: usize,
    /// Default bar durations
    bar_durations: Vec<i64>,
}

impl TickStore {
    pub fn new(capacity: usize) -> Self {
        Self {
            ticks: DashMap::new(),
            bar_builders: DashMap::new(),
            capacity,
            bar_durations: vec![
                60_000_000_000,     // 1m
                300_000_000_000,    // 5m
                900_000_000_000,    // 15m
                3_600_000_000_000,  // 1h
                86_400_000_000_000, // 1d
            ],
        }
    }

    /// Insert a new tick from a quote
    pub fn insert_from_quote(&self, quote: &Quote) {
        let tick = TickData {
            symbol: quote.symbol.clone(),
            timestamp: quote.timestamp,
            bid: quote.bid_price,
            ask: quote.ask_price,
            last_price: quote.mid_price(),
            last_size: 0.0,
            volume: 0.0,
            vwap: quote.mid_price(),
        };

        self.insert_tick(tick);
    }

    /// Insert a new tick from a trade
    pub fn insert_from_trade(&self, trade: &Trade) {
        let tick = TickData {
            symbol: trade.symbol.clone(),
            timestamp: trade.timestamp,
            bid: trade.price, // Approximate from last trade
            ask: trade.price,
            last_price: trade.price,
            last_size: trade.size,
            volume: trade.size,
            vwap: trade.price,
        };

        self.insert_tick(tick);
    }

    /// Insert tick data
    fn insert_tick(&self, tick: TickData) {
        let symbol = tick.symbol.clone();

        // Store in ring buffer (lock the mutex)
        {
            let mut buffer = self
                .ticks
                .entry(symbol.clone())
                .or_insert_with(|| Mutex::new(RingBuffer::new(self.capacity)))
                .lock();
            buffer.push(tick.clone());
        }

        // Update bar builders (lock the mutex)
        {
            let mut builders = self
                .bar_builders
                .entry(symbol)
                .or_insert_with(|| {
                    Mutex::new(
                        self.bar_durations
                            .iter()
                            .map(|&dur| BarBuilder::new(dur))
                            .collect(),
                    )
                })
                .lock();
            builders
                .iter_mut()
                .for_each(|bb| bb.process(tick.clone()));
        }
    }

    /// Get recent ticks for a symbol
    pub fn get_recent(&self, symbol: &Symbol, count: usize) -> Vec<TickData> {
        self.ticks
            .get(symbol)
            .map(|buf| buf.lock().iter_recent(count).cloned().collect())
            .unwrap_or_default()
    }

    /// Get ticks within a time window
    pub fn get_window(
        &self,
        symbol: &Symbol,
        start: NanosTimestamp,
        end: NanosTimestamp,
    ) -> Vec<TickData> {
        self.ticks
            .get(symbol)
            .map(|buf| {
                let lock = buf.lock();
                lock.iter_recent(self.capacity)
                    .filter(|t| t.timestamp >= start && t.timestamp <= end)
                    .cloned()
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Get latest OHLCV bar for a duration
    pub fn get_latest_bar(&self, symbol: &Symbol, duration_ns: i64) -> Option<OHLCVBar> {
        self.bar_builders.get(symbol).and_then(|builders| {
            let lock = builders.lock();
            lock.iter()
                .find(|b| b.bar_duration_ns == duration_ns)
                .map(|b| b.current_bar.clone())
        })
    }

    /// Get completed bars for a symbol
    pub fn get_completed_bars(
        &self,
        symbol: &Symbol,
        duration_ns: i64,
    ) -> Vec<OHLCVBar> {
        self.bar_builders
            .get(symbol)
            .map(|builders| {
                let lock = builders.lock();
                lock.iter()
                    .find(|b| b.bar_duration_ns == duration_ns)
                    .map(|b| b.completed_bars.clone())
                    .unwrap_or_default()
            })
            .unwrap_or_default()
    }
}

// ── Ring Buffer ──

struct RingBuffer<T: Clone> {
    data: Vec<Option<T>>,
    head: usize,
    capacity: usize,
    len: usize,
}

impl<T: Clone> RingBuffer<T> {
    fn new(capacity: usize) -> Self {
        Self {
            data: vec![None; capacity],
            head: 0,
            capacity,
            len: 0,
        }
    }

    fn push(&mut self, item: T) {
        let idx = (self.head + self.len) % self.capacity;
        if self.len == self.capacity {
            // Overwrite oldest
            self.data[idx] = Some(item);
            self.head = (self.head + 1) % self.capacity;
        } else {
            self.data[idx] = Some(item);
            self.len += 1;
        }
    }

    fn iter_recent(&self, count: usize) -> impl Iterator<Item = &T> {
        let count = count.min(self.len);
        let start = if self.len < self.capacity {
            0
        } else {
            (self.head + self.len - count) % self.capacity
        };

        (0..count).filter_map(move |i| {
            let idx = (start + i) % self.capacity;
            self.data[idx].as_ref()
        })
    }
}

// ── Bar Builder ──

struct BarBuilder {
    bar_duration_ns: i64,
    current_bar: OHLCVBar,
    completed_bars: Vec<OHLCVBar>,
    bar_start: i64,
}

impl BarBuilder {
    fn new(bar_duration_ns: i64) -> Self {
        Self {
            bar_duration_ns,
            current_bar: OHLCVBar {
                symbol: Symbol("".into()),
                timestamp: NanosTimestamp(0),
                open: Decimal::ZERO,
                high: Decimal::ZERO,
                low: Decimal::ZERO,
                close: Decimal::ZERO,
                volume: 0.0,
                vwap: Decimal::ZERO,
                trade_count: 0,
                bar_duration_ns,
            },
            completed_bars: Vec::new(),
            bar_start: 0,
        }
    }

    fn process(&mut self, tick: TickData) {
        let ts = tick.timestamp.as_nanos();
        let bar_idx = ts / self.bar_duration_ns;
        let bar_start = bar_idx * self.bar_duration_ns;

        if bar_start != self.bar_start {
            // Close current bar, start new one
            if self.current_bar.trade_count > 0 {
                self.completed_bars.push(self.current_bar.clone());
                if self.completed_bars.len() > 1000 {
                    self.completed_bars.remove(0);
                }
            }

            self.bar_start = bar_start;
            self.current_bar = OHLCVBar {
                symbol: tick.symbol.clone(),
                timestamp: NanosTimestamp(bar_start),
                open: tick.last_price,
                high: tick.last_price,
                low: tick.last_price,
                close: tick.last_price,
                volume: tick.volume,
                vwap: Decimal::ZERO,
                trade_count: 1,
                bar_duration_ns: self.bar_duration_ns,
            };
        } else {
            // Update current bar
            self.current_bar.high = self.current_bar.high.max(tick.last_price);
            self.current_bar.low = if self.current_bar.low.is_zero() {
                tick.last_price
            } else {
                self.current_bar.low.min(tick.last_price)
            };
            self.current_bar.close = tick.last_price;
            self.current_bar.volume += tick.volume;
            self.current_bar.trade_count += 1;
            self.current_bar.symbol = tick.symbol;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ring_buffer() {
        let mut buf = RingBuffer::new(5);
        buf.push(1);
        buf.push(2);
        buf.push(3);

        let items: Vec<i32> = buf.iter_recent(3).copied().collect();
        assert_eq!(items, vec![1, 2, 3]);

        buf.push(4);
        buf.push(5);
        buf.push(6);
        buf.push(7);

        let items: Vec<i32> = buf.iter_recent(5).copied().collect();
        assert_eq!(items, vec![3, 4, 5, 6, 7]);
    }
}
