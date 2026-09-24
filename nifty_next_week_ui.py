from __future__ import annotations

import io
import os
import zipfile
from datetime import date

import pandas as pd
import streamlit as st

from dhan_next_week import (
    DhanClient,
    NIFTY_UNDERLYING_SECURITY_ID,
    choose_expiry_for_week,
    contracts_from_chain,
    fetch_contracts,
    next_week_window,
)

st.set_page_config(page_title="NIFTY Next-Week 1m Downloader", page_icon="📈", layout="wide")

st.title("NIFTY Next-Week Option Data Downloader")
st.caption("DhanHQ v2 · 1-minute NIFTY option candles · secure session credentials · CSV/Parquet export")

with st.sidebar:
    st.header("Dhan connection")
    client_id = st.text_input("Client ID", value=os.getenv("DHAN_CLIENT_ID", ""))
    access_token = st.text_input("Access Token", value=os.getenv("DHAN_ACCESS_TOKEN", ""), type="password")
    underlying_id = st.number_input(
        "NIFTY underlying security ID",
        min_value=1,
        value=int(os.getenv("DHAN_NIFTY_UNDERLYING_ID", NIFTY_UNDERLYING_SECURITY_ID)),
        step=1,
        help="Default 13 follows the NIFTY example used in Dhan's Option Chain docs. Keep editable in case Dhan changes mappings.",
    )
    st.info("Credentials stay in this Streamlit process/session. Do not commit tokens to GitHub.")

week_start, week_end = next_week_window()

col1, col2, col3, col4 = st.columns(4)
with col1:
    start_date = st.date_input("Week start", value=week_start)
with col2:
    end_date = st.date_input("Week end", value=week_end)
with col3:
    strikes_each_side = st.selectbox("Strike range", [5, 10, 20, 30], index=3, format_func=lambda x: f"ATM ±{x}")
with col4:
    include_oi = st.toggle("Include OI", value=True)

st.markdown("---")

if "chain" not in st.session_state:
    st.session_state.chain = None
if "expiry" not in st.session_state:
    st.session_state.expiry = None
if "contracts" not in st.session_state:
    st.session_state.contracts = []
if "spot" not in st.session_state:
    st.session_state.spot = None
if "atm" not in st.session_state:
    st.session_state.atm = None

left, right = st.columns([1, 2])

with left:
    st.subheader("1. Discover next-week contracts")
    if st.button("Connect & Load NIFTY Chain", type="primary", use_container_width=True):
        try:
            client = DhanClient(client_id, access_token)
            expiries = client.expiry_list(underlying_security_id=int(underlying_id))
            expiry = choose_expiry_for_week(expiries, start_date, end_date)
            chain = client.option_chain(expiry, underlying_security_id=int(underlying_id))
            contracts, spot, atm = contracts_from_chain(chain, strikes_each_side=strikes_each_side)
            contracts = [
                c.__class__(
                    expiry=expiry,
                    strike=c.strike,
                    side=c.side,
                    security_id=c.security_id,
                    offset=c.offset,
                )
                for c in contracts
            ]
            st.session_state.chain = chain
            st.session_state.expiry = expiry
            st.session_state.contracts = contracts
            st.session_state.spot = spot
            st.session_state.atm = atm
            st.success(f"Loaded {len(contracts)} contracts for expiry {expiry}.")
        except Exception as exc:
            st.error(str(exc))

    if st.session_state.expiry:
        st.metric("Selected expiry", st.session_state.expiry)
        a, b = st.columns(2)
        a.metric("NIFTY spot", f"{st.session_state.spot:,.2f}")
        b.metric("ATM strike", f"{st.session_state.atm:,.0f}")
        st.write(f"Resolved contracts: **{len(st.session_state.contracts)}**")

with right:
    st.subheader("Contract universe")
    if st.session_state.contracts:
        contract_df = pd.DataFrame([c.__dict__ for c in st.session_state.contracts])
        contract_df = contract_df.rename(columns={"side": "option_type"})
        st.dataframe(contract_df, use_container_width=True, height=300)
    else:
        st.info("Load the option chain to resolve actual Dhan security IDs for CE/PE contracts.")

st.markdown("---")
st.subheader("2. Fetch 1-minute candles")

future_note = date.today() < start_date
if future_note:
    st.warning(
        "This date range is still in the future. The app can resolve the active next-week contracts now, "
        "but Dhan's historical intraday endpoint can only return candles after they exist. Re-run during or after next week."
    )

fetch_disabled = not bool(st.session_state.contracts)
if st.button("Fetch 1-Minute Data", disabled=fetch_disabled, use_container_width=True):
    try:
        client = DhanClient(client_id, access_token)
        with st.spinner("Downloading 1-minute candles from DhanHQ..."):
            data, manifest = fetch_contracts(
                client,
                st.session_state.contracts,
                start_date=start_date,
                end_date=end_date,
                include_oi=include_oi,
            )
        st.session_state.data = data
        st.session_state.manifest = manifest
    except Exception as exc:
        st.error(str(exc))

if "manifest" in st.session_state:
    manifest = st.session_state.manifest
    data = st.session_state.get("data", pd.DataFrame())

    ok = int((manifest.get("status") == "ok").sum()) if "status" in manifest.columns else 0
    errors = int((manifest.get("status") == "error").sum()) if "status" in manifest.columns else 0
    empty = int((manifest.get("status") == "empty").sum()) if "status" in manifest.columns else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Contracts OK", ok)
    c2.metric("Empty", empty)
    c3.metric("Errors", errors)
    c4.metric("Total candles", f"{len(data):,}")

    st.subheader("Fetch manifest")
    st.dataframe(manifest, use_container_width=True, height=240)

    if not data.empty:
        st.subheader("Data preview")
        st.dataframe(data.head(2000), use_container_width=True, height=360)

        csv_bytes = data.to_csv(index=False).encode("utf-8")
        parquet_buffer = io.BytesIO()
        data.to_parquet(parquet_buffer, index=False)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("nifty_options_1m_combined.csv", csv_bytes)
            manifest_csv = manifest.to_csv(index=False).encode("utf-8")
            zf.writestr("manifest.csv", manifest_csv)
            for (expiry, strike, option_type), grp in data.groupby(["expiry", "strike", "option_type"]):
                name = f"{expiry}_{int(float(strike))}_{option_type}.csv"
                zf.writestr(name, grp.to_csv(index=False).encode("utf-8"))

        d1, d2, d3 = st.columns(3)
        d1.download_button(
            "Download Combined CSV",
            data=csv_bytes,
            file_name="nifty_next_week_options_1m.csv",
            mime="text/csv",
            use_container_width=True,
        )
        d2.download_button(
            "Download Parquet",
            data=parquet_buffer.getvalue(),
            file_name="nifty_next_week_options_1m.parquet",
            mime="application/octet-stream",
            use_container_width=True,
        )
        d3.download_button(
            "Download ZIP by Contract",
            data=zip_buffer.getvalue(),
            file_name="nifty_next_week_options_1m.zip",
            mime="application/zip",
            use_container_width=True,
        )

        st.subheader("Quick quality checks")
        q1, q2, q3 = st.columns(3)
        q1.metric("Unique security IDs", int(data["security_id"].nunique()))
        q2.metric("Unique strikes", int(data["strike"].nunique()))
        q3.metric("Date span", f"{data['timestamp'].min()} → {data['timestamp'].max()}")

st.markdown("---")
st.caption(
    "Uses DhanHQ v2 Option Chain + Expiry List to resolve active NIFTY CE/PE security IDs, then /charts/intraday for 1-minute OHLC, volume and optional OI. "
    "Historical intraday data can only be fetched after bars exist."
)
