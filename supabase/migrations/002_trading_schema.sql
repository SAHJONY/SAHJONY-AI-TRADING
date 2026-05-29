-- AI Trading Platform - Trading Schema
-- Run this in Supabase SQL Editor

-- Asset type enum
CREATE TYPE asset_type AS ENUM ('stock', 'crypto', 'forex');
CREATE TYPE order_type AS ENUM ('market', 'limit', 'stop', 'stop_limit');
CREATE TYPE order_side AS ENUM ('buy', 'sell');
CREATE TYPE order_status AS ENUM ('pending', 'filled', 'partial', 'cancelled', 'rejected');
CREATE TYPE strategy_status AS ENUM ('draft', 'active', 'paused', 'archived');

-- Trading portfolios
CREATE TABLE trading_portfolios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  initial_balance DECIMAL(18, 2) NOT NULL DEFAULT 10000.00,
  current_balance DECIMAL(18, 2) NOT NULL DEFAULT 10000.00,
  currency TEXT NOT NULL DEFAULT 'USD',
  is_paper BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Portfolio assets (holdings)
CREATE TABLE trading_holdings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  portfolio_id UUID REFERENCES trading_portfolios(id) ON DELETE CASCADE NOT NULL,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  symbol TEXT NOT NULL,
  asset_type asset_type NOT NULL,
  quantity DECIMAL(18, 8) NOT NULL DEFAULT 0,
  average_price DECIMAL(18, 8) NOT NULL DEFAULT 0,
  current_price DECIMAL(18, 8),
  last_updated TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(portfolio_id, symbol)
);

-- Trading orders
CREATE TABLE trading_orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  portfolio_id UUID REFERENCES trading_portfolios(id) ON DELETE CASCADE NOT NULL,
  symbol TEXT NOT NULL,
  asset_type asset_type NOT NULL,
  order_type order_type NOT NULL,
  side order_side NOT NULL,
  quantity DECIMAL(18, 8) NOT NULL,
  price DECIMAL(18, 8),
  stop_price DECIMAL(18, 8),
  limit_price DECIMAL(18, 8),
  status order_status NOT NULL DEFAULT 'pending',
  filled_quantity DECIMAL(18, 8) DEFAULT 0,
  filled_price DECIMAL(18, 8),
  total_value DECIMAL(18, 2),
  notes TEXT,
  executed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Trading strategies
CREATE TABLE trading_strategies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  strategy_type TEXT NOT NULL DEFAULT 'custom',
  asset_types asset_type[] NOT NULL DEFAULT '{}',
  indicators JSONB DEFAULT '[]',
  conditions JSONB DEFAULT '{}',
  code TEXT,
  status strategy_status NOT NULL DEFAULT 'draft',
  performance_metrics JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Backtest results
CREATE TABLE trading_backtests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  strategy_id UUID REFERENCES trading_strategies(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  symbol TEXT NOT NULL,
  asset_type asset_type NOT NULL,
  timeframe TEXT NOT NULL DEFAULT '1d',
  start_date TIMESTAMPTZ NOT NULL,
  end_date TIMESTAMPTZ NOT NULL,
  initial_capital DECIMAL(18, 2) NOT NULL,
  final_capital DECIMAL(18, 2),
  total_return DECIMAL(10, 4),
  max_drawdown DECIMAL(10, 4),
  sharpe_ratio DECIMAL(10, 4),
  win_rate DECIMAL(10, 4),
  total_trades INTEGER,
  profitable_trades INTEGER,
  losing_trades INTEGER,
  avg_win DECIMAL(18, 2),
  avg_loss DECIMAL(18, 2),
  results_json JSONB DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Watchlists
CREATE TABLE trading_watchlists (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  is_default BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Watchlist items
CREATE TABLE trading_watchlist_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  watchlist_id UUID REFERENCES trading_watchlists(id) ON DELETE CASCADE NOT NULL,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  symbol TEXT NOT NULL,
  asset_type asset_type NOT NULL,
  added_price DECIMAL(18, 8),
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(watchlist_id, symbol)
);

-- Market data cache
CREATE TABLE trading_market_data (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol TEXT NOT NULL,
  asset_type asset_type NOT NULL,
  price DECIMAL(18, 8),
  change_24h DECIMAL(10, 4),
  change_pct_24h DECIMAL(10, 4),
  high_24h DECIMAL(18, 8),
  low_24h DECIMAL(18, 8),
  volume_24h DECIMAL(24, 2),
  market_cap DECIMAL(24, 2),
  data_json JSONB DEFAULT '{}',
  fetched_at TIMESTAMPTZ DEFAULT now(),
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(symbol, asset_type)
);

-- Trading agents junction (connect agents to portfolios)
CREATE TABLE trading_agent_configs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID REFERENCES agents(id) ON DELETE CASCADE NOT NULL,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  portfolio_id UUID REFERENCES trading_portfolios(id) ON DELETE SET NULL,
  auto_trade BOOLEAN DEFAULT false,
  max_position_size DECIMAL(10, 4) DEFAULT 0.1,
  risk_level TEXT DEFAULT 'medium' CHECK (risk_level IN ('low', 'medium', 'high')),
  allowed_assets asset_type[] DEFAULT '{}',
  trading_config JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(agent_id)
);

-- Indexes
CREATE INDEX idx_trading_portfolios_user ON trading_portfolios(user_id);
CREATE INDEX idx_trading_holdings_portfolio ON trading_holdings(portfolio_id);
CREATE INDEX idx_trading_holdings_user ON trading_holdings(user_id);
CREATE INDEX idx_trading_orders_user ON trading_orders(user_id);
CREATE INDEX idx_trading_orders_portfolio ON trading_orders(portfolio_id);
CREATE INDEX idx_trading_orders_symbol ON trading_orders(symbol);
CREATE INDEX idx_trading_strategies_user ON trading_strategies(user_id);
CREATE INDEX idx_trading_backtests_user ON trading_backtests(user_id);
CREATE INDEX idx_trading_backtests_strategy ON trading_backtests(strategy_id);
CREATE INDEX idx_trading_watchlists_user ON trading_watchlists(user_id);
CREATE INDEX idx_trading_watchlist_items_watchlist ON trading_watchlist_items(watchlist_id);
CREATE INDEX idx_trading_market_data_symbol ON trading_market_data(symbol);
CREATE INDEX idx_trading_agent_configs_agent ON trading_agent_configs(agent_id);

-- Enable RLS
ALTER TABLE trading_portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_holdings ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_strategies ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_backtests ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_watchlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_watchlist_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_market_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE trading_agent_configs ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Users can only access their own data
CREATE POLICY "Users can manage own portfolios" ON trading_portfolios
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own holdings" ON trading_holdings
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own orders" ON trading_orders
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own strategies" ON trading_strategies
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own backtests" ON trading_backtests
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own watchlists" ON trading_watchlists
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users manage watchlist items" ON trading_watchlist_items
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can read market data" ON trading_market_data
  FOR SELECT USING (true);

CREATE POLICY "Users can manage own agent trading configs" ON trading_agent_configs
  FOR ALL USING (auth.uid() = user_id);

-- Updated_at triggers
CREATE TRIGGER trading_portfolios_updated_at
  BEFORE UPDATE ON trading_portfolios
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trading_holdings_updated_at
  BEFORE UPDATE ON trading_holdings
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trading_orders_updated_at
  BEFORE UPDATE ON trading_orders
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trading_strategies_updated_at
  BEFORE UPDATE ON trading_strategies
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trading_backtests_updated_at
  BEFORE UPDATE ON trading_backtests
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trading_watchlists_updated_at
  BEFORE UPDATE ON trading_watchlists
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trading_agent_configs_updated_at
  BEFORE UPDATE ON trading_agent_configs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
