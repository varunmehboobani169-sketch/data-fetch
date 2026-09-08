from __future__ import annotations

from dataclasses import dataclass
from math import exp, log, pi, sqrt
from statistics import NormalDist
from typing import Iterable

import pandas as pd

_N = NormalDist()


@dataclass
class Trade:
    date: str
    strategy: str
    entry_time: str
    exit_time: str
    expiry: str
    spot: float
    ce_strike: float
    pe_strike: float
    entry_credit: float
    exit_debit: float
    pnl_points: float
    pnl_rupees: float


def _norm_pdf(x: float) -> float:
    return exp(-0.5 * x * x) / sqrt(2.0 * pi)


def greeks(spot: float, strike: float, iv_pct: float, days_to_expiry: float, option_type: str, rate: float = 0.06):
    if spot <= 0 or strike <= 0 or iv_pct <= 0 or days_to_expiry <= 0:
        return None
    sigma = iv_pct / 100.0
    t = days_to_expiry / 365.0
    d1 = (log(spot / strike) + (rate + 0.5 * sigma * sigma) * t) / (sigma * sqrt(t))
    d2 = d1 - sigma * sqrt(t)
    pdf = _norm_pdf(d1)
    delta = _N.cdf(d1) if option_type == "CE" else _N.cdf(d1) - 1.0
    theta_year = -(spot * pdf * sigma) / (2 * sqrt(t))
    if option_type == "CE":
        theta_year -= rate * strike * exp(-rate * t) * _N.cdf(d2)
    else:
        theta_year += rate * strike * exp(-rate * t) * _N.cdf(-d2)
    return {
        "delta": float(delta),
        "theta_day": float(theta_year / 365.0),
        "theta_hour": float(theta_year / 365.0 / 6.25),
    }


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], errors="coerce")
    x["close"] = pd.to_numeric(x["close"], errors="coerce")
    x["strike"] = pd.to_numeric(x["strike"], errors="coerce")
    x["spot"] = pd.to_numeric(x["spot"], errors="coerce")
    x["iv"] = pd.to_numeric(x["iv"], errors="coerce").fillna(0)
    x["expiry"] = pd.to_datetime(x["expiry"], errors="coerce").dt.date
    x["option_type"] = x["option_type"].astype(str).str.upper()
    return x.dropna(subset=["timestamp", "close", "strike", "spot", "expiry"])


def _nearest_ts(day: pd.DataFrame, hhmm: str):
    session = day["timestamp"].dt.date.iloc[0]
    target = pd.Timestamp(f"{session} {hhmm}")
    if getattr(day["timestamp"].dt, "tz", None) is not None:
        target = target.tz_localize(day["timestamp"].dt.tz)
    after = day.loc[day["timestamp"] >= target, "timestamp"]
    if not after.empty:
        return after.iloc[0]
    before = day.loc[day["timestamp"] <= target, "timestamp"]
    return before.iloc[-1] if not before.empty else None


def _snapshot(day: pd.DataFrame, ts: pd.Timestamp) -> pd.DataFrame:
    return day[day["timestamp"] == ts].drop_duplicates(["option_type", "strike"], keep="last")


def _select_theta(
    snapshot: pd.DataFrame,
    side: str,
    min_abs_delta: float = 0.10,
    max_abs_delta: float = 0.50,
):
    """Select the contract with the strongest theta edge.

    Theta is the primary ranking variable. Delta is only a configurable
    safety boundary to keep the engine away from extreme gamma exposure.
    The score is expected theta income per hour divided by current premium.
    """
    candidates = []
    for idx, row in snapshot[snapshot["option_type"] == side].iterrows():
        dte = max((row["expiry"] - row["timestamp"].date()).days + 0.01, 0.01)
        g = greeks(float(row["spot"]), float(row["strike"]), float(row["iv"]), dte, side)
        premium = float(row["close"])
        if not g or premium <= 0:
            continue
        ad = abs(g["delta"])
        if min_abs_delta <= ad <= max_abs_delta:
            theta_income = max(0.0, -g["theta_hour"])
            theta_efficiency = theta_income / max(premium, 0.05)
            candidates.append((idx, theta_efficiency, theta_income, g))

    if not candidates:
        return None

    # Theta efficiency is the objective; raw theta is the tie-breaker.
    idx, _, _, g = max(candidates, key=lambda z: (z[1], z[2]))
    out = snapshot.loc[idx].copy()
    out["delta_calc"] = g["delta"]
    out["theta_hour_calc"] = g["theta_hour"]
    out["theta_efficiency"] = max(0.0, -g["theta_hour"]) / max(float(out["close"]), 0.05)
    return out


def _row(snapshot: pd.DataFrame, side: str, strike: float):
    q = snapshot[(snapshot["option_type"] == side) & (snapshot["strike"] == strike)]
    return q.iloc[0] if not q.empty else None


def _price(day: pd.DataFrame, ts: pd.Timestamp, side: str, strike: float):
    q = day[(day["timestamp"] >= ts) & (day["option_type"] == side) & (day["strike"] == strike)]
    return float(q.iloc[0]["close"]) if not q.empty else None


def backtest_theta(
    df: pd.DataFrame,
    strategy: str = "Dynamic Theta Strangle",
    entry_time: str = "09:30",
    exit_time: str = "15:15",
    min_abs_delta: float = 0.10,
    max_abs_delta: float = 0.50,
    wing_distance: int = 4,
    lot_size: int = 65,
):
    """Backtest theta-first option-selling structures, one trade/day."""
    x = _prepare(df)
    trades: list[Trade] = []
    if x.empty:
        return pd.DataFrame(), {}

    for session_date, day in x.groupby(x["timestamp"].dt.date, sort=True):
        entry_ts = _nearest_ts(day, entry_time)
        exit_ts = _nearest_ts(day, exit_time)
        if entry_ts is None or exit_ts is None or exit_ts <= entry_ts:
            continue

        entry = _snapshot(day, entry_ts)
        if entry.empty:
            continue

        spot = float(entry["spot"].median())
        atm = float(entry.loc[(entry["strike"] - spot).abs().idxmin(), "strike"])

        if strategy == "ATM Straddle":
            ce = _row(entry, "CE", atm)
            pe = _row(entry, "PE", atm)
        else:
            ce = _select_theta(entry, "CE", min_abs_delta, max_abs_delta)
            pe = _select_theta(entry, "PE", min_abs_delta, max_abs_delta)

        if ce is None or pe is None:
            continue

        ce_k, pe_k = float(ce["strike"]), float(pe["strike"])
        ce_in, pe_in = float(ce["close"]), float(pe["close"])

        wing_ce = wing_pe = None
        hedge_cost = 0.0
        if strategy == "Dynamic Theta Iron Condor":
            wing_ce = _row(entry, "CE", ce_k + wing_distance * 50)
            wing_pe = _row(entry, "PE", pe_k - wing_distance * 50)
            if wing_ce is None or wing_pe is None:
                continue
            hedge_cost = float(wing_ce["close"]) + float(wing_pe["close"])

        ce_out = _price(day, exit_ts, "CE", ce_k)
        pe_out = _price(day, exit_ts, "PE", pe_k)
        if ce_out is None or pe_out is None:
            continue

        exit_debit = ce_out + pe_out
        if wing_ce is not None and wing_pe is not None:
            hce = _price(day, exit_ts, "CE", float(wing_ce["strike"]))
            hpe = _price(day, exit_ts, "PE", float(wing_pe["strike"]))
            if hce is None or hpe is None:
                continue
            exit_debit -= hce + hpe

        entry_credit = ce_in + pe_in - hedge_cost
        pnl = entry_credit - exit_debit
        trades.append(
            Trade(
                str(session_date),
                strategy,
                str(entry_ts),
                str(exit_ts),
                str(ce["expiry"]),
                spot,
                ce_k,
                pe_k,
                entry_credit,
                exit_debit,
                pnl,
                pnl * lot_size,
            )
        )

    result = pd.DataFrame([t.__dict__ for t in trades])
    if result.empty:
        return result, {}

    result["date"] = pd.to_datetime(result["date"])
    result["cum_pnl_rupees"] = result["pnl_rupees"].cumsum()
    result["peak_rupees"] = result["cum_pnl_rupees"].cummax()
    result["drawdown_rupees"] = result["cum_pnl_rupees"] - result["peak_rupees"]
    wins = result.loc[result["pnl_rupees"] > 0, "pnl_rupees"]
    losses = result.loc[result["pnl_rupees"] < 0, "pnl_rupees"]

    summary = {
        "trades": int(len(result)),
        "win_rate": float((result["pnl_rupees"] > 0).mean() * 100),
        "net_pnl": float(result["pnl_rupees"].sum()),
        "avg_day": float(result["pnl_rupees"].mean()),
        "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() else None,
        "max_drawdown": float(result["drawdown_rupees"].min()),
        "best_day": float(result["pnl_rupees"].max()),
        "worst_day": float(result["pnl_rupees"].min()),
    }
    return result, summary


def compare_strategies(df: pd.DataFrame, strategies: Iterable[str] | None = None, **kwargs):
    strategies = list(
        strategies
        or [
            "ATM Straddle",
            "Theta-Efficient Strangle",
            "Dynamic Theta Strangle",
            "Dynamic Theta Iron Condor",
        ]
    )
    rows, details = [], {}
    for name in strategies:
        trades, summary = backtest_theta(df, strategy=name, **kwargs)
        details[name] = trades
        rows.append({"Strategy": name, **summary})
    return pd.DataFrame(rows), details
