"""Rollback manager — version control for strategies."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from finn.database import Database

logger = logging.getLogger(__name__)


class RollbackManager:
    """Manages strategy versions and rollbacks."""

    def __init__(self, db: Database, strategies_path: Path, active_strategy_path: Path):
        self.db = db
        self.strategies_path = strategies_path
        self.active_strategy_path = active_strategy_path

    def save_version(
        self,
        version: int,
        source_code: str,
        description: str,
        parent_version: int | None = None,
    ) -> None:
        """Save a new strategy version and make it active."""
        # Save to version history
        version_file = self.strategies_path / f"strategy_v{version}.py"
        version_file.write_text(source_code)

        # Save to database
        self.db.save_strategy_version(version, source_code, description, parent_version)

        # Update active strategy file
        self.active_strategy_path.write_text(source_code)

        logger.info(f"Strategy v{version} saved and activated")

    def rollback(self, to_version: int) -> bool:
        """Roll back to a previous strategy version."""
        source_code = self.db.get_strategy_source(to_version)
        if source_code is None:
            logger.error(f"Strategy v{to_version} not found in database")
            return False

        # Update active strategy
        self.active_strategy_path.write_text(source_code)

        # Mark as active in DB
        self.db.save_strategy_version(
            to_version, source_code, f"Rolled back to v{to_version}", None
        )

        logger.info(f"Rolled back to strategy v{to_version}")
        return True

    def get_current_code(self) -> str:
        """Get the current active strategy source code."""
        if self.active_strategy_path.exists():
            return self.active_strategy_path.read_text()

        # Fallback: check database
        version = self.db.get_active_strategy_version()
        code = self.db.get_strategy_source(version)
        if code:
            return code

        # Last resort: return v1
        v1_path = Path(__file__).parent.parent / "strategy" / "active" / "strategy_v1.py"
        if v1_path.exists():
            return v1_path.read_text()

        raise FileNotFoundError("No strategy code found anywhere")

    def get_version_history(self) -> list[dict]:
        """Get all strategy versions with metadata."""
        return self.db.get_all_strategy_versions()

    def initialize(self) -> None:
        """Initialize with v1 strategy if no versions exist."""
        versions = self.db.get_all_strategy_versions()
        if not versions:
            v1_path = Path(__file__).parent.parent / "strategy" / "active" / "strategy_v1.py"
            if v1_path.exists():
                code = v1_path.read_text()
                self.save_version(1, code, "Initial signal aggregation strategy")
                logger.info("Initialized strategy version history with v1")
