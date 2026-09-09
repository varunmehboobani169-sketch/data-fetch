from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from research.backtest_engine import BacktestConfig, run_backtest
from research.data_adapter import normalize_frame
from research.metrics import summarize
from research.strategies.breakout import BreakoutStrategy

st.set_page_config(page_title="Backtest Lab", page_icon="🧪", layout="centered")

st.markdown("# 🧪 Backtest Lab")
st.caption("Upload your market data and strategy. Run the backtest. Nothing else.")


def load_uploaded_strategy(uploaded):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / uploaded.name
        path.write_bytes(uploaded.getvalue())
        spec = importlib.util.spec_from_file_location("uploaded_strategy", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load the strategy file.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        candidates = []
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and hasattr(obj, "signal"):
                candidates.append(obj)
        if not candidates:
            raise RuntimeError("Strategy file must contain a class with a signal(day, config) method.")
        return candidates[0]()


st.subheader("1. Market Data")
data_files = st.file_uploader(
    "Upload CSV or Parquet files",
    type=["csv", "parquet"],
    accept_multiple_files=True,
)

st.subheader("2. Strategy")
strategy_mode = st.radio("Use", ["Built-in strategy", "Upload strategy"], horizontal=True)
strategy_file = None
if strategy_mode == "Built-in strategy":
    strategy = BreakoutStrategy()
    st.caption(f"Strategy: {strategy.name}")
else:
    strategy_file = st.file_uploader("Upload Python strategy file", type=["py"])
    strategy = None
    if strategy_file is not None:
        try:
            strategy = load_uploaded_strategy(strategy_file)
            st.success(f"Loaded: {getattr(strategy, 'name', strategy_file.name)}")
        except Exception as exc:
            st.error(f"Strategy could not be loaded: {exc}")

st.subheader("3. Run")
run_clicked = st.button("Run Backtest", type="primary", use_container_width=True)

if run_clicked:
    if not data_files:
        st.error("Upload at least one market-data file.")
    elif strategy is None:
        st.error("Select or upload a valid strategy.")
    else:
        frames = []
        errors = []
        for uploaded in data_files:
            try:
                raw = pd.read_parquet(uploaded) if uploaded.name.lower().endswith(".parquet") else pd.read_csv(uploaded)
                frames.append(normalize_frame(raw))
            except Exception as exc:
                errors.append(f"{uploaded.name}: {exc}")

        if errors:
            st.error("Data loading failed:\n" + "\n".join(errors))
        elif not frames:
            st.error("No usable data was loaded.")
        else:
            data = pd.concat(frames, ignore_index=True).sort_values("timestamp").drop_duplicates().reset_index(drop=True)
            config = BacktestConfig()
            with st.spinner("Running backtest..."):
                trades = run_backtest(data, strategy, config)

            if trades.empty:
                st.warning("The strategy produced no trades on this dataset.")
            else:
                summary = summarize(trades)
                st.success(f"Completed • {len(trades):,} trades")

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Net P&L", f"₹{summary['net_pnl']:,.0f}")
                c2.metric("Win Rate", f"{summary['win_rate']:.1f}%")
                c3.metric("Profit Factor", f"{summary['profit_factor']:.2f}")
                c4.metric("Max Drawdown", f"₹{summary['max_drawdown']:,.0f}")

                st.subheader("Equity Curve")
                st.line_chart(trades.set_index("date")["cum_pnl"])

                st.subheader("Trade Log")
                st.dataframe(trades, use_container_width=True, hide_index=True)

                st.download_button(
                    "Download Trade Log",
                    trades.to_csv(index=False),
                    file_name="backtest_trades.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

st.divider()
st.caption("Research only • Replace the data or strategy at any time and run a new test.")
