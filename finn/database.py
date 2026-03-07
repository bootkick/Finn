"""SQLite database layer for Finn."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from finn.models import Pick, Signal, Conviction


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                ticker TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                headline TEXT DEFAULT '',
                content TEXT DEFAULT '',
                sentiment REAL DEFAULT 0.0,
                magnitude REAL DEFAULT 0.0,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                conviction TEXT NOT NULL,
                direction TEXT DEFAULT 'long',
                reasoning TEXT DEFAULT '',
                entry_price REAL,
                strategy_version INTEGER DEFAULT 1,
                timestamp TEXT NOT NULL,
                signals_used INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pick_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                entry_date TEXT NOT NULL,
                current_price REAL,
                exit_price REAL,
                exit_date TEXT,
                return_pct REAL DEFAULT 0.0,
                days_held INTEGER DEFAULT 0,
                strategy_version INTEGER DEFAULT 1,
                is_closed INTEGER DEFAULT 0,
                FOREIGN KEY (pick_id) REFERENCES picks(id)
            );

            CREATE TABLE IF NOT EXISTS strategy_versions (
                version INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL,
                source_code TEXT NOT NULL,
                description TEXT DEFAULT '',
                parent_version INTEGER,
                performance_summary TEXT DEFAULT '',
                total_picks INTEGER DEFAULT 0,
                win_rate REAL DEFAULT 0.0,
                avg_return REAL DEFAULT 0.0,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);
            CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
            CREATE INDEX IF NOT EXISTS idx_picks_timestamp ON picks(timestamp);
            CREATE INDEX IF NOT EXISTS idx_picks_strategy ON picks(strategy_version);
            CREATE INDEX IF NOT EXISTS idx_performance_pick ON performance(pick_id);
        """)
        self.conn.commit()

    def save_signals(self, signals: list[Signal]) -> None:
        self.conn.executemany(
            """INSERT INTO signals (source, signal_type, ticker, timestamp, headline,
               content, sentiment, magnitude, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    s.source,
                    s.signal_type.value,
                    s.ticker,
                    s.timestamp.isoformat(),
                    s.headline,
                    s.content,
                    s.sentiment,
                    s.magnitude,
                    json.dumps(s.metadata),
                )
                for s in signals
            ],
        )
        self.conn.commit()

    def save_pick(self, pick: Pick) -> int:
        cursor = self.conn.execute(
            """INSERT INTO picks (ticker, conviction, direction, reasoning,
               entry_price, strategy_version, timestamp, signals_used, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pick.ticker,
                pick.conviction.value,
                pick.direction,
                pick.reasoning,
                pick.entry_price,
                pick.strategy_version,
                pick.timestamp.isoformat(),
                pick.signals_used,
                json.dumps(pick.metadata),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def save_performance(self, pick_id: int, pick: Pick) -> None:
        self.conn.execute(
            """INSERT INTO performance (pick_id, ticker, direction, entry_price,
               entry_date, strategy_version)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                pick_id,
                pick.ticker,
                pick.direction,
                pick.entry_price,
                pick.timestamp.isoformat(),
                pick.strategy_version,
            ),
        )
        self.conn.commit()

    def update_performance(self, pick_id: int, current_price: float, return_pct: float, days_held: int) -> None:
        self.conn.execute(
            """UPDATE performance SET current_price = ?, return_pct = ?, days_held = ?
               WHERE pick_id = ?""",
            (current_price, return_pct, days_held, pick_id),
        )
        self.conn.commit()

    def close_performance(self, pick_id: int, exit_price: float, return_pct: float, days_held: int) -> None:
        self.conn.execute(
            """UPDATE performance SET exit_price = ?, exit_date = ?, return_pct = ?,
               days_held = ?, is_closed = 1 WHERE pick_id = ?""",
            (exit_price, datetime.utcnow().isoformat(), return_pct, days_held, pick_id),
        )
        self.conn.commit()

    def get_open_positions(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT p.*, pk.reasoning FROM performance p
               JOIN picks pk ON p.pick_id = pk.id
               WHERE p.is_closed = 0 ORDER BY p.entry_date DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_recent_picks(self, days: int = 30) -> list[dict]:
        rows = self.conn.execute(
            """SELECT * FROM picks
               WHERE timestamp >= datetime('now', ?)
               ORDER BY timestamp DESC""",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_strategy_performance(self, version: int) -> dict:
        row = self.conn.execute(
            """SELECT
                COUNT(*) as total_picks,
                AVG(CASE WHEN p.is_closed = 1 THEN p.return_pct END) as avg_return,
                SUM(CASE WHEN p.return_pct > 0 AND p.is_closed = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN p.is_closed = 1 THEN 1 ELSE 0 END) as closed
               FROM performance p
               WHERE p.strategy_version = ?""",
            (version,),
        ).fetchone()
        result = dict(row)
        closed = result.get("closed") or 0
        result["win_rate"] = (result.get("wins") or 0) / closed if closed > 0 else 0.0
        return result

    def save_strategy_version(self, version: int, source_code: str, description: str, parent_version: int | None = None) -> None:
        # Deactivate previous versions
        self.conn.execute("UPDATE strategy_versions SET is_active = 0")
        self.conn.execute(
            """INSERT OR REPLACE INTO strategy_versions
               (version, created_at, source_code, description, parent_version, is_active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (version, datetime.utcnow().isoformat(), source_code, description, parent_version),
        )
        self.conn.commit()

    def get_active_strategy_version(self) -> int:
        row = self.conn.execute(
            "SELECT version FROM strategy_versions WHERE is_active = 1 ORDER BY version DESC LIMIT 1"
        ).fetchone()
        return row["version"] if row else 1

    def get_strategy_source(self, version: int) -> str | None:
        row = self.conn.execute(
            "SELECT source_code FROM strategy_versions WHERE version = ?", (version,)
        ).fetchone()
        return row["source_code"] if row else None

    def get_all_strategy_versions(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM strategy_versions ORDER BY version DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_total_days_with_picks(self) -> int:
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT date(timestamp)) as days FROM picks"
        ).fetchone()
        return row["days"] if row else 0

    def get_signals_for_date(self, date_str: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM signals WHERE date(timestamp) = ? ORDER BY timestamp",
            (date_str,),
        ).fetchall()
        return [dict(r) for r in rows]

    def save_journal_entry(self, date_str: str, content: str) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO journal_entries (date, content, created_at)
               VALUES (?, ?, ?)""",
            (date_str, content, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def get_journal_entry(self, date_str: str) -> str | None:
        row = self.conn.execute(
            "SELECT content FROM journal_entries WHERE date = ?", (date_str,)
        ).fetchone()
        return row["content"] if row else None

    def close(self):
        self.conn.close()
