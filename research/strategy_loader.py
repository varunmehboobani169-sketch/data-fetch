from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path
from types import ModuleType

import pandas as pd

from research.backtest_engine import BacktestConfig, Strategy


def _load_module(source: str, filename: str = "uploaded_strategy.py") -> ModuleType:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / filename
        path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("uploaded_strategy", path)
        if spec is None or spec.loader is None:
            raise ValueError("Could not create a Python module from the uploaded strategy.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def load_strategy_from_source(
    source: str,
    filename: str = "uploaded_strategy.py",
    class_name: str | None = None,
) -> Strategy:
    module = _load_module(source, filename)

    candidates = []
    for name, obj in vars(module).items():
        if name.startswith("_"):
            continue
        if isinstance(obj, type) and hasattr(obj, "signal") and hasattr(obj, "name"):
            candidates.append((name, obj))

    if class_name:
        matches = [(name, cls) for name, cls in candidates if name == class_name]
        if not matches:
            raise ValueError(f"Strategy class '{class_name}' was not found or does not implement name + signal().")
        candidates = matches

    if not candidates:
        raise ValueError(
            "No compatible strategy class found. Define a class with a 'name' attribute "
            "and signal(day, config) -> list[dict]."
        )
    if len(candidates) > 1:
        raise ValueError(
            "Multiple compatible strategy classes found. Select one explicitly."
        )

    cls = candidates[0][1]
    try:
        instance = cls()
    except TypeError as exc:
        raise ValueError("The selected strategy class must be instantiable without arguments.") from exc
    return instance


def strategy_interface_text() -> str:
    return '''from research.backtest_engine import BacktestConfig

class MyStrategy:
    name = "My Strategy"

    def signal(self, day, config: BacktestConfig):
        # Return zero or more decisions for the current trading day.
        # Each decision must contain: option_type (CE/PE) and strike.
        return []
'''
