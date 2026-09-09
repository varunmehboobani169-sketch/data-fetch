from __future__ import annotations

from pathlib import Path
import tempfile

import pandas as pd
import streamlit as st

from research.data_adapter import normalize_frame
from research.backtest_engine import BacktestConfig, run_backtest
from research.metrics import summarize
from research.strategies.breakout import BreakoutStrategy

st.set_page_config(page_title="NIFTY Research Lab", page_icon="🧪", layout="wide")
st.title("🧪 NIFTY Research Lab")
st.caption("Upload historical data, choose a strategy, and test it. This is research only; no live orders are placed.")

with st.sidebar:
    st.header("Backtest Settings")
    entry_time = st.time_input("Entry time", value=pd.Timestamp("09:30").time())
    exit_time = st.time_input("Square-off", value=pd.Timestamp("15:15").time())
    sl = st.number_input("Stop-loss %", 1.0, 90.0, 25.0, 1.0) / 100.0
    target = st.number_input("Target %", 1.0, 200.0, 50.0, 1.0) / 100.0
    lot_size = st.number_input("Lot size", 1, 10000, 65, 1)
    lots = st.number_input("Lots", 1, 100, 1, 1)
    slippage = st.number_input("Slippage % of notional", 0.0, 1.0, 0.0, 0.01) / 100.0

files = st.file_uploader("Upload CSV or Parquet market-data files", type=["csv", "parquet"], accept_multiple_files=True)

if files:
    frames = []
    errors = []
    with tempfile.TemporaryDirectory() as td:
        for uploaded in files:
            path = Path(td) / uploaded.name
            path.write_bytes(uploaded.getvalue())
            try:
                raw = pd.read_parquet(path) if path.suffix.lower() == ".parquet" else pd.read_csv(path)
                frames.append(normalize_frame(raw))
            except Exception as exc:
                errors.append(f"{uploaded.name}: {exc}")
    if errors:
        st.warning("Some files could not be loaded:\n" + "\n".join(errors))
    if frames:
        data = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
        st.success(f"Loaded {len(data):,} rows from {len(frames)} file(s).")
        st.dataframe(data.head(20), use_container_width=True, hide_index=True)

        strategy = BreakoutStrategy()
        config = BacktestConfig(
            entry_time=entry_time.strftime("%H:%M"),
            exit_time=exit_time.strftime("%H:%M"),
            stop_loss_pct=sl,
            target_pct=target,
            lot_size=int(lot_size),
            lots=int(lots),
            slippage_pct=slippage,
        )

        if st.button("Run Backtest", type="primary", use_container_width=True):
            with st.spinner("Running backtest..."):
                trades = run_backtest(data, strategy, config)
            st.session_state["research_trades"] = trades

trades = st.session_state.get("research_trades", pd.DataFrame())
if not trades.empty:
    s = summarize(trades)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Net P&L", f"₹{s['net_pnl']:,.0f}")
    c2.metric("Win rate", f"{s['win_rate']:.1f}%")
    c3.metric("Profit factor", f"{s['profit_factor']:.2f}")
    c4.metric("Trades", f"{s['trades']}")
    c5.metric("Max drawdown", f"₹{s['max_drawdown']:,.0f}")
    c6.metric("Avg win", f"₹{s['avg_win']:,.0f}")
    st.subheader("Equity Curve")
    st.line_chart(trades.set_index("date")["cum_pnl"])
    st.subheader("Trade Log")
    st.dataframe(trades, use_container_width=True, hide_index=True)
    st.download_button("Download Trade Log", trades.to_csv(index=False), "backtest_trades.csv", "text/csv", use_container_width=True)
else:
    st.info("Upload historical data and run the backtest.")
