from __future__ import annotations

from datetime import date
import streamlit as st

from regime_engine import MarketInputs, classify

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

for key, default in {
    "dhan_client_id": "1113195747",
    "dhan_token": "",
    "connected": False,
    "live_mode": False,
    "last_action": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

with st.sidebar:
    st.header("🔐 Dhan Login")
    st.caption("Client ID is pre-filled. Access Token stays only in this Streamlit session.")

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
            st.session_state.dhan_token = ""
            st.session_state.connected = False
            st.session_state.live_mode = False
            st.session_state.last_action = "Disconnected"

    st.success("Dhan session ready") if st.session_state.connected else st.info("Disconnected")

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
    st.subheader("Paper Position Monitor")
    position_enabled = st.toggle("Enable position monitor", value=False)
    position_type = st.selectbox(
        "Position structure",
        ["None", "Iron Condor", "Bull Put Spread", "Bear Call Spread", "Short Strangle"],
        disabled=not position_enabled,
    )
    quantity = st.number_input("Reference quantity", min_value=1, value=1, step=1, disabled=not position_enabled)

st.markdown(
    """
    <div class="hero">
      <h1 style="margin-bottom:4px;">📈 NIFTY Intraday Option Selling Engine</h1>
      <div class="small">Theta + Vega + IV + market regime • regime-based paper-trading prototype</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Prototype inputs. These are deliberately labeled as sample values until the Dhan
# historical/live data adapter is connected and validated.
proto = MarketInputs(
    trend_score=0.05,
    realized_vol_percentile=38,
    iv_percentile=72,
    iv_change=-0.35,
    theta_vega=0.34,
)
result = classify(proto)

c0, c1, c2, c3, c4 = st.columns(5)
c0.metric("NIFTY", "25,200", "+0.42%")
c1.metric("ATM", "25,200")
c2.metric("Expiry", "10-Sep-2026")
c3.metric("Time", "11:05")
c4.metric("Data", "1 min")

left, right = st.columns([1.55, 1])
with left:
    st.markdown('<div class="section">Selling Environment</div>', unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    a.metric("Theta / Vega", f"{proto.theta_vega:.2f}x", "Research input")
    b.metric("IV Percentile", f"{proto.iv_percentile:.0f}%", "Research input")
    c.metric("IV Change", f"{proto.iv_change:+.2f}", "Research input")
    d.metric("Realized Vol", f"{proto.realized_vol_percentile:.0f}th pct", "Research input")

    st.markdown("### 🎯 Selling Score")
    st.progress(result.selling_score / 100)
    s1, s2, s3 = st.columns(3)
    s1.metric("Score", f"{result.selling_score} / 100")
    s2.metric("Regime", result.regime)
    s3.metric("Action", result.action)

    st.markdown('<div class="section">Market Regime Decision Tree</div>', unsafe_allow_html=True)
    regime_rows = {
        "Engine": ["Trend", "Realized Vol", "IV", "Theta/Vega"],
        "Reading": [
            "Neutral / Sideways",
            f"{proto.realized_vol_percentile:.0f}th percentile",
            f"{proto.iv_percentile:.0f}th percentile • {proto.iv_change:+.2f}",
            f"{proto.theta_vega:.2f}x",
        ],
        "Interpretation": [
            result.regime,
            "Contained" if proto.realized_vol_percentile < 50 else "Elevated",
            "Falling" if proto.iv_change < 0 else "Rising",
            "Favorable" if proto.theta_vega >= 0.30 else "Selective",
        ],
    }
    st.dataframe(regime_rows, use_container_width=True, hide_index=True)

with right:
    st.markdown('<div class="section">⚡ Strategy Selection</div>', unsafe_allow_html=True)
    if result.selling_score >= 80:
        st.success("CONDITIONS FAVOUR PREMIUM SELLING")
    elif result.selling_score >= 65:
        st.warning("SELECTIVE PREMIUM SELLING")
    else:
        st.error("AVOID NEW PREMIUM SELLING")

    st.write(f"**Preferred structure:** {result.preferred_strategy}")
    st.write("**Short-side selection:** determined by regime + strike ranking")
    st.write("**Wings:** determined by risk budget and tested distance rules")
    st.divider()
    st.metric("Selling Score", f"{result.selling_score}/100")
    st.metric("Theta/Vega", f"{proto.theta_vega:.2f}x")
    st.caption("Prototype decision only. No live orders are placed.")

    st.markdown("**Why this decision?**")
    for reason in result.reasons:
        st.write(f"• {reason}")

st.markdown("---")
st.markdown('<div class="section">🏆 Strike Ranking — Prototype Layout</div>', unsafe_allow_html=True)
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

ch1, ch2 = st.columns(2)
with ch1:
    st.markdown('<div class="section">Theta / Vega Trend</div>', unsafe_allow_html=True)
    st.line_chart({"Theta/Vega": [2.1, 2.3, 2.6, 2.8, 3.1, 3.0, 3.2, 3.4]})
with ch2:
    st.markdown('<div class="section">NIFTY / ATM Context</div>', unsafe_allow_html=True)
    st.line_chart({"NIFTY": [25120, 25135, 25150, 25142, 25170, 25188, 25195, 25200], "ATM": [25100, 25100, 25150, 25150, 25150, 25200, 25200, 25200]})

st.markdown("---")
st.markdown('<div class="section">🛡 Sample Portfolio</div>', unsafe_allow_html=True)
if position_enabled and position_type != "None":
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Structure", position_type)
    p2.metric("Quantity", str(quantity))
    p3.metric("Paper MTM", "+₹1,840")
    p4.metric("Risk", "Monitoring")
    st.info("This is a paper/research position monitor. It does not place orders with Dhan.")
else:
    st.info("Enable the paper position monitor from the left panel to track a sample strategy.")

st.markdown("---")
with st.expander("Research roadmap"):
    st.markdown(
        """
**Phase 1:** Connect Dhan 1-minute historical/live option data.

**Phase 2:** Calculate Greeks minute-by-minute for the actual strike of every contract.

**Phase 3:** Validate the regime engine and Theta/Vega thresholds on historical NIFTY data.

**Phase 4:** Rank strikes and select Iron Condor / Bull Put / Bear Call / other structures by regime.

**Phase 5:** Run a paper portfolio continuously and record entry, adjustment, exit, P&L and drawdown.

**Phase 6:** Backtest out-of-sample before considering any live execution layer.
        """
    )

st.caption(
    f"Mode: {'Live' if st.session_state.live_mode else 'Historical'} • Date: {hist_date:%d-%b-%Y} • "
    f"Requested universe: ATM−{strike_range}…ATM+{strike_range} • {timeframe} • {expiry}"
)
