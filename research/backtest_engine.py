from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd


@dataclass
class BacktestConfig:
    entry_time: str = "09:30"
    exit_time: str = "15:15"
    stop_loss_pct: float = 0.25
    target_pct: float = 0.50
    lot_size: int = 65
    lots: int = 1
    brokerage_per_trade: float = 0.0
    slippage_pct: float = 0.0


@dataclass
class Trade:
    date: object
    option_type: str
    strike: float
    entry_time: object
    entry_price: float
    exit_time: object
    exit_price: float
    exit_reason: str
    pnl_per_unit: float
    pnl: float


class Strategy(Protocol):
    name: str

    def signal(self, day: pd.DataFrame, config: BacktestConfig) -> list[dict]: ...


def _price_at_or_after(day: pd.DataFrame, target: pd.Timestamp) -> pd.Series | None:
    rows = day[day["timestamp"] >= target]
    if rows.empty:
        return None
    return rows.iloc[0]


def run_backtest(data: pd.DataFrame, strategy: Strategy, config: BacktestConfig) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame()
    df = data.copy()
    df["trade_date"] = df["timestamp"].dt.date
    trades: list[Trade] = []

    for trade_date, day in df.groupby("trade_date", sort=True):
        decisions = strategy.signal(day, config)
        for decision in decisions:
            option_type = str(decision["option_type"]).upper()
            strike = float(decision["strike"])
            entry_target = pd.Timestamp(f"{trade_date} {config.entry_time}")
            exit_target = pd.Timestamp(f"{trade_date} {config.exit_time}")
            contract = day[(day["option_type"] == option_type) & (day["strike"] == strike)]
            if contract.empty:
                continue
            entry = _price_at_or_after(contract, entry_target)
            if entry is None:
                continue
            entry_price = float(entry["close"])
            if entry_price <= 0:
                continue
            stop_price = entry_price * (1.0 - config.stop_loss_pct)
            target_price = entry_price * (1.0 + config.target_pct)
            after_entry = contract[contract["timestamp"] >= entry["timestamp"]]
            exit_row = _price_at_or_after(after_entry, exit_target)
            exit_reason = "Square-off"
            if not after_entry.empty:
                hit_stop = after_entry["close"] <= stop_price
                hit_target = after_entry["close"] >= target_price
                candidates = after_entry[hit_stop | hit_target]
                if not candidates.empty:
                    exit_row = candidates.iloc[0]
                    exit_reason = "Stop-loss" if float(exit_row["close"]) <= stop_price else "Target"
            if exit_row is None:
                exit_row = after_entry.iloc[-1] if not after_entry.empty else None
            if exit_row is None:
                continue
            exit_price = float(exit_row["close"])
            # Long option: positive price change is profit.
            pnl_per_unit = exit_price - entry_price
            qty = int(config.lot_size * config.lots)
            gross = pnl_per_unit * qty
            costs = config.brokerage_per_trade + (entry_price + exit_price) * qty * config.slippage_pct
            pnl = gross - costs
            trades.append(Trade(trade_date, option_type, strike, entry["timestamp"], entry_price, exit_row["timestamp"], exit_price, exit_reason, pnl_per_unit, pnl))

    if not trades:
        return pd.DataFrame()
    out = pd.DataFrame([t.__dict__ for t in trades])
    out["cum_pnl"] = out["pnl"].cumsum()
    out["win"] = out["pnl"] > 0
    return out
