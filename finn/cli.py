"""CLI interface for Finn."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from finn.config import get_settings

app = typer.Typer(
    name="finn",
    help="Finn: Self-evolving financial AI agent",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run():
    """Execute the daily cycle: collect signals, generate picks, evaluate, evolve."""
    from finn.main import daily_run

    settings = get_settings()
    result = daily_run(settings)

    if result["picks"]:
        console.print(f"\n[bold]Summary: {len(result['picks'])} picks from {result['signals_collected']} signals[/bold]")
    else:
        console.print("\n[yellow]No picks generated. Check signal collection.[/yellow]")


@app.command()
def status():
    """Show current strategy and recent performance."""
    settings = get_settings()

    from finn.database import Database
    from finn.evaluation.scorer import StrategyScorer
    from finn.evolution.rollback import RollbackManager
    from finn.strategy.runner import StrategyRunner
    from pathlib import Path

    db = Database(settings.db_path)
    try:
        version = db.get_active_strategy_version()
        perf = db.get_strategy_performance(version)
        positions = db.get_open_positions()
        days = db.get_total_days_with_picks()

        console.rule("[bold blue]Finn Status")

        console.print(f"Active strategy: v{version}")
        console.print(f"Days running: {days}")
        console.print(f"Total picks: {perf.get('total_picks', 0)}")
        console.print(f"Win rate: {perf.get('win_rate', 0):.1%}")
        console.print(f"Avg return: {perf.get('avg_return') or 0:.2f}%")

        if positions:
            console.print(f"\nOpen positions ({len(positions)}):")
            table = Table()
            table.add_column("Ticker")
            table.add_column("Direction")
            table.add_column("Return %")
            table.add_column("Days Held")

            for pos in positions:
                table.add_row(
                    pos["ticker"],
                    pos["direction"],
                    f"{pos.get('return_pct', 0):+.1f}%",
                    str(pos.get("days_held", 0)),
                )
            console.print(table)

        # Show strategy description
        runner = StrategyRunner(settings.strategies_path)
        active_path = Path(__file__).parent / "strategy" / "active" / "strategy_v1.py"
        rollback = RollbackManager(db, settings.strategies_path, active_path)
        try:
            code = rollback.get_current_code()
            strategy = runner.load_strategy(code)
            console.print(f"\nStrategy description:\n{strategy.describe()}")
        except Exception:
            pass

    finally:
        db.close()


@app.command()
def history():
    """Show strategy evolution timeline."""
    settings = get_settings()

    from finn.database import Database

    db = Database(settings.db_path)
    try:
        versions = db.get_all_strategy_versions()

        if not versions:
            console.print("[yellow]No strategy versions recorded yet. Run 'finn run' first.[/yellow]")
            return

        console.rule("[bold blue]Strategy Evolution History")

        table = Table()
        table.add_column("Version")
        table.add_column("Created")
        table.add_column("Parent")
        table.add_column("Active")
        table.add_column("Description")

        for v in versions:
            table.add_row(
                f"v{v['version']}",
                v["created_at"][:16],
                f"v{v['parent_version']}" if v.get("parent_version") else "-",
                "Yes" if v.get("is_active") else "",
                (v.get("description") or "")[:80],
            )
        console.print(table)

    finally:
        db.close()


@app.command()
def journal(days: int = typer.Option(7, help="Number of recent entries to show")):
    """Show recent journal entries."""
    settings = get_settings()
    journal_path = settings.journal_path

    files = sorted(journal_path.glob("*.md"), reverse=True)[:days]

    if not files:
        console.print("[yellow]No journal entries yet. Run 'finn run' first.[/yellow]")
        return

    for f in files:
        console.print(f.read_text())
        console.print()


@app.command()
def schedule(
    interval_hours: int = typer.Option(24, help="Hours between runs"),
    run_at: str = typer.Option("09:30", help="Time to run daily (HH:MM)"),
):
    """Start the scheduler for automated daily runs."""
    import schedule as sched
    import time
    from finn.main import daily_run

    settings = get_settings()

    console.print(f"[bold]Scheduling Finn to run daily at {run_at}[/bold]")
    console.print("Press Ctrl+C to stop.\n")

    def job():
        try:
            daily_run(settings)
        except Exception as e:
            console.print(f"[red]Run failed: {e}[/red]")

    sched.every().day.at(run_at).do(job)

    # Also run immediately on first start
    console.print("[dim]Running initial cycle now...[/dim]\n")
    job()

    while True:
        sched.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    app()
