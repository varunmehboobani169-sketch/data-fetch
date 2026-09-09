from __future__ import annotations

import pandas as pd

from research.backtest_engine import BacktestConfig


class BreakoutStrategy:
    name = "ATM Breakout"

    def signal(self, day: pd.DataFrame, config: BacktestConfig) -> list[dict]:
        # Simple first-pass breakout: current spot must break the prior
        # 30-minute high/low at the entry point. No future data is used.
        entry = day[day["timestamp"].dt.strftime("%H:%M") >= config.entry_time]
        if entry.empty:
            return []
        first = entry.iloc[0]
        prior = day[day["timestamp"] < first["timestamp"]]
        if prior.empty or "spot" not in prior:
            return []
        lookback = prior.tail(30)
        high = float(lookback["spot"].max())
        low = float(lookback["spot"].min())
        atm = round(float(first["spot"]) / 50.0) * 50.0
        if float(first["spot"]) > high:
            return [{"option_type": "CE", "strike": atm}]
        if float(first["spot"]) < low:
            return [{"option_type": "PE", "strike": atm}]
        return []
