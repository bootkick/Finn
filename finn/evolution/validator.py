"""Strategy code validator — ensures generated code is safe and correct."""

from __future__ import annotations

import ast
import logging

logger = logging.getLogger(__name__)

REQUIRED_IMPORTS = {"Strategy", "Signal", "Pick", "Conviction"}
BANNED_MODULES = {
    "os", "sys", "subprocess", "shutil", "pathlib", "socket",
    "http", "urllib", "requests", "pickle", "shelve", "sqlite3",
    "io", "tempfile", "glob", "importlib", "ctypes", "multiprocessing",
    "threading", "signal", "atexit", "code", "compile", "exec", "eval",
}


class StrategyValidator:
    """Validates strategy code before deployment."""

    def validate(self, source_code: str) -> dict:
        """Run all validation checks on strategy source code.

        Returns:
            {"valid": True/False, "error": str | None, "warnings": list[str]}
        """
        warnings = []

        # 1. Syntax check
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return {"valid": False, "error": f"Syntax error: {e}", "warnings": []}

        # 2. Check for Strategy subclass
        has_strategy_class = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "Strategy":
                        has_strategy_class = True
                    elif isinstance(base, ast.Attribute) and base.attr == "Strategy":
                        has_strategy_class = True

        if not has_strategy_class:
            return {"valid": False, "error": "No Strategy subclass found", "warnings": warnings}

        # 3. Check required methods
        has_analyze = False
        has_describe = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name == "analyze":
                    has_analyze = True
                elif node.name == "describe":
                    has_describe = True

        if not has_analyze:
            return {"valid": False, "error": "Missing 'analyze' method", "warnings": warnings}
        if not has_describe:
            return {"valid": False, "error": "Missing 'describe' method", "warnings": warnings}

        # 4. Check for banned imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module in BANNED_MODULES:
                        return {"valid": False, "error": f"Banned import: {alias.name}", "warnings": warnings}
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split(".")[0]
                    if module in BANNED_MODULES:
                        return {"valid": False, "error": f"Banned import: {node.module}", "warnings": warnings}

        # 5. Check for dangerous builtins
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in {"exec", "eval", "compile", "__import__", "open"}:
                        return {"valid": False, "error": f"Banned function call: {node.func.id}", "warnings": warnings}

        # 6. Code length sanity check
        lines = source_code.strip().split("\n")
        if len(lines) > 500:
            warnings.append(f"Strategy is {len(lines)} lines — consider simplifying")
        if len(lines) < 10:
            warnings.append("Strategy seems very short — may be incomplete")

        return {"valid": True, "error": None, "warnings": warnings}
