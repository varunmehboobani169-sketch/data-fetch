from __future__ import annotations

from datetime import date
import streamlit as st

st.set_page_config(
    page_title="NIFTY Intraday Option Selling Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 1550px; padding-top: 1rem; padding-bottom: 2rem;}
    [data-testid="stSidebar"] {min-width: 330px; max-width: 360px;}
    .hero {padding: 18px 20px; border: 1px solid rgba(128,128,128,.22); border-radius: 14px; margin-bottom: 16px;}
    .small {font-size: .88rem; opacity: .78;}
    .section {font-size: 1.05rem; font-weight: 700; margin: 10px 0 8px 0;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Session state ----------
for key, default in {
    "dhan_client_id": "",
    "dhan_token": "",
    "connected": False,
    "live_mode": False,
    "last_action": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ---------- Sidebar ----------
with st.sidebar:
    st.header("🔐 Dhan Login")
    st.caption("Credentials are kept only in the Streamlit session and are never written to GitHub.")

    cid = st.text_input("Dhan Client ID", value=st.session_state.dhan_client_id)
    tok = st.text_input("Dhan Access Token", value=st.session_state.dhan_token, type="password")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Connect", type="primary", use_container_width=True):
            st.session_state.dhan_client_id = cid.strip()
            st.session_state.dhan_token = tok.strip()
            st.session_state.connected = bool(st.session_state.dhan_client_id and st.session_state.dhan_token)
            st.session_state.last_action = "Connected" if st.session_state.connected else "Missing credentials"
    with c2:
        if st.button("Clear", use_container_width=True):
            st.session_state.dhan_client_id = ""
            st.session_state.dhan_token = ""
            st.session_state.connected = False
            st.session_state.live_mode = False
            st.session_state.last_action = "Disconnected"
            st.rerun()

    if st.session_state.connected:
        st.success("Dhan session ready")
    else:
        st.info("Disconnected")

    st.divider()
    st.header("Engine Controls")
    mode = st.radio("Data mode", ["Historical", "Live"], horizontal=True)
    st.session_state.live_mode = mode == "Live"

    if not st.session_state.live_mode:
        hist_date = st.date_input("Research date", value=date.today())
    else:
        hist_date = date.today()

    expiry = st.selectbox("Expiry", ["Nearest weekly", "Next weekly", "Select later"])
    strike_range = st.slider("Strike universe", 1, 20, 20)
    sides = st.multiselect("Option sides", ["CE", "PE"], default=["CE", "PE"])
    timeframe = st.selectbox("Timeframe", ["1 minute"], disabled=True)

    st.divider()
    st.subheader("Position Monitor")
    position_enabled = st.toggle("Enable position monitor", value=False)
    if position_enabled:
        st.selectbox("Position", ["None", "Short Strangle", "Iron Condor", "Short Call", "Short Put"])
        st.number_input("Reference quantity", min_value=1, value=1, step=1)

# ---------- Hero ----------
st.markdown(
    """
    <div class="hero">
      <h1 style="margin-bottom:4px;">📈 NIFTY Intraday Option Selling Engine</h1>
      <div class="small">Theta + Vega + IV + market regime • Decision-first dashboard prototype</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------- Status strip ----------
c0, c1, c2, c3, c4 = st.columns(5)
c0.metric("NIFTY", "25,200", "+0.42%")
c1.metric("ATM", "25,200")
c2.metric("Expiry", "10-Sep-2026")
c3.metric("Time", "11:05")
c4.metric("Data", "1 min")

# ---------- Main decision ----------
left, right = st.columns([1.55, 1])
with left:
    st.markdown('<div class="section">Selling Environment</div>', unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    a.metric("Theta", "+4.82", "Strong")
    b.metric("Vega", "1.41", "Low risk")
    c.metric("Theta / Vega", "3.42x", "Favourable")
    d.metric("IV Regime", "Falling", "Good")

    st.markdown("### 🎯 Selling Score")
    st.progress(0.84)
    s1, s2, s3 = st.columns(3)
    s1.metric("Score", "84 / 100")
    s2.metric("Regime", "Sideways")
    s3.metric("Action", "SELL SELECTIVELY")

    st.markdown('<div class="section">Market Regime</div>', unsafe_allow_html=True)
    regime = st.dataframe(
        {
            "Engine": ["Trend", "Volatility", "IV", "Theta", "Vega"],
            "Reading": ["Sideways", "Low → Stable", "High → Falling", "Strong", "Low"],
            "Signal": ["Neutral", "Favourable", "Favourable", "Favourable", "Favourable"],
        },
        use_container_width=True,
        hide_index=True,
    )

with right:
    st.markdown('<div class="section">⚡ Recommended Setup</div>', unsafe_allow_html=True)
    st.success("CONDITIONS FAVOUR PREMIUM SELLING")
    st.write("**Preferred structure:** Iron Condor")
    st.write("**Short CE:** 25,400")
    st.write("**Short PE:** 25,000")
    st.write("**Outer wings:** 25,500 / 24,900")
    st.divider()
    st.metric("Estimated Greek edge", "+₹1,220")
    st.metric("Theta / Vega", "3.42x")
    st.caption("Illustrative values only — not yet connected to live calculations.")

# ---------- Strike ranking ----------
st.markdown("---")
st.markdown('<div class="section">🏆 Strike Ranking</div>', unsafe_allow_html=True)

ranking = {
    "Rank": [1, 2, 3, 4, 5, 6],
    "Option": ["25,400 CE", "25,350 CE", "25,000 PE", "24,950 PE", "25,450 CE", "24,900 PE"],
    "Offset": [4, 3, -4, -5, 5, -6],
    "Theta": ["+2.18", "+2.04", "+2.11", "+1.94", "+1.82", "+1.75"],
    "Vega": ["0.64", "0.71", "0.68", "0.73", "0.79", "0.81"],
    "Theta/Vega": [3.41, 2.87, 3.10, 2.66, 2.30, 2.16],
    "Sell Score": [94, 90, 92, 86, 79, 75],
    "Status": ["Preferred", "Strong", "Preferred", "Strong", "Watch", "Watch"],
}
st.dataframe(ranking, use_container_width=True, hide_index=True)

# ---------- Charts placeholder ----------
ch1, ch2 = st.columns(2)
with ch1:
    st.markdown('<div class="section">Theta / Vega Trend</div>', unsafe_allow_html=True)
    st.line_chart({"Theta/Vega": [2.1, 2.3, 2.6, 2.8, 3.1, 3.0, 3.2, 3.4]})
with ch2:
    st.markdown('<div class="section">NIFTY / ATM Context</div>', unsafe_allow_html=True)
    st.line_chart({"NIFTY": [25120, 25135, 25150, 25142, 25170, 25188, 25195, 25200], "ATM": [25100, 25100, 25150, 25150, 25150, 25200, 25200, 25200]})

# ---------- Position monitor ----------
st.markdown("---")
st.markdown('<div class="section">🛡 Position Monitor</div>', unsafe_allow_html=True)
if position_enabled:
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Position", "IRON CONDOR")
    p2.metric("MTM", "+₹1,840", "+₹260")
    p3.metric("Theta", "+₹1,220")
    p4.metric("Vega risk", "Moderate")
    st.warning("VEGA RISK: monitor for acceleration")
else:
    st.info("Position monitor is off. Turn it on from the left panel when you want to track an existing trade.")

# ---------- Data / implementation roadmap ----------
st.markdown("---")
with st.expander("What this prototype will become"):
    st.markdown(
        """
**Phase 1 — Data:** connect the dashboard to Dhan 1-minute NIFTY/option history and live data.

**Phase 2 — Greeks:** calculate and validate Theta, Vega, IV, Delta and Gamma at each minute.

**Phase 3 — Engine:** build the actual Selling Score from Theta/Vega efficiency, IV regime, trend, realized volatility and OI.

**Phase 4 — Strike selector:** rank CE/PE strikes and suggest the best structure.

**Phase 5 — Backtest:** test the score and strike-selection rules on 2024–2026 historical data before using them live.
        """
    )

st.caption(
    f"Mode: {'Live' if st.session_state.live_mode else 'Historical'} • Date: {hist_date:%d-%b-%Y} • "
    f"Requested universe: ATM−{strike_range}…ATM+{strike_range} • {timeframe}"
)
