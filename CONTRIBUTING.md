# Contributing to Agent Workforce

Thanks for contributing! This guide covers how to set up your local environment and submit changes.

## Prerequisites

- **Node.js 20** (see [Node Version Setup](#node-version-setup) below)
- **npm 10+** (bundled with Node.js 20)

## Node Version Setup

The project is locked to Node.js 20. Pick your version manager:

### nvm

```bash
nvm use        # reads .nvmrc
nvm install    # if 20 isn't installed yet
```

### fnm

```bash
fnm use        # reads .node-version
fnm install 20 # if 20 isn't installed yet
```

### nodenv

```bash
nodenv install 20.0.0  # if 20 isn't installed yet
nodenv local   # reads .node-version
```

### asdf

```bash
asdf plugin add nodejs  # first-time only
asdf install            # reads .tool-versions
```

### Manual Check

```bash
node --version  # should print v20.x.x
```

## Local Development

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

Copy or create a `.env` file:

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

## Quality Gates

Run these before submitting a PR:

```bash
npm run lint       # ESLint (0 warnings, 0 errors)
npm run typecheck  # tsc --noEmit
npm test           # Jest (all 186 tests)
npm run coverage   # Jest with coverage report
```

Run all three together:

```bash
npm run lint && npm run typecheck && npm test
```

## CI/CD

GitHub Actions runs on every push and PR to `master`/`main`:

1. **Lint** — `eslint . --max-warnings 0`
2. **TypeCheck** — `tsc --noEmit`
3. **Tests + Coverage** — `jest` with lcov upload to Codecov

## Project Structure

```
agent-workforce/
├── src/
│   ├── agents/          # Base agent classes
│   ├── trading/         # Layer 4 — Trading Workforce
│   ├── knowledge/       # Layer 3 — Knowledge Pipeline
│   ├── meta/            # Layer 5 — Meta-Learning
│   ├── orchestration/   # Task orchestration engine
│   ├── api/             # Express REST API
│   ├── cli/             # CLI interface
│   └── web/             # Web dashboard
├── tests/
│   └── meta/            # Integration & unit tests
└── .github/workflows/   # CI pipeline
```

See the [README](./README.md) for a full architecture overview.

## Pull Request Checklist

- [ ] Node.js 20 is active (`node --version`)
- [ ] `npm run lint` passes with no errors
- [ ] `npm run typecheck` passes
- [ ] `npm test` passes (186 tests)
- [ ] New code follows existing conventions and includes tests
- [ ] No new ESLint warnings introduced

## License

MIT — see `"license"` in [package.json](./package.json).
