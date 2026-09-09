from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="NIFTY Research Lab", page_icon="🧪", layout="wide")

st.title("🧪 NIFTY Research Lab")
st.caption("Upload data → choose a strategy → run a backtest")

st.info("The research lab is loading a minimal, standalone backtest interface. No Dhan login or live-data calls are required.")

st.file_uploader(
    "Upload CSV or Parquet market data",
    type=["csv", "parquet"],
    accept_multiple_files=True,
    key="research_uploads",
)

st.selectbox(
    "Strategy",
    ["ATM Breakout"],
    help="More strategies can be added as independent modules without changing the backtest engine.",
)

st.number_input("Entry time hour", min_value=0, max_value=23, value=9, step=1)
st.number_input("Exit time hour", min_value=0, max_value=23, value=15, step=1)

if st.button("Run Backtest", type="primary", use_container_width=True):
    st.warning("Backtest execution is being connected to the uploaded dataset. The interface is ready; no live trading is involved.")

st.divider()
st.subheader("Results")
st.caption("Results will appear here after a dataset and strategy are connected to the engine.")
