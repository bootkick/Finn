"""Daily run orchestrator — the main pipeline."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from finn.config import Settings
from finn.database import Database
from finn.collectors import MarketDataCollector, NewsCollector, RedditCollector, SECFilingCollector
from finn.strategy.runner import StrategyRunner
from finn.evaluation.tracker import PerformanceTracker
from finn.evaluation.scorer import StrategyScorer
from finn.evaluation.backtester import Backtester
from finn.evolution.engine import EvolutionEngine
from finn.evolution.validator import StrategyValidator
from finn.evolution.rollback import RollbackManager
from finn.journal.writer import JournalWriter
from finn.models.signals import Signal

console = Console()
logger = logging.getLogger("finn")


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def daily_run(settings: Settings) -> dict:
    """Execute the full daily cycle.

    1. Collect signals
    2. Load current strategy
    3. Generate picks
    4. Record picks + entry prices
    5. Update open positions
    6. Run evolution (if enough data)
    7. Write journal
    """
    setup_logging(settings.log_level)
    today = datetime.utcnow().date().isoformat()

    console.rule(f"[bold blue]Finn Daily Run — {today}")

    # Initialize components
    db = Database(settings.db_path)
    runner = StrategyRunner(settings.strategies_path)
    tracker = PerformanceTracker(db)
    scorer = StrategyScorer(db)
    backtester = Backtester(db, runner)
    validator = StrategyValidator()
    active_strategy_path = Path(__file__).parent / "strategy" / "active" / "strategy_v1.py"
    rollback = RollbackManager(db, settings.strategies_path, active_strategy_path)
    journal = JournalWriter(db, settings.journal_path)

    # Initialize strategy version tracking
    rollback.initialize()

    result = {
        "date": today,
        "signals_collected": 0,
        "picks": [],
        "performance_update": [],
        "evolution_result": None,
    }

    try:
        # === STEP 1: Collect Signals ===
        console.print("\n[bold]Step 1: Collecting signals...[/bold]")
        signals = _collect_signals(settings)
        result["signals_collected"] = len(signals)
        console.print(f"  Collected {len(signals)} signals from {_count_sources(signals)} sources")

        # Save signals to DB
        if signals:
            db.save_signals(signals)

        # === STEP 2: Load Strategy ===
        console.print("\n[bold]Step 2: Loading strategy...[/bold]")
        current_code = rollback.get_current_code()
        strategy = runner.load_strategy(current_code)
        current_version = db.get_active_strategy_version()
        console.print(f"  Strategy v{current_version}: {strategy.describe()[:100]}...")

        # === STEP 3: Generate Picks ===
        console.print("\n[bold]Step 3: Generating picks...[/bold]")
        picks = runner.run(strategy, signals)

        # Set entry prices from market data
        picks = _set_entry_prices(picks, settings.watchlist_tickers)

        # Set strategy version
        for pick in picks:
            pick.strategy_version = current_version

        result["picks"] = [
            {"ticker": p.ticker, "direction": p.direction, "conviction": p.conviction.value, "reasoning": p.reasoning}
            for p in picks
        ]

        if picks:
            console.print(f"  Generated {len(picks)} picks:")
            for pick in picks:
                console.print(f"    {pick.summary()}")
        else:
            console.print("  [yellow]No picks generated today[/yellow]")

        # === STEP 4: Record Picks ===
        console.print("\n[bold]Step 4: Recording picks...[/bold]")
        for pick in picks:
            tracker.record_pick(pick)
        console.print(f"  Recorded {len(picks)} picks")

        # === STEP 5: Update Open Positions ===
        console.print("\n[bold]Step 5: Updating open positions...[/bold]")
        performance_update = tracker.update_open_positions()
        result["performance_update"] = performance_update

        if performance_update:
            for pos in performance_update:
                console.print(
                    f"  {pos['ticker']} ({pos['direction']}): "
                    f"{pos.get('return_pct', 0):+.1f}% over {pos.get('days_held', 0)} days"
                )
        else:
            console.print("  No open positions to update")

        # === STEP 6: Evolution ===
        console.print("\n[bold]Step 6: Evolution check...[/bold]")
        days_running = db.get_total_days_with_picks()

        if days_running >= settings.evolution_min_days and settings.has_anthropic_key:
            console.print(f"  {days_running} days of data — running evolution cycle")
            evolution_engine = EvolutionEngine(
                api_key=settings.anthropic_api_key,
                db=db,
                scorer=scorer,
                validator=validator,
                backtester=backtester,
                rollback=rollback,
                runner=runner,
            )
            evolution_result = evolution_engine.evolve(strategy, current_code)
            result["evolution_result"] = evolution_result

            if evolution_result["evolved"]:
                console.print(
                    f"  [bold green]Strategy evolved to v{evolution_result['new_version']}![/bold green]"
                )
            else:
                console.print(f"  [yellow]Evolution skipped: {evolution_result['reason']}[/yellow]")
        else:
            reasons = []
            if days_running < settings.evolution_min_days:
                reasons.append(f"need {settings.evolution_min_days - days_running} more days of data")
            if not settings.has_anthropic_key:
                reasons.append("no Anthropic API key configured")
            console.print(f"  Skipping evolution: {', '.join(reasons)}")

        # === STEP 7: Journal ===
        console.print("\n[bold]Step 7: Writing journal...[/bold]")
        journal_content = journal.write_daily_entry(
            date=today,
            signals_collected=len(signals),
            picks_made=result["picks"],
            performance_update=performance_update,
            evolution_result=result["evolution_result"],
            strategy_description=strategy.describe(),
        )
        console.print(f"  Journal written to data/journal/{today}.md")

        console.rule("[bold green]Daily run complete")

    except Exception as e:
        logger.error(f"Daily run failed: {e}", exc_info=True)
        raise
    finally:
        db.close()

    return result


def _collect_signals(settings: Settings) -> list[Signal]:
    """Collect signals from all available sources."""
    collectors = [
        MarketDataCollector(),
        NewsCollector(),
        RedditCollector(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        ),
        SECFilingCollector(),
    ]

    all_signals = []
    for collector in collectors:
        if not collector.is_available:
            logger.info(f"Skipping {collector.name} (not available)")
            continue
        try:
            signals = collector.collect(settings.watchlist_tickers)
            logger.info(f"  {collector.name}: {len(signals)} signals")
            all_signals.extend(signals)
        except Exception as e:
            logger.warning(f"  {collector.name} failed: {e}")

    return all_signals


def _count_sources(signals: list[Signal]) -> int:
    return len({s.source for s in signals})


def _set_entry_prices(picks: list, tickers: list[str]) -> list:
    """Set entry prices on picks using current market data."""
    try:
        import yfinance as yf
    except ImportError:
        return picks

    for pick in picks:
        try:
            ticker = yf.Ticker(pick.ticker)
            hist = ticker.history(period="1d")
            if not hist.empty:
                pick.entry_price = float(hist["Close"].iloc[-1])
        except Exception:
            pass
    return picks
