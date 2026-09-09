from __future__ import annotations

import pandas as pd


def summarize(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0, "net_pnl": 0.0, "roi": 0.0, "win_rate": 0.0, "profit_factor": 0.0, "max_drawdown": 0.0, "avg_win": 0.0, "avg_loss": 0.0}
    pnl = pd.to_numeric(trades["pnl"], errors="coerce").fillna(0.0)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    equity = pnl.cumsum()
    drawdown = equity - equity.cummax()
    gross_loss = abs(losses.sum())
    return {
        "trades": int(len(trades)),
        "net_pnl": float(pnl.sum()),
        "roi": float(pnl.sum()),
        "win_rate": float((pnl > 0).mean() * 100),
        "profit_factor": float(wins.sum() / gross_loss) if gross_loss else float("inf"),
        "max_drawdown": float(abs(drawdown.min())) if not drawdown.empty else 0.0,
        "avg_win": float(wins.mean()) if not wins.empty else 0.0,
        "avg_loss": float(losses.mean()) if not losses.empty else 0.0,
    }
