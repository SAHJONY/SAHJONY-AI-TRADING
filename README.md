# Agent Workforce — Multi-Agent AI Trading System

[![CI](https://github.com/SAHJONY/SAHJONY-AI-TRADING/actions/workflows/test.yml/badge.svg)](https://github.com/SAHJONY/SAHJONY-AI-TRADING/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/SAHJONY/SAHJONY-AI-TRADING/graph/badge.svg)](https://codecov.io/gh/SAHJONY/SAHJONY-AI-TRADING)

A three-layer autonomous trading system built with TypeScript and LangGraph: knowledge enrichment, multi-agent collaborative debate, and self-evolving meta-learning.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         LAYER 3                                   │
│              Knowledge Enrichment Pipeline                        │
│                                                                   │
│  SEC EDGAR → Knowledge Graph → Vector Store → RAG Orchestrator   │
│  News API → Alt Data Aggregator → Composite Sentiment Signals    │
│                                                                   │
│  Provides enriched market context to Layer 4 before each debate   │
└──────────────────────────┬───────────────────────────────────────┘
                           │ enriched market data
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                         LAYER 4                                   │
│              Trading Workforce (LangGraph Debate)                 │
│                                                                   │
│  ┌─────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐              │
│  │  Macro   │ │ Sector  │ │Sentiment │ │Technical │              │
│  │Strategist│ │ Analyst │ │  Agent   │ │ Analyst  │   Supervisor │
│  └────┬─────┘ └────┬────┘ └────┬─────┘ └────┬─────┘      │      │
│       └────────────┐└──────────┐└───────────┐│◄───────────┘      │
│                    ▼            ▼            ▼▼                   │
│              ┌─────────┐ ┌──────────────┐                         │
│              │  Risk    │ │  Execution   │  ◄── Aggregator        │
│              │ Manager  │ │  Optimizer   │      (weighted vote)   │
│              │ (veto)   │ │(order intent)│                        │
│              └─────────┘ └──────────────┘                         │
│                                                                   │
│  Consensus → FinalDecision → OrderIntent → Layer 1 Execution      │
└──────────────────────────┬───────────────────────────────────────┘
                           │ trade outcomes
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                         LAYER 5                                   │
│              Self-Evolving Meta-Learning                          │
│                                                                   │
│  Performance Tracker → Model Router (MAB) → Strategy GA           │
│  Prompt Optimizer   → Backtest Engine    → Walk-Forward Analysis │
│                                                                   │
│  Continuously tracks agent accuracy, evolves weights, and         │
│  optimizes prompts based on trade outcomes                        │
└──────────────────────────────────────────────────────────────────┘
```

### Layer 3 — Knowledge Enrichment

| Component | Description |
|---|---|
| **SEC EDGAR Client** | Fetches company filings (10-K, 10-Q, 8-K) and XBRL financial data |
| **Knowledge Graph** | Entities (Company, Person, Sector, Filing) and their relationships |
| **Vector Store** | LanceDB-backed embeddings for RAG retrieval |
| **RAG Orchestrator** | Retrieval-augmented context generation for trading agents |
| **Alt Data Aggregator** | News sentiment, social media signals, composite indicators |
| **Pipeline** | Scheduled ingestion every 6 hours, on-demand enrichment for debates |

### Layer 4 — Trading Workforce (6-Agent Debate)

| Agent | Role | Description |
|---|---|---|
| **Macro Strategist** | `macro_strategist` | Economic indicators, monetary policy, global trends |
| **Sector Analyst** | `sector_analyst` | Industry dynamics, competitive landscape, sector rotation |
| **Sentiment Agent** | `sentiment_agent` | News sentiment, social media, market psychology |
| **Technical Analyst** | `technical_analyst` | Price action, indicators, chart patterns |
| **Risk Manager** | `risk_manager` | Position sizing, drawdown limits, **veto override** (STRONG_SELL + ≥0.8 confidence) |
| **Execution Optimizer** | `execution_optimizer` | Order intent generation, execution timing, cost optimization |

**Debate flow:** All 6 agents analyze market data in parallel → Aggregator computes weighted consensus → Risk Manager can veto → Consensus reached or next round (max 3 rounds) → FinalDecision (BUY/SELL/HOLD) → OrderIntent → Layer 1 execution.

**Key behaviors:**
- Weighted voting with historical performance weights
- Risk Manager veto: STRONG_SELL at ≥80% confidence overrides any bullish consensus
- Human review required when overall confidence < 70%
- AutoExecute path: debate → execute with risk checks
- Trade outcomes flow to Layer 5 for performance tracking

### Layer 5 — Meta-Learning

| Component | Description |
|---|---|
| **Performance Tracker** | Records every debate and trade; computes winRate, Sharpe ratio, cumulative P&L, max drawdown, profit factor |
| **Model Router** | Multi-armed bandit selecting optimal LLM model per agent role |
| **Strategy GA** | Genetic algorithm evolving agent weights based on historical accuracy |
| **Prompt Optimizer** | A/B tests prompt variants and few-shot examples |
| **Backtest Engine** | Walk-forward backtesting framework with historical market data |

## Tech Stack

- **Runtime:** Node.js 20+
- **Language:** TypeScript 5.3 (strict mode)
- **Graph:** LangGraph.js (debate state machine)
- **LLM:** LangChain (`@langchain/openai`, `@langchain/anthropic`)
- **Vector DB:** LanceDB
- **Web scraping:** Cheerio
- **Scheduling:** node-cron
- **API Server:** Express
- **Testing:** Jest 29 + ts-jest

## Setup

```bash
# Clone
git clone https://github.com/SAHJONY/SAHJONY-AI-TRADING.git
cd SAHJONY-AI-TRADING

# Install dependencies
npm install

# Build
npm run build
```

### Environment Variables

Create a `.env` file with your LLM API keys:

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

## Running

```bash
# Type-check the project
npm run typecheck

# Build TypeScript → JavaScript
npm run build

# Start the API server
npm start

# Start in development mode (build + start)
npm run dev

# Run CLI
npm run cli
```

## Testing

```bash
# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Run a specific test file
npx jest tests/meta/workforce-integration.test.ts --verbose

# Type-check only (no test execution)
npm run typecheck

# Lint
npm run lint
```

### Test Suite Overview

| File | Tests | Coverage |
|---|---|---|
| `tests/meta/workforce-integration.test.ts` | ~90 tests | Full pipeline: debate, veto, consensus, autoExecute, human review, order intent failure, trade closure |
| `tests/meta/workforce-record.test.ts` | ~8 tests | `recordTradeForMetaLearning`, TradeOutcomeRecord creation |
| `tests/orchestration.test.ts` | ~2 tests | Core orchestration engine |

**Integration test coverage:**
- Bullish consensus debate (all 6 agents)
- Veto-triggered debate (8 tests)
- Bearish SELL consensus with normal voting (9 tests)
- AutoExecute trade flow (16 tests)
- Human-review path (7 tests)
- Order intent null path (3 tests)
- Trade closure flow (WIN, LOSS, mixed, BREAKEVEN, Sharpe, partial close)
- Performance tracker metrics computation

## CI/CD

GitHub Actions workflow (`.github/workflows/test.yml`) runs on every push and PR to `master`/`main`:

- **Lint** — `eslint . --max-warnings 0`
- **TypeCheck** — `tsc --noEmit`
- **Tests** — `jest` (all test suites)

## Project Structure

```
agent-workforce/
├── src/
│   ├── index.ts              # Main entry point, all public exports
│   ├── types/                # Shared type definitions
│   ├── agents/               # Base agent classes
│   ├── orchestration/        # Task orchestration engine
│   ├── trading/              # Layer 4 — Trading Workforce
│   │   ├── workforce.ts      # TradingWorkforce class (main orchestrator)
│   │   ├── supervisor.ts     # LangGraph debate graph builder
│   │   ├── agents.ts         # 6 specialized trading agents
│   │   ├── integration.ts    # Layer 1 execution client
│   │   ├── config.ts         # System configuration
│   │   ├── types.ts          # Trading-specific types
│   │   ├── prompts.ts        # Agent system prompts
│   │   └── llm-provider.ts   # LLM provider abstraction
│   ├── knowledge/            # Layer 3 — Knowledge Pipeline
│   │   ├── pipeline.ts       # Full pipeline orchestrator
│   │   ├── knowledge-graph.ts
│   │   ├── vector-store.ts
│   │   ├── rag-orchestrator.ts
│   │   ├── sec-client.ts     # SEC EDGAR API client
│   │   ├── alt-data.ts       # News + social sentiment
│   │   └── types.ts
│   ├── meta/                 # Layer 5 — Meta-Learning
│   │   ├── pipeline.ts       # Meta-learning orchestrator
│   │   ├── performance-tracker.ts
│   │   ├── strategy-ga.ts    # Genetic algorithm
│   │   ├── prompt-optimizer.ts
│   │   ├── model-router.ts   # Multi-armed bandit
│   │   ├── backtest-engine.ts
│   │   └── types.ts
│   ├── api/                  # Express REST API
│   ├── cli/                  # CLI interface
│   └── web/                  # Web dashboard
├── tests/
│   └── meta/
│       ├── workforce-integration.test.ts  # Main integration suite
│       ├── workforce-record.test.ts       # Trade record tests
│       └── strategy-ga.test.ts            # Genetic algorithm tests
├── .github/workflows/test.yml  # CI pipeline
├── jest.config.js
├── tsconfig.json
└── package.json
```

## License

MIT
