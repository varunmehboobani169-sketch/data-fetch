from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="NIFTY Strike Selector", page_icon="📌", layout="centered")

st.markdown("""
<style>
.block-container {max-width: 900px; padding-top: 2rem;}
.big {font-size: 2.2rem; font-weight: 800; margin-bottom: .2rem;}
.sub {font-size: 1rem; opacity: .7; margin-bottom: 1.5rem;}
.pick {padding: 18px; border: 1px solid rgba(128,128,128,.25); border-radius: 14px; margin: 10px 0;}
.label {font-size: .9rem; opacity: .65; margin-bottom: 4px;}
.value {font-size: 1.8rem; font-weight: 800;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="big">📌 NIFTY Strike Selector</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">Simple answer: which strike should I sell?</div>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    spot = st.number_input("NIFTY Spot", min_value=1000.0, max_value=100000.0, value=23690.0, step=50.0)
with c2:
    market = st.selectbox("Market", ["Sideways", "Mild Bullish", "Strong Bullish", "Mild Bearish", "Strong Bearish"])

atm = int(round(spot / 50) * 50)

plans = {
    "Sideways": {
        "strategy": "Iron Condor",
        "ce_sell": 3,
        "pe_sell": -3,
        "ce_wing": 6,
        "pe_wing": -6,
        "message": "Sell both sides around 150 points from ATM."
    },
    "Mild Bullish": {
        "strategy": "Bull Put Spread",
        "ce_sell": 4,
        "pe_sell": -2,
        "ce_wing": 7,
        "pe_wing": -5,
        "message": "Prefer the put side; keep the call side farther away."
    },
    "Strong Bullish": {
        "strategy": "Bull Put Spread",
        "ce_sell": 5,
        "pe_sell": -2,
        "ce_wing": 8,
        "pe_wing": -5,
        "message": "Prefer put-side selling; avoid aggressive call selling."
    },
    "Mild Bearish": {
        "strategy": "Bear Call Spread",
        "ce_sell": 2,
        "pe_sell": -4,
        "ce_wing": 5,
        "pe_wing": -7,
        "message": "Prefer the call side; keep the put side farther away."
    },
    "Strong Bearish": {
        "strategy": "Bear Call Spread",
        "ce_sell": 2,
        "pe_sell": -5,
        "ce_wing": 5,
        "pe_wing": -8,
        "message": "Prefer call-side selling; avoid aggressive put selling."
    },
}

plan = plans[market]

st.markdown("---")
a, b = st.columns(2)
a.metric("NIFTY ATM", f"{atm:,}")
b.metric("Strategy", plan["strategy"])

st.markdown("### Preferred Sells")

ce_sell = atm + plan["ce_sell"] * 50
pe_sell = atm + plan["pe_sell"] * 50
ce_wing = atm + plan["ce_wing"] * 50
pe_wing = atm + plan["pe_wing"] * 50

if market in {"Strong Bullish", "Mild Bullish"}:
    st.markdown(f'<div class="pick"><div class="label">PRIMARY SELL</div><div class="value">{pe_sell:,} PE</div><div>{abs(plan["pe_sell"]) * 50} points OTM • {plan["message"]}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="pick"><div class="label">PROTECTIVE WING</div><div class="value">{pe_wing:,} PE</div></div>', unsafe_allow_html=True)
    st.info(f"Secondary call reference: {ce_sell:,} CE")
elif market in {"Strong Bearish", "Mild Bearish"}:
    st.markdown(f'<div class="pick"><div class="label">PRIMARY SELL</div><div class="value">{ce_sell:,} CE</div><div>{abs(plan["ce_sell"]) * 50} points OTM • {plan["message"]}</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="pick"><div class="label">PROTECTIVE WING</div><div class="value">{ce_wing:,} CE</div></div>', unsafe_allow_html=True)
    st.info(f"Secondary put reference: {pe_sell:,} PE")
else:
    st.markdown(f'<div class="pick"><div class="label">CALL SELL</div><div class="value">{ce_sell:,} CE</div><div>{abs(plan["ce_sell"]) * 50} points OTM</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="pick"><div class="label">PUT SELL</div><div class="value">{pe_sell:,} PE</div><div>{abs(plan["pe_sell"]) * 50} points OTM</div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="pick"><div class="label">WINGS</div><div class="value">{pe_wing:,} PE / {ce_wing:,} CE</div></div>', unsafe_allow_html=True)
    st.success(plan["message"])

st.caption("This is the basic strike rule only. No option LTP, Dhan quote, Greeks, charts, or instrument lookup is used here.")
