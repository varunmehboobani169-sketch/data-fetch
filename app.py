from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from dhan_data import DhanClient, HistoricalCollector, available_expiries

st.set_page_config(page_title="NIFTY Options Data Lab", page_icon="📊", layout="wide")

st.markdown("""
<style>
.block-container { max-width: 1550px; padding-top: 1rem; }
[data-testid="stSidebar"] { min-width: 320px; max-width: 360px; }
.metric-card { border: 1px solid rgba(128,128,128,.25); border-radius: 10px; padding: 12px; }
</style>
""", unsafe_allow_html=True)

st.title("📊 NIFTY Weekly Options Data Lab")
st.caption("1-minute historical data • weekly expiry • dynamic ATM • requested ATM−20 to ATM+20 • CE + PE")

if "client_id" not in st.session_state:
    st.session_state.client_id = ""
if "token" not in st.session_state:
    st.session_state.token = ""
if "status" not in st.session_state:
    st.session_state.status = "Disconnected"

with st.sidebar:
    st.header("🔐 Dhan Login")
    st.caption("Your credentials are kept only in this Streamlit session. They are never written to GitHub by this app.")
    cid = st.text_input("Dhan Client ID", value=st.session_state.client_id)
    token = st.text_input("Dhan Access Token", value=st.session_state.token, type="password")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Connect", type="primary", use_container_width=True):
            st.session_state.client_id = cid.strip()
            st.session_state.token = token.strip()
            st.session_state.status = "Connected" if st.session_state.token else "Missing token"
    with c2:
        if st.button("Clear", use_container_width=True):
            st.session_state.client_id = ""
            st.session_state.token = ""
            st.session_state.status = "Disconnected"
            st.session_state.pop("data", None)
            st.rerun()

    st.caption(f"Status: **{st.session_state.status}**")
    st.divider()

    st.header("Historical Data")
    start = st.date_input("Start date", value=date(2024, 1, 1), min_value=date(2021, 1, 1), max_value=date.today())
    end = st.date_input("End date", value=date.today(), min_value=date(2021, 1, 1), max_value=date.today())
    strike_range = st.slider("Strike range", 1, 20, 20, help="Requested relative strikes around the minute-by-minute ATM.")
    sides = st.multiselect("Options", ["CE", "PE"], default=["CE", "PE"])
    st.selectbox("Timeframe", ["1 minute"], index=0, disabled=True)
    st.caption("Dhan's rolling expired-options API natively provides ATM±10 for index options. The ±20 control is retained so an extended data adapter can be added later.")
    fetch = st.button("⬇ FETCH HISTORY", type="primary", use_container_width=True)

connected = bool(st.session_state.client_id and st.session_state.token)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Range", f"{start:%d %b %Y} → {end:%d %b %Y}")
m2.metric("Frequency", "1 minute")
m3.metric("Requested universe", f"ATM−{strike_range} … ATM+{strike_range}")
m4.metric("Sides", " + ".join(sides) if sides else "None")

st.info("The fetcher stores every API window locally as Parquet and resumes from existing files. This matters because a multi-year 1-minute dataset is much too large to hold only in browser memory.")

if not connected:
    st.warning("Enter your Dhan Client ID and Access Token in the left panel.")
    st.stop()
if start > end:
    st.error("Start date must be before or equal to end date.")
    st.stop()
if not sides:
    st.error("Select CE, PE, or both.")
    st.stop()

client = DhanClient(st.session_state.client_id, st.session_state.token)
collector = HistoricalCollector(client)

if fetch:
    progress = st.progress(0.0)
    status = st.empty()

    def cb(done: int, total: int, message: str) -> None:
        progress.progress(min(done / max(total, 1), 1.0))
        status.write(message)

    result = collector.fetch_range(start, end, strike_range, sides, cb)
    progress.progress(1.0)
    if result.errors:
        st.warning(f"Fetch finished with {len(result.errors)} failed API windows. Existing successful files were retained.")
        with st.expander("Fetch warnings"):
            st.write(result.errors[:50])
    else:
        st.success("Fetch completed successfully.")
    st.session_state.data = result.frame

if "data" not in st.session_state:
    st.subheader("Ready")
    st.write("Connect to Dhan and click **FETCH HISTORY**. For the complete 2024–today archive, keep the default dates and let the collector resume through all 30-day API windows.")
    st.stop()

df = st.session_state.data.copy()
if df.empty:
    st.error("No data returned for the selected window.")
    st.stop()

# Normalize display types.
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp"]).sort_values(["timestamp", "option_type", "strike_offset"])

# Metrics.
a, b, c, d, e = st.columns(5)
a.metric("Rows", f"{len(df):,}")
b.metric("1-minute timestamps", f"{df.timestamp.nunique():,}")
c.metric("Weekly expiries", f"{df.expiry.nunique():,}")
d.metric("Offsets present", f"{df.strike_offset.nunique():,}")
e.metric("Native Dhan", "ATM±10")

# Filters.
f1, f2, f3 = st.columns(3)
with f1:
    selected_expiry = st.selectbox("Expiry", ["All"] + sorted(df["expiry"].dropna().astype(str).unique().tolist()))
with f2:
    selected_side = st.selectbox("Option type", sides)
with f3:
    offsets = sorted(pd.to_numeric(df.loc[df.option_type.eq(selected_side), "strike_offset"], errors="coerce").dropna().unique().tolist())
    chosen_offset = st.select_slider("ATM offset", options=offsets or [0], value=0 if 0 in offsets else offsets[len(offsets)//2])

view = df[df.option_type.eq(selected_side) & (df.strike_offset == chosen_offset)].copy()
if selected_expiry != "All":
    view = view[view.expiry.astype(str) == selected_expiry]

if view.empty:
    st.warning("No rows match the current filters.")
    st.stop()

# Price chart without forcing a custom colour palette.
st.subheader(f"{selected_side} • ATM{chosen_offset:+d}")
st.line_chart(view.set_index("timestamp")["close"], height=400)

x1, x2, x3 = st.tabs(["OI", "Volume", "Option Chain Snapshot"])
with x1:
    if "oi" in view:
        st.line_chart(view.set_index("timestamp")["oi"], height=300)
with x2:
    if "volume" in view:
        st.line_chart(view.set_index("timestamp")["volume"], height=300)
with x3:
    latest = df["timestamp"].max()
    snap = df[df.timestamp == latest].copy()
    cols = [c for c in ["timestamp", "expiry", "spot", "atm", "strike_offset", "moneyness", "strike", "option_type", "open", "high", "low", "close", "volume", "oi", "iv"] if c in snap.columns]
    st.caption(f"Latest available 1-minute snapshot: {latest}")
    st.dataframe(snap[cols].sort_values(["strike_offset", "option_type"]), use_container_width=True, hide_index=True)

st.divider()
st.subheader("Data Preview")
st.dataframe(df.head(500), use_container_width=True, height=360, hide_index=True)

csv = df.to_csv(index=False).encode("utf-8")
st.download_button("⬇ Download current result as CSV", csv, file_name="nifty_weekly_options_1m.csv", mime="text/csv", use_container_width=True)

with st.expander("Dhan coverage and data notes"):
    st.markdown("""
Dhan's **Expired Options Data** endpoint provides minute-level rolling expired-options data for up to five years, including OHLC, IV, volume, OI and spot. Its documented index-option range is **ATM±10**. The app therefore never fills ATM±11…ATM±20 with invented values. citeturn772798view0

Dhan's v2 historical intraday API also supports 1-minute candles and OI for active futures/options instruments, with up to 90 days per request, which is useful as a secondary route when an exact historical contract/security ID is available. citeturn366055search2
""")
