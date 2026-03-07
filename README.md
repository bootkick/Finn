# Finn

A self-evolving financial AI agent that rewrites its own strategy code.

Finn pulls signals from news, SEC filings, Reddit, and market data to surface the best stock picks of the day. Every day, it evaluates past performance and uses Claude to literally rewrite its own analysis logic.

Day 1 agent and Day 90 agent won't recognize each other.

## Quick Start

```bash
# Install
pip install -e .

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys (ANTHROPIC_API_KEY required for evolution)

# Run the daily cycle
finn run

# Check current status
finn status

# View strategy evolution history
finn history

# Read the daily journal
finn journal
```

## How It Works

1. **Collect** — Pulls signals from multiple sources (market data, news, Reddit, SEC filings)
2. **Analyze** — Current strategy processes signals and generates ranked picks
3. **Track** — Records picks and monitors real performance over time
4. **Evolve** — After enough data, Claude analyzes what worked/flopped and writes a new strategy
5. **Validate** — New strategy must parse, implement the interface, and pass backtesting
6. **Deploy** — New strategy replaces the old one; old version preserved in history

## Architecture

```
Signals → Collectors → Strategy Engine → Daily Picks
                                              ↓
                              Performance Tracker ← Market Data
                                              ↓
                              Evolution Engine (Claude API)
                                              ↓
                              New Strategy Code → Validated → Deployed
```

**Immutable**: Collectors, evaluation, evolution engine, journal
**Mutable**: Strategy code (the part that evolves)

## Safety Rails

- Strategy code runs in a restricted context (limited imports, timeout)
- New strategies must pass validation + backtesting before deployment
- Automatic rollback if a strategy crashes or underperforms
- Every strategy version is preserved with its performance data
- No real trading — analysis and picks only

## #BuildInPublic

Check `data/journal/` for daily entries documenting every signal, pick, performance update, and strategy evolution.
