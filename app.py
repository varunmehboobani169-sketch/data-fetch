from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from dhan_data import DhanClient

st.set_page_config(page_title="NIFTY Option Selling", page_icon="📌", layout="centered")

CLIENT_ID = "1113195747"

st.markdown("""
<style>
.block-container {max-width: 950px; padding-top: 1.6rem;}
.big {font-size: 2.2rem; font-weight: 800; margin-bottom: .2rem;}
.sub {font-size: 1rem; opacity: .7; margin-bottom: 1.2rem;}
.pick {padding: 18px; border: 1px solid rgba(128,128,128,.25); border-radius: 14px; margin: 10px 0 14px;}
.label {font-size: .85rem; opacity: .65; margin-bottom: 4px;}
.value {font-size: 1.8rem; font-weight: 800;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="big">📌 NIFTY Option Selling</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">Simple answer: strategy, strike and Greeks</div>', unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
with c1:
    spot = st.number_input("NIFTY Spot", min_value=1000.0, max_value=100000.0, value=23690.0, step=50.0)
with c2:
    market = st.selectbox("Market", ["Sideways", "Mild Bullish", "Strong Bullish", "Mild Bearish", "Strong Bearish"])
with c3:
    expiry = st.date_input("Expiry", value=date.today() + timedelta(days=7))

atm = int(round(spot / 50) * 50)

plans = {
    "Sideways": {"strategy": "Iron Condor", "sell": [("PE", -3), ("CE", 3)], "wing": [(-6, "PE"), (6, "CE")], "note": "Sell both sides 150 points OTM."},
    "Mild Bullish": {"strategy": "Bull Put Spread", "sell": [("PE", -2)], "wing": [(-5, "PE")], "note": "Prefer the put side."},
    "Strong Bullish": {"strategy": "Bull Put Spread", "sell": [("PE", -2)], "wing": [(-5, "PE")], "note": "Prefer put-side selling; avoid aggressive call selling."},
    "Mild Bearish": {"strategy": "Bear Call Spread", "sell": [("CE", 2)], "wing": [(5, "CE")], "note": "Prefer the call side."},
    "Strong Bearish": {"strategy": "Bear Call Spread", "sell": [("CE", 2)], "wing": [(5, "CE")], "note": "Prefer call-side selling; avoid aggressive put selling."},
}
plan = plans[market]

st.markdown("---")
a, b = st.columns(2)
a.metric("ATM", f"{atm:,}")
b.metric("Suggested Strategy", plan["strategy"])

st.markdown("### ✅ Sell")
for side, offset in plan["sell"]:
    strike = atm + offset * 50
    st.markdown(f'<div class="pick"><div class="label">SELL</div><div class="value">{strike:,} {side}</div><div>{abs(offset) * 50} points OTM</div></div>', unsafe_allow_html=True)

if plan["wing"]:
    st.markdown("### 🛡 Hedge")
    wing_text = []
    for offset, side in plan["wing"]:
        wing_text.append(f"{atm + offset * 50:,} {side}")
    st.write(" / ".join(wing_text))

st.info(plan["note"])

st.markdown("### Greeks")
token = st.text_input("Dhan Access Token", type="password", help="Only used to fetch Greeks. Option LTP is never displayed.")

greek_rows = []
greek_error = ""
if token.strip():
    try:
        client = DhanClient(CLIENT_ID, token)
        chain = client.option_chain(expiry.isoformat())
        oc = chain.get("oc") or {}
        selected_offsets = sorted(set([x[1] for x in plan["sell"]] + [x[0] for x in plan["wing"]]))
        wanted = {float(atm + off * 50) for off in selected_offsets}
        for strike_text, payload in oc.items():
            strike = float(strike_text)
            if strike not in wanted:
                continue
            for side, key in [("CE", "ce"), ("PE", "pe")]:
                opt = payload.get(key) or {}
                g = opt.get("greeks") or {}
                if not g:
                    continue
                theta = float(g.get("theta", 0.0))
                vega = float(g.get("vega", 0.0))
                ratio = abs(theta) / vega if vega else 0.0
                greek_rows.append({
                    "Strike": f"{strike:,.0f}",
                    "Side": side,
                    "Delta": round(float(g.get("delta", 0.0)), 3),
                    "Theta": round(theta, 2),
                    "Vega": round(vega, 2),
                    "Theta/Vega": round(ratio, 3),
                })
    except Exception as exc:
        greek_error = str(exc)

if greek_error:
    st.warning(f"Greeks unavailable: {greek_error}")
elif greek_rows:
    st.dataframe(pd.DataFrame(greek_rows), use_container_width=True, hide_index=True)
else:
    st.caption("Enter a valid Dhan token to show Greeks. LTP is intentionally excluded.")

st.caption("The recommendation is intentionally simple: market condition → strategy → strike. Greeks are shown separately to evaluate the selected strikes.")
