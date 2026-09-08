from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from dhan_data import DhanClient, HistoricalCollector
from theta_engine import compare_strategies

st.set_page_config(page_title="NIFTY Option Selling", page_icon="📌", layout="wide")

CLIENT_ID = "1113195747"
DATA_DIR = Path("data")

st.markdown("""
<style>
.block-container {max-width: 1200px; padding-top: 1.4rem;}
.big {font-size: 2.2rem; font-weight: 800; margin-bottom: .2rem;}
.sub {font-size: 1rem; opacity: .7; margin-bottom: 1.2rem;}
.pick {padding: 18px; border: 1px solid rgba(128,128,128,.25); border-radius: 14px; margin: 10px 0 14px;}
.label {font-size: .85rem; opacity: .65; margin-bottom: 4px;}
.value {font-size: 1.8rem; font-weight: 800;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="big">📌 NIFTY Option Selling</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">Strategy recommendation, Greeks and theta-first backtesting</div>', unsafe_allow_html=True)

tab1, tab2 = st.tabs(["Live Greeks", "Theta Backtest"])

with tab1:
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
        st.write(" / ".join(f"{atm + offset * 50:,} {side}" for offset, side in plan["wing"]))

    st.info(plan["note"])
    st.markdown("### Greeks")
    token = st.text_input("Dhan Access Token", type="password", help="Used only for the live option-chain request.")
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
                    greek_rows.append({"Strike": f"{strike:,.0f}", "Side": side, "Delta": round(float(g.get("delta", 0.0)), 3), "Theta": round(theta, 2), "Vega": round(vega, 2), "Theta/Vega": round(abs(theta) / vega, 3) if vega else 0.0})
        except Exception as exc:
            greek_error = str(exc)
    if greek_error:
        st.warning(f"Greeks unavailable: {greek_error}")
    elif greek_rows:
        st.dataframe(pd.DataFrame(greek_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("Enter a valid Dhan token to show Greeks.")

with tab2:
    st.markdown("### Theta Backtest Lab")
    st.caption("Theta is the primary strike-selection objective. Delta is used only as a safety boundary against excessive gamma exposure. The backtest uses information available at entry and actual option prices at exit.")

    b1, b2, b3 = st.columns(3)
    with b1:
        bt_start = st.date_input("Start date", value=date(2024, 1, 1), key="bt_start")
    with b2:
        bt_end = st.date_input("End date", value=date.today(), key="bt_end")
    with b3:
        bt_entry = st.time_input("Entry", value=pd.Timestamp("09:30").time(), key="bt_entry")
    b4, b5, b6 = st.columns(3)
    with b4:
        bt_exit = st.time_input("Exit", value=pd.Timestamp("15:15").time(), key="bt_exit")
    with b5:
        lot_size = st.number_input("Lot size", min_value=1, value=65, step=1)
    with b6:
        max_delta = st.number_input("Maximum absolute delta (risk filter)", min_value=0.20, max_value=0.70, value=0.50, step=0.05)

    st.markdown("#### Theta selection controls")
    c7, c8 = st.columns(2)
    with c7:
        min_delta = st.number_input("Minimum absolute delta (risk filter)", min_value=0.05, max_value=0.40, value=0.10, step=0.05)
    with c8:
        wing_distance = st.number_input("Iron Condor wing distance (50-point strikes)", min_value=1, max_value=10, value=4, step=1)
    st.info("The engine ranks eligible CE and PE contracts by theta income per hour relative to premium (theta efficiency). Delta does not choose the strike; it only limits the allowed risk range.")

    bt_token = st.text_input("Dhan Access Token for historical data", type="password", key="bt_token")
    fetch_col1, fetch_col2 = st.columns([1, 3])
    with fetch_col1:
        fetch_clicked = st.button("Fetch / refresh data", type="primary", use_container_width=True)
    with fetch_col2:
        st.caption("Historical collector stores 1-minute data in the app's data/ cache. The current rolling-option feed is limited to ATM±10 in this project.")

    if fetch_clicked:
        if bt_start > bt_end:
            st.error("Start date must be on or before end date.")
        elif min_delta >= max_delta:
            st.error("Minimum delta risk filter must be lower than the maximum.")
        elif not bt_token.strip():
            st.error("Enter the Dhan Access Token first.")
        else:
            try:
                client = DhanClient(CLIENT_ID, bt_token)
                collector = HistoricalCollector(client, DATA_DIR)
                progress = st.progress(0.0)
                status = st.empty()
                def cb(done, total, text):
                    progress.progress(done / max(total, 1))
                    status.write(text)
                result = collector.fetch_range(bt_start, bt_end, strike_range=10, sides=["CE", "PE"], progress=cb)
                st.session_state["theta_df"] = result.frame
                if result.errors:
                    st.warning(f"Loaded data with {len(result.errors)} fetch errors. Existing cached files were retained where possible.")
                else:
                    st.success(f"Loaded {len(result.frame):,} one-minute option rows.")
            except Exception as exc:
                st.error(f"Historical data fetch failed: {exc}")

    if "theta_df" in st.session_state and not st.session_state["theta_df"].empty:
        data = st.session_state["theta_df"]
        mask = (data["timestamp"].dt.date >= bt_start) & (data["timestamp"].dt.date <= bt_end)
        data = data.loc[mask].copy()
        if data.empty:
            st.warning("No cached rows exist inside the selected date range.")
        else:
            if st.button("Run theta comparison", type="secondary", use_container_width=True):
                with st.spinner("Running theta-first strategies..."):
                    comparison, details = compare_strategies(
                        data,
                        entry_time=bt_entry.strftime("%H:%M"),
                        exit_time=bt_exit.strftime("%H:%M"),
                        min_abs_delta=float(min_delta),
                        max_abs_delta=float(max_delta),
                        wing_distance=int(wing_distance),
                        lot_size=int(lot_size),
                    )
                st.session_state["theta_comparison"] = comparison
                st.session_state["theta_details"] = details

    comparison = st.session_state.get("theta_comparison")
    if isinstance(comparison, pd.DataFrame) and not comparison.empty:
        view = comparison.copy()
        display_view = view.copy()
        display_view["win_rate"] = display_view["win_rate"].map(lambda x: f"{x:.1f}%")
        for col in ["net_pnl", "avg_day", "max_drawdown", "best_day", "worst_day"]:
            display_view[col] = display_view[col].map(lambda x: f"₹{x:,.0f}")
        display_view["profit_factor"] = display_view["profit_factor"].map(lambda x: f"{x:.2f}" if pd.notna(x) else "—")
        st.markdown("#### Strategy comparison")
        st.dataframe(display_view, use_container_width=True, hide_index=True)

        st.download_button("Download P&L Summary CSV", view.to_csv(index=False), file_name="theta_pnl_summary.csv", mime="text/csv", use_container_width=True)

        details = st.session_state.get("theta_details", {})
        names = [n for n in view["Strategy"] if n in details and not details[n].empty]
        if names:
            selected = st.selectbox("Equity curve / trade report", names)
            d = details[selected].copy()
            fig = px.line(d, x="date", y="cum_pnl_rupees", title=selected)
            fig.update_yaxes(title="Cumulative P&L (₹)")
            fig.update_xaxes(title="Date")
            st.plotly_chart(fig, use_container_width=True)

            st.download_button("Download Detailed Trade P&L CSV", d.to_csv(index=False), file_name=f"theta_{selected.lower().replace(' ', '_')}_trades.csv", mime="text/csv", use_container_width=True)

            st.markdown("#### Detailed P&L")
            st.dataframe(d, use_container_width=True, hide_index=True)
    else:
        st.info("Fetch or load historical option data, then run the theta comparison.")
