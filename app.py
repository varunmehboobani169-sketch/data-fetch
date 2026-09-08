from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from dhan_data import DhanClient
from regime_engine import MarketInputs, classify

st.set_page_config(page_title="NIFTY Intraday Option Selling Engine", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container {max-width: 1550px; padding-top: 1rem; padding-bottom: 2rem;}
[data-testid="stSidebar"] {min-width: 330px; max-width: 360px;}
.hero {padding: 18px 20px; border: 1px solid rgba(128,128,128,.22); border-radius: 14px; margin-bottom: 16px;}
.small {font-size: .88rem; opacity: .78;}
.section {font-size: 1.05rem; font-weight: 700; margin: 10px 0 8px 0;}
</style>
""", unsafe_allow_html=True)

CLIENT_ID = "1113195747"

with st.sidebar:
    st.header("Engine Controls")
    atm_input = st.number_input("NIFTY Spot", min_value=1000.0, max_value=100000.0, value=23690.0, step=50.0, help="Enter the current NIFTY spot. No Dhan quote is used here.")
    atm = round(atm_input / 50) * 50
    expiry_mode = st.selectbox("Expiry", ["Nearest weekly", "Next weekly", "Select later"])
    strike_range = st.slider("Strike universe", 1, 20, 20)
    sides = st.multiselect("Option sides", ["CE", "PE"], default=["CE", "PE"])
    timeframe = st.selectbox("Timeframe", ["1 minute"], disabled=True)

    st.divider()
    st.subheader("Paper Position Monitor")
    position_enabled = st.toggle("Enable position monitor", value=False)
    position_type = st.selectbox("Position structure", ["None", "Iron Condor", "Bull Put Spread", "Bear Call Spread", "Short Strangle"], disabled=not position_enabled)
    quantity = st.number_input("Reference quantity", min_value=1, value=1, step=1, disabled=not position_enabled)

st.markdown("""
<div class="hero">
  <h1 style="margin-bottom:4px;">📈 NIFTY Intraday Option Selling Engine</h1>
  <div class="small">Basic regime-based preferred-strike selector • no option LTP dependency</div>
</div>
""", unsafe_allow_html=True)

proto = MarketInputs(trend_score=0.05, realized_vol_percentile=38, iv_percentile=72, iv_change=-0.35, theta_vega=0.34)
result = classify(proto)

c0, c1, c2, c3 = st.columns(4)
c0.metric("NIFTY Spot", f"₹{atm:,.0f}", "Manual input")
c1.metric("ATM", f"{atm:,.0f}")
c2.metric("Expiry", expiry_mode)
c3.metric("Mode", "Basic selector")

left, right = st.columns([1.55, 1])
with left:
    st.markdown('<div class="section">Selling Environment</div>', unsafe_allow_html=True)
    a, b, c, d = st.columns(4)
    a.metric("Theta / Vega", f"{proto.theta_vega:.2f}x", "Prototype")
    b.metric("IV Percentile", f"{proto.iv_percentile:.0f}%", "Prototype")
    c.metric("IV Change", f"{proto.iv_change:+.2f}", "Prototype")
    d.metric("Realized Vol", f"{proto.realized_vol_percentile:.0f}th pct", "Prototype")
    st.markdown("### 🎯 Selling Score")
    st.progress(result.selling_score / 100)
    s1, s2, s3 = st.columns(3)
    s1.metric("Score", f"{result.selling_score} / 100")
    s2.metric("Regime", result.regime)
    s3.metric("Action", result.action)
    st.markdown('<div class="section">Market Regime Decision Tree</div>', unsafe_allow_html=True)
    st.dataframe({"Engine": ["Trend", "Realized Vol", "IV", "Theta/Vega"], "Reading": ["Neutral / Sideways", f"{proto.realized_vol_percentile:.0f}th percentile", f"{proto.iv_percentile:.0f}% • {proto.iv_change:+.2f}", f"{proto.theta_vega:.2f}x"], "Interpretation": [result.regime, "Contained" if proto.realized_vol_percentile < 50 else "Elevated", "Falling" if proto.iv_change < 0 else "Rising", "Favorable" if proto.theta_vega >= 0.30 else "Selective"]}, use_container_width=True, hide_index=True)

with right:
    st.markdown('<div class="section">⚡ Strategy Selection</div>', unsafe_allow_html=True)
    if result.selling_score >= 80:
        st.success("CONDITIONS FAVOUR PREMIUM SELLING")
    elif result.selling_score >= 65:
        st.warning("SELECTIVE PREMIUM SELLING")
    else:
        st.error("AVOID NEW PREMIUM SELLING")
    st.write(f"**Preferred structure:** {result.preferred_strategy}")
    st.write("**Strike selection:** relative to manually entered NIFTY ATM")
    st.write("**Wings:** determined later by tested risk rules")
    st.divider()
    st.metric("Selling Score", f"{result.selling_score}/100")
    st.metric("Theta/Vega", f"{proto.theta_vega:.2f}x")
    st.caption("No option LTP is fetched or displayed.")
    st.markdown("**Why this decision?**")
    for reason in result.reasons:
        st.write(f"• {reason}")

st.markdown("---")
st.markdown('<div class="section">🏆 Preferred Strike Ranking</div>', unsafe_allow_html=True)

regime_name = result.regime.lower()
if "bull" in regime_name:
    preferred = [
        (1, "PE SELL", -2, "Primary bullish premium sell"),
        (2, "PE WING", -5, "Protective put wing"),
        (3, "CE SELL", 4, "Farther OTM call sell / secondary"),
    ]
elif "bear" in regime_name:
    preferred = [
        (1, "CE SELL", 2, "Primary bearish premium sell"),
        (2, "CE WING", 5, "Protective call wing"),
        (3, "PE SELL", -4, "Farther OTM put sell / secondary"),
    ]
else:
    preferred = [
        (1, "CE SELL", 3, "Primary neutral call sell"),
        (2, "PE SELL", -3, "Primary neutral put sell"),
        (3, "CE WING", 6, "Protective call wing"),
        (4, "PE WING", -6, "Protective put wing"),
    ]

ranking_rows = []
for rank, role, offset, reason in preferred:
    absolute = atm + offset * 50
    ranking_rows.append({
        "Rank": rank,
        "Role": role,
        "Relative Strike": f"ATM {offset:+d}",
        "Strike": f"{absolute:,.0f}",
        "Distance": f"{abs(offset) * 50:,.0f} points from ATM",
        "Reason": reason,
    })

st.dataframe(ranking_rows, use_container_width=True, hide_index=True, height=260)
st.caption("Strike Ranking uses only NIFTY Spot/ATM and the relative strike rule. No Dhan quote, option LTP, security ID, or instrument-master lookup is involved.")

ch1, ch2 = st.columns(2)
with ch1:
    st.markdown('<div class="section">Theta / Vega Trend</div>', unsafe_allow_html=True)
    st.line_chart({"Theta/Vega": [2.1, 2.3, 2.6, 2.8, 3.1, 3.0, 3.2, 3.4]})
with ch2:
    st.markdown('<div class="section">NIFTY / ATM Context</div>', unsafe_allow_html=True)
    series = [atm - 40, atm - 25, atm - 12, atm - 6, atm - 2, atm]
    st.line_chart({"NIFTY": series, "ATM": [round(x / 50) * 50 for x in series]})

st.markdown("---")
st.markdown('<div class="section">🛡 Sample Portfolio</div>', unsafe_allow_html=True)
if position_enabled and position_type != "None":
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Structure", position_type)
    p2.metric("Quantity", str(quantity))
    p3.metric("Paper MTM", "—")
    p4.metric("Risk", "Awaiting later Greek layer")
    st.info("This is a paper/research position monitor. It does not place orders with Dhan.")
else:
    st.info("Enable the paper position monitor from the left panel to track a sample strategy.")

st.markdown("---")
with st.expander("Research roadmap"):
    st.markdown("""
**Phase 1:** Basic regime-based strike selection.

**Phase 2:** Backtest ATM offsets and identify the best strike distance by regime.

**Phase 3:** Add Theta/Vega and IV gating without changing the strike-selector layer.

**Phase 4:** Run a paper portfolio and record entry, adjustment, exit, P&L and drawdown.
""")

st.caption(f"Mode: Basic selector • Date: {date.today():%d-%b-%Y} • Requested universe: ATM−{strike_range}…ATM+{strike_range} • {timeframe} • {expiry_mode}")
