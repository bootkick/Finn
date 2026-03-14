"""Daily run orchestrator — the main pipeline."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from finn.config import Settings
from finn.database import Database
from finn.collectors import MarketDataCollector, NewsCollector, RedditCollector, SECFilingCollector, CryptoCollector
from finn.strategy.runner import StrategyRunner
from finn.evaluation.tracker import PerformanceTracker
from finn.evaluation.scorer import StrategyScorer
from finn.evaluation.backtester import Backtester
from finn.evolution.engine import EvolutionEngine
from finn.evolution.validator import StrategyValidator
from finn.evolution.rollback import RollbackManager
from finn.journal.writer import JournalWriter
from finn.human_loop import HumanInTheLoop
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

    1. Collect signals (stocks + crypto)
    2. Load current strategy
    3. Generate picks
    4. Record picks + entry prices
    5. Execute trades (if enabled)
    6. Update open positions
    7. Run evolution with memory (if enough data)
    8. Generate memory reflection
    9. Human-in-the-loop check
    10. Generate LinkedIn post
    11. Write journal
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
    human_loop = HumanInTheLoop(db, settings.data_path)

    # Initialize strategy version tracking
    rollback.initialize()

    result = {
        "date": today,
        "signals_collected": 0,
        "picks": [],
        "performance_update": [],
        "evolution_result": None,
        "trades_executed": [],
        "linkedin_post": None,
        "human_questions": [],
        "source_suggestions": [],
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
        picks = _set_entry_prices(picks, settings.all_tickers)

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

        # === STEP 5: Auto-Trading ===
        if settings.enable_trading and settings.has_alpaca_keys:
            console.print("\n[bold]Step 5: Executing trades...[/bold]")
            from finn.trading import AutoTrader
            trader = AutoTrader(
                api_key=settings.alpaca_api_key,
                api_secret=settings.alpaca_api_secret,
                db=db,
                paper=settings.alpaca_paper,
            )
            trades = trader.execute_picks(picks)
            result["trades_executed"] = trades

            for trade in trades:
                db.save_trade(trade)
                mode = trade.get("mode", "PAPER")
                console.print(
                    f"  [{mode}] {trade.get('side', '?').upper()} "
                    f"${trade.get('notional', 0):.2f} of {trade['ticker']} — {trade.get('status', '?')}"
                )

            if not trades:
                console.print("  No trades executed (risk limits or no qualifying picks)")
        else:
            console.print("\n[bold]Step 5: Trading[/bold] — [dim]disabled[/dim]")

        # === STEP 6: Update Open Positions ===
        console.print("\n[bold]Step 6: Updating open positions...[/bold]")
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

        # === STEP 7: Evolution ===
        console.print("\n[bold]Step 7: Evolution check...[/bold]")
        days_running = db.get_total_days_with_picks()

        evolution_result = None
        if days_running >= settings.evolution_min_days and settings.has_anthropic_key:
            console.print(f"  {days_running} days of data — running evolution cycle")

            # Gather memory context
            memory_context = journal.get_memory_context()

            # Gather human guidance
            human_guidance = human_loop.format_answers_for_evolution()

            evolution_engine = EvolutionEngine(
                api_key=settings.anthropic_api_key,
                db=db,
                scorer=scorer,
                validator=validator,
                backtester=backtester,
                rollback=rollback,
                runner=runner,
            )
            evolution_result = evolution_engine.evolve(
                strategy, current_code,
                memory_context=memory_context,
                human_guidance=human_guidance,
            )
            result["evolution_result"] = evolution_result
            result["source_suggestions"] = evolution_result.get("source_suggestions", [])

            if evolution_result["evolved"]:
                console.print(
                    f"  [bold green]Strategy evolved to v{evolution_result['new_version']}![/bold green]"
                )
            else:
                console.print(f"  [yellow]Evolution skipped: {evolution_result['reason']}[/yellow]")

            if result["source_suggestions"]:
                console.print(f"  Source discovery: {len(result['source_suggestions'])} new ideas")
        else:
            reasons = []
            if days_running < settings.evolution_min_days:
                reasons.append(f"need {settings.evolution_min_days - days_running} more days of data")
            if not settings.has_anthropic_key:
                reasons.append("no Anthropic API key configured")
            console.print(f"  Skipping evolution: {', '.join(reasons)}")

        # === STEP 8: Memory Reflection ===
        console.print("\n[bold]Step 8: Memory reflection...[/bold]")
        if settings.has_anthropic_key and days_running >= 2:
            from finn.personality import Personality
            personality = Personality(settings.anthropic_api_key)
            recent_entries = journal.get_recent_entries(count=5)
            reflection = personality.reflect_on_memory(recent_entries)
            journal.save_memory(today, "reflection", reflection)
            console.print("  Memory updated with today's reflection")
        else:
            console.print("  [dim]Skipping reflection (too early or no API key)[/dim]")

        # === STEP 9: Human-in-the-Loop ===
        console.print("\n[bold]Step 9: Human-in-the-loop...[/bold]")
        pending_questions = human_loop.get_pending_questions()
        result["human_questions"] = pending_questions

        if pending_questions:
            console.print(f"  {len(pending_questions)} pending question(s) for you:")
            for q in pending_questions:
                console.print(f"    [{q['priority']}] {q['question']}")
            console.print("  Answer with: finn answer <question_id> <your answer>")

        if human_loop.should_ask_question(days_running):
            context = {
                "performance": scorer.score_strategy(current_version) if days_running > 0 else {},
                "evolution_result": evolution_result,
                "signals_collected": len(signals),
                "day_number": days_running,
                "strategy_version": current_version,
            }
            new_question = human_loop.generate_question(context)
            if new_question:
                q_id = human_loop.ask(
                    new_question["question"],
                    new_question["context"],
                    new_question["priority"],
                )
                console.print(f"  New question ({q_id}): {new_question['question']}")
        else:
            if not pending_questions:
                console.print("  [dim]No questions today[/dim]")

        # === STEP 10: LinkedIn Post ===
        console.print("\n[bold]Step 10: LinkedIn post...[/bold]")
        if settings.has_anthropic_key:
            from finn.personality import Personality
            personality = Personality(settings.anthropic_api_key)
            memory_context = journal.get_memory_context()

            # Write journal first to use as context
            journal_content = journal.write_daily_entry(
                date=today,
                signals_collected=len(signals),
                picks_made=result["picks"],
                performance_update=performance_update,
                evolution_result=result["evolution_result"],
                strategy_description=strategy.describe(),
                trades_executed=result["trades_executed"] or None,
                human_questions=pending_questions or None,
                source_suggestions=result["source_suggestions"] or None,
            )

            linkedin_post = personality.generate_linkedin_post(
                journal_entry=journal_content,
                memory_context=memory_context,
                day_number=days_running,
                strategy_version=current_version,
            )
            result["linkedin_post"] = linkedin_post
            db.save_linkedin_post(today, linkedin_post)

            console.print("  LinkedIn post generated!")
            console.print(f"\n[dim]{'─' * 60}[/dim]")
            console.print(f"[italic]{linkedin_post}[/italic]")
            console.print(f"[dim]{'─' * 60}[/dim]")
        else:
            # Write journal without LinkedIn post
            journal.write_daily_entry(
                date=today,
                signals_collected=len(signals),
                picks_made=result["picks"],
                performance_update=performance_update,
                evolution_result=result["evolution_result"],
                strategy_description=strategy.describe(),
                trades_executed=result["trades_executed"] or None,
                human_questions=pending_questions or None,
                source_suggestions=result["source_suggestions"] or None,
            )
            console.print("  [dim]Skipping LinkedIn post (no API key)[/dim]")

        console.print(f"\n  Journal written to data/journal/{today}.md")

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

    # Add crypto collector if enabled
    if settings.enable_crypto:
        collectors.append(CryptoCollector())

    all_signals = []
    for collector in collectors:
        if not collector.is_available:
            logger.info(f"Skipping {collector.name} (not available)")
            continue
        try:
            # Use combined tickers for stock collectors, crypto tickers for crypto
            if isinstance(collector, CryptoCollector):
                tickers = settings.crypto_tickers
            else:
                tickers = settings.watchlist_tickers

            signals = collector.collect(tickers)
            logger.info(f"  {collector.name}: {len(signals)} signals")
            all_signals.extend(signals)
        except Exception as e:
            logger.warning(f"  {collector.name} failed: {e}")

    return all_signals


def _count_sources(signals: list[Signal]) -> int:
    return len({s.source for s in signals})


def _set_entry_prices(picks: list, tickers: list[str]) -> list:
    """Set entry prices on picks using Yahoo Finance HTTP API."""
    from finn.collectors.market_data import _yahoo_request, YAHOO_CHART_URL
    from finn.collectors.crypto import CRYPTO_COINS

    for pick in picks:
        try:
            symbol = CRYPTO_COINS.get(pick.ticker, pick.ticker)
            url = YAHOO_CHART_URL.format(symbol=symbol)
            data = _yahoo_request(url)
            result = data.get("chart", {}).get("result", [])
            if result:
                closes = result[0].get("indicators", {}).get("quote", [{}])[0].get("close", [])
                valid = [c for c in closes if c is not None]
                if valid:
                    pick.entry_price = float(valid[-1])
        except Exception:
            pass
    return picks
