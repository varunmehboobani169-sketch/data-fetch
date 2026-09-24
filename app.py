import csv
import io
import os
import zipfile
from datetime import date, datetime, timedelta

import requests
import streamlit as st

DHAN_BASE = "https://api.dhan.co/v2"
NIFTY_ID = 13
NIFTY_SEG = "IDX_I"

st.set_page_config(page_title="NIFTY Dhan Data Collector", page_icon="📈", layout="wide")
st.title("NIFTY Next-Week 1-Minute Option Data Collector")
st.caption("DhanHQ v2 · active weekly NIFTY options · CSV/ZIP export")

def next_week():
    today = date.today()
    days = (7 - today.weekday()) % 7 or 7
    monday = today + timedelta(days=days)
    return monday, monday + timedelta(days=4)

def post(path, payload, client_id, token):
    r = requests.post(
        DHAN_BASE + path,
        json=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "client-id": client_id,
            "access-token": token,
        },
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Dhan API {r.status_code}: {r.text[:500]}")
    data = r.json()
    if isinstance(data, dict) and data.get("status") == "failure":
        raise RuntimeError(str(data))
    return data

def choose_expiry(expiries, start_d, end_d):
    parsed = sorted(datetime.strptime(str(x), "%Y-%m-%d").date() for x in expiries)
    in_week = [d for d in parsed if start_d <= d <= end_d]
    if in_week:
        return in_week[0].isoformat()
    after = [d for d in parsed if d >= start_d]
    if after:
        return after[0].isoformat()
    raise RuntimeError("No suitable active NIFTY expiry found.")

def chain_contracts(chain, n):
    d = chain.get("data") or {}
    spot = float(d.get("last_price"))
    oc = d.get("oc") or {}
    if not oc:
        raise RuntimeError("Option chain returned no strikes.")
    strikes = sorted(float(k) for k in oc.keys())
    atm = min(strikes, key=lambda x: abs(x - spot))
    atm_i = strikes.index(atm)
    selected = strikes[max(0, atm_i-n): min(len(strikes), atm_i+n+1)]
    out = []
    for strike in selected:
        node = None
        for k, v in oc.items():
            if abs(float(k) - strike) < 1e-9:
                node = v
                break
        if not node:
            continue
        offset = strikes.index(strike) - atm_i
        for key, side in (("ce", "CE"), ("pe", "PE")):
            leg = node.get(key) or {}
            sec = leg.get("security_id")
            if sec is not None:
                out.append({
                    "strike": strike,
                    "option_type": side,
                    "security_id": int(sec),
                    "atm_offset": offset,
                })
    return out, spot, atm

def fetch_intraday(contract, start_d, end_d, client_id, token, include_oi):
    start_dt = datetime.combine(start_d, datetime.min.time()).replace(hour=9, minute=15)
    end_dt = datetime.combine(end_d, datetime.min.time()).replace(hour=15, minute=30)
    now = datetime.now()
    if start_dt > now:
        return []
    end_dt = min(end_dt, now)

    raw = post(
        "/charts/intraday",
        {
            "securityId": str(contract["security_id"]),
            "exchangeSegment": "NSE_FNO",
            "instrument": "OPTIDX",
            "interval": "1",
            "oi": bool(include_oi),
            "fromDate": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "toDate": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        },
        client_id,
        token,
    )
    ts = raw.get("timestamp") or []
    rows = []
    for i, epoch in enumerate(ts):
        rows.append({
            "security_id": contract["security_id"],
            "strike": contract["strike"],
            "option_type": contract["option_type"],
            "atm_offset": contract["atm_offset"],
            "timestamp": datetime.fromtimestamp(epoch).isoformat(sep=" "),
            "open": (raw.get("open") or [None]*len(ts))[i],
            "high": (raw.get("high") or [None]*len(ts))[i],
            "low": (raw.get("low") or [None]*len(ts))[i],
            "close": (raw.get("close") or [None]*len(ts))[i],
            "volume": (raw.get("volume") or [None]*len(ts))[i],
            "oi": (raw.get("oi") or [None]*len(ts))[i] if include_oi else None,
        })
    return rows

week_start, week_end = next_week()

with st.sidebar:
    st.header("Dhan connection")
    client_id = st.text_input("Client ID", value=os.getenv("DHAN_CLIENT_ID", ""))
    token = st.text_input("Access Token", value=os.getenv("DHAN_ACCESS_TOKEN", ""), type="password")
    st.caption("Credentials are used only for this running session.")

c1, c2, c3, c4 = st.columns(4)
with c1:
    start_d = st.date_input("Week start", value=week_start)
with c2:
    end_d = st.date_input("Week end", value=week_end)
with c3:
    strike_range = st.selectbox("Strike range", [5, 10, 20, 30], index=3, format_func=lambda x: f"ATM ±{x}")
with c4:
    include_oi = st.checkbox("Include OI", value=True)

if "contracts" not in st.session_state:
    st.session_state.contracts = []
if "expiry" not in st.session_state:
    st.session_state.expiry = None
if "spot" not in st.session_state:
    st.session_state.spot = None
if "atm" not in st.session_state:
    st.session_state.atm = None

st.subheader("1. Discover next-week NIFTY contracts")
if st.button("Connect & Load NIFTY Chain", type="primary", use_container_width=True):
    if not client_id or not token:
        st.error("Enter your Dhan Client ID and Access Token.")
    else:
        try:
            expiries = post(
                "/optionchain/expirylist",
                {"UnderlyingScrip": NIFTY_ID, "UnderlyingSeg": NIFTY_SEG},
                client_id,
                token,
            ).get("data", [])
            expiry = choose_expiry(expiries, start_d, end_d)
            chain = post(
                "/optionchain",
                {"UnderlyingScrip": NIFTY_ID, "UnderlyingSeg": NIFTY_SEG, "Expiry": expiry},
                client_id,
                token,
            )
            contracts, spot, atm = chain_contracts(chain, strike_range)
            st.session_state.contracts = contracts
            st.session_state.expiry = expiry
            st.session_state.spot = spot
            st.session_state.atm = atm
            st.success(f"Loaded {len(contracts)} contracts for expiry {expiry}.")
        except Exception as exc:
            st.exception(exc)

if st.session_state.expiry:
    a, b, c = st.columns(3)
    a.metric("Expiry", st.session_state.expiry)
    b.metric("NIFTY spot", f"{st.session_state.spot:,.2f}")
    c.metric("ATM", f"{st.session_state.atm:,.0f}")

    preview = st.session_state.contracts[:20]
    st.dataframe(preview, use_container_width=True)

st.subheader("2. Fetch 1-minute candles")
if date.today() < start_d:
    st.info("The selected week is still in the future. You can resolve contracts now, but 1-minute candles become available only after trading occurs.")

if st.button("Fetch 1-Minute Data", disabled=not bool(st.session_state.contracts), use_container_width=True):
    all_rows = []
    manifest = []
    progress = st.progress(0)
    total = len(st.session_state.contracts)
    for idx, contract in enumerate(st.session_state.contracts, start=1):
        try:
            rows = fetch_intraday(contract, start_d, end_d, client_id, token, include_oi)
            all_rows.extend(rows)
            manifest.append({**contract, "rows": len(rows), "status": "ok" if rows else "empty", "error": ""})
        except Exception as exc:
            manifest.append({**contract, "rows": 0, "status": "error", "error": str(exc)})
        progress.progress(idx / total)

    st.session_state.rows = all_rows
    st.session_state.manifest = manifest

if "manifest" in st.session_state:
    manifest = st.session_state.manifest
    rows = st.session_state.get("rows", [])

    ok = sum(1 for x in manifest if x["status"] == "ok")
    empty = sum(1 for x in manifest if x["status"] == "empty")
    errors = sum(1 for x in manifest if x["status"] == "error")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Contracts OK", ok)
    m2.metric("Empty", empty)
    m3.metric("Errors", errors)
    m4.metric("Total candles", len(rows))

    st.dataframe(manifest, use_container_width=True)

    if rows:
        st.subheader("Data preview")
        st.dataframe(rows[:1000], use_container_width=True)

        fields = list(rows[0].keys())
        csv_io = io.StringIO()
        writer = csv.DictWriter(csv_io, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        csv_bytes = csv_io.getvalue().encode()

        zip_io = io.BytesIO()
        with zipfile.ZipFile(zip_io, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("nifty_options_1m_combined.csv", csv_bytes)

            manifest_fields = list(manifest[0].keys())
            manifest_io = io.StringIO()
            mw = csv.DictWriter(manifest_io, fieldnames=manifest_fields)
            mw.writeheader()
            mw.writerows(manifest)
            zf.writestr("manifest.csv", manifest_io.getvalue().encode())

        d1, d2 = st.columns(2)
        d1.download_button("Download CSV", csv_bytes, "nifty_next_week_options_1m.csv", "text/csv", use_container_width=True)
        d2.download_button("Download ZIP", zip_io.getvalue(), "nifty_next_week_options_1m.zip", "application/zip", use_container_width=True)

st.markdown("---")
st.caption("Collector-only build. Uses DhanHQ v2 Option Chain, Expiry List and Intraday Historical APIs.")
