from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from research.backtest_engine import BacktestConfig, run_backtest
from research.data_adapter import load_uploaded_files, normalize_frame
from research.strategy_loader import load_strategy_from_source

st.set_page_config(page_title="NIFTY Research Lab", page_icon="🧪", layout="wide")

st.title("🧪 NIFTY Research Lab")
st.caption("Choose a dataset → upload/select a Python strategy → run the backtest")

# -----------------------------------------------------------------------------
# Dataset
# -----------------------------------------------------------------------------
st.subheader("1. Dataset")

repo_data_dir = Path("data")
repo_datasets = []
if repo_data_dir.exists():
    repo_datasets = sorted(
        [
            p for p in repo_data_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".csv", ".parquet"}
        ]
    )

if repo_datasets:
    labels = [str(p.relative_to(repo_data_dir)) for p in repo_datasets]
    selected_label = st.selectbox(
        "Dataset already stored in GitHub",
        ["Upload a new dataset"] + labels,
    )
else:
    selected_label = "Upload a new dataset"
    st.info("No repository dataset was found. Upload one below, or place a CSV/Parquet file under data/ in GitHub.")

uploaded_data = st.file_uploader(
    "Upload CSV or Parquet",
    type=["csv", "parquet"],
    accept_multiple_files=True,
    key="data_uploads",
)

# -----------------------------------------------------------------------------
# Strategy
# -----------------------------------------------------------------------------
st.subheader("2. Strategy")

strategy_source = st.file_uploader(
    "Upload strategy Python (.py)",
    type=["py"],
    accept_multiple_files=False,
    key="strategy_upload",
    help="Your Python file should define exactly one strategy class with name and signal(day, config).",
)

st.caption("Strategy contract: return decisions such as {'option_type': 'CE', 'strike': 25000} from signal().")

built_in = st.checkbox("Use built-in ATM Breakout strategy instead", value=not bool(strategy_source))

# -----------------------------------------------------------------------------
# Backtest controls
# -----------------------------------------------------------------------------
st.subheader("3. Backtest settings")
col1, col2, col3, col4 = st.columns(4)
with col1:
    entry_hour = st.number_input("Entry hour", 0, 23, 9, 1)
with col2:
    entry_minute = st.number_input("Entry minute", 0, 59, 30, 1)
with col3:
    exit_hour = st.number_input("Exit hour", 0, 23, 15, 1)
with col4:
    exit_minute = st.number_input("Exit minute", 0, 59, 15, 1)

col1, col2, col3, col4 = st.columns(4)
with col1:
    stop_loss = st.number_input("Stop-loss %", min_value=0.0, max_value=100.0, value=25.0, step=1.0) / 100
with col2:
    target = st.number_input("Target %", min_value=0.0, max_value=500.0, value=50.0, step=1.0) / 100
with col3:
    lot_size = st.number_input("Lot size", min_value=1, value=65, step=1)
with col4:
    lots = st.number_input("Lots", min_value=1, value=1, step=1)

# -----------------------------------------------------------------------------
# Run
# -----------------------------------------------------------------------------
if st.button("Run Backtest", type="primary", use_container_width=True):
    try:
        # Load data either from the repository or from the uploader.
        if selected_label != "Upload a new dataset":
            dataset_path = repo_data_dir / selected_label
            data = load_uploaded_files([dataset_path])
        else:
            if not uploaded_data:
                st.error("Upload a CSV/Parquet dataset or select a repository dataset first.")
                st.stop()

            frames = []
            for file in uploaded_data:
                raw = (
                    pd.read_parquet(io.BytesIO(file.getvalue()))
                    if file.name.lower().endswith(".parquet")
                    else pd.read_csv(io.BytesIO(file.getvalue()))
                )
                frames.append(normalize_frame(raw))
            data = pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)

        if data.empty:
            st.error("The dataset loaded successfully but contains no valid rows after normalization.")
            st.stop()

        # Load either the uploaded Python strategy or the built-in strategy.
        if strategy_source is not None and not built_in:
            source = strategy_source.getvalue().decode("utf-8")
            strategy = load_strategy_from_source(source, strategy_source.name)
        else:
            from research.strategies.breakout import BreakoutStrategy

            strategy = BreakoutStrategy()

        config = BacktestConfig(
            entry_time=f"{entry_hour:02d}:{entry_minute:02d}",
            exit_time=f"{exit_hour:02d}:{exit_minute:02d}",
            stop_loss_pct=stop_loss,
            target_pct=target,
            lot_size=int(lot_size),
            lots=int(lots),
        )

        results = run_backtest(data, strategy, config)

        st.success(f"Backtest complete: {strategy.name}")
        st.write(f"Rows loaded: **{len(data):,}**")

        if results.empty:
            st.warning("No trades were generated for this strategy and dataset.")
            st.stop()

        total_pnl = float(results["pnl"].sum())
        wins = int(results["win"].sum())
        trade_count = len(results)
        win_rate = wins / trade_count * 100
        gross_profit = float(results.loc[results["pnl"] > 0, "pnl"].sum())
        gross_loss = float(-results.loc[results["pnl"] < 0, "pnl"].sum())
        profit_factor = gross_profit / gross_loss if gross_loss else float("inf")
        equity = results["cum_pnl"]
        drawdown = equity - equity.cummax()
        max_drawdown = float(drawdown.min())

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Net P&L", f"₹{total_pnl:,.0f}")
        m2.metric("Trades", f"{trade_count:,}")
        m3.metric("Win rate", f"{win_rate:.1f}%")
        m4.metric("Profit factor", f"{profit_factor:.2f}" if profit_factor != float("inf") else "∞")
        m5.metric("Max drawdown", f"₹{max_drawdown:,.0f}")

        st.subheader("Trade log")
        st.dataframe(results, use_container_width=True, hide_index=True)

        st.download_button(
            "Download trade log CSV",
            results.to_csv(index=False).encode("utf-8"),
            file_name="backtest_trades.csv",
            mime="text/csv",
        )

    except Exception as exc:
        st.error(f"Backtest failed: {exc}")
        st.exception(exc)

st.divider()
st.caption(
    "Python strategies are executed by the Streamlit app, so only upload strategy files you trust. "
    "For permanent datasets, storing compressed Parquet files in the repository avoids re-uploading them each run."
)
