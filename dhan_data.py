from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

API = "https://api.dhan.co/v2"
MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
NIFTY_ID = "13"
IST = "Asia/Kolkata"
DATA_DIR = Path("data")


def _normalise_security_id(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.map(lambda x: str(int(x)) if pd.notna(x) and float(x).is_integer() else str(x).strip())


class DhanClient:
    def __init__(self, client_id: str, access_token: str):
        if not client_id.strip() or not access_token.strip():
            raise ValueError("Dhan Client ID and Access Token are required.")
        self.client_id = client_id.strip()
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
            "access-token": access_token.strip(),
            "client-id": self.client_id,
        })

    def post(self, path: str, payload: dict, retries: int = 2) -> dict:
        last: Exception | None = None
        for attempt in range(retries):
            try:
                r = self.session.post(f"{API}{path}", json=payload, timeout=30)
                r.raise_for_status()
                body = r.json()
                if isinstance(body, dict) and str(body.get("status", "")).lower() == "failure":
                    raise RuntimeError(str(body))
                return body
            except Exception as exc:
                last = exc
                if attempt + 1 < retries:
                    import time
                    time.sleep(1)
        raise last or RuntimeError("Dhan request failed")

    def expiry_list(self) -> list[str]:
        body = self.post("/optionchain/expirylist", {"UnderlyingScrip": int(NIFTY_ID), "UnderlyingSeg": "IDX_I"})
        values = (body.get("data") or []) if isinstance(body, dict) else []
        return [str(x) for x in values]

    def option_chain(self, expiry: str) -> dict:
        body = self.post("/optionchain", {"UnderlyingScrip": int(NIFTY_ID), "UnderlyingSeg": "IDX_I", "Expiry": expiry})
        return body.get("data") or {}


def fetch_instrument_master() -> pd.DataFrame:
    df = pd.read_csv(MASTER_URL, low_memory=False)
    aliases = {
        "SECURITY_ID": "SECURITY_ID",
        "SEM_SECURITY_ID": "SECURITY_ID",
        "UNDERLYING_SECURITY_ID": "UNDERLYING_SECURITY_ID",
        "SEM_UNDERLYING_SECURITY_ID": "UNDERLYING_SECURITY_ID",
        "SM_UNDERLYING_SECURITY_ID": "UNDERLYING_SECURITY_ID",
        "SEM_EXPIRY_DATE": "EXPIRY",
        "SM_EXPIRY_DATE": "EXPIRY",
        "EXPIRY_DATE": "EXPIRY",
        "STRIKE_PRICE": "STRIKE",
        "SEM_STRIKE_PRICE": "STRIKE",
        "OPTION_TYPE": "OPTION_TYPE",
        "SEM_OPTION_TYPE": "OPTION_TYPE",
        "SEM_OPTION_TYPE_NAME": "OPTION_TYPE",
    }
    rename = {col: aliases[str(col).upper().strip()] for col in df.columns if str(col).upper().strip() in aliases}
    df = df.rename(columns=rename)
    required = {"SECURITY_ID", "UNDERLYING_SECURITY_ID", "EXPIRY", "STRIKE", "OPTION_TYPE"}
    missing = required - set(df.columns)
    if missing:
        raise RuntimeError(f"Instrument master is missing: {sorted(missing)}")
    df["SECURITY_ID"] = _normalise_security_id(df["SECURITY_ID"])
    df["UNDERLYING_SECURITY_ID"] = _normalise_security_id(df["UNDERLYING_SECURITY_ID"])
    df["EXPIRY"] = pd.to_datetime(df["EXPIRY"], errors="coerce").dt.date
    df["STRIKE"] = pd.to_numeric(df["STRIKE"], errors="coerce")
    df["OPTION_TYPE"] = df["OPTION_TYPE"].astype(str).str.upper().str.strip()
    return df


def available_expiries(master: pd.DataFrame, start: date, end: date) -> list[date]:
    q = master[
        master["UNDERLYING_SECURITY_ID"].eq(NIFTY_ID)
        & master["OPTION_TYPE"].isin(["CE", "PE"])
        & master["EXPIRY"].notna()
    ]
    return sorted(x for x in q["EXPIRY"].dropna().unique().tolist() if start <= x <= end)


def nearest_weekly_expiry(master: pd.DataFrame, on_date: date) -> date | None:
    values = available_expiries(master, on_date, date.max)
    return values[0] if values else None


def expiry_for_session(ts: pd.Timestamp, expiries: list[date]) -> date | None:
    d = ts.date()
    future = [exp for exp in expiries if exp >= d]
    return min(future) if future else None


def strike_contracts(master: pd.DataFrame, expiry: date, strikes: list[float], sides: list[str]) -> pd.DataFrame:
    q = master[
        master["UNDERLYING_SECURITY_ID"].eq(NIFTY_ID)
        & master["EXPIRY"].eq(expiry)
        & master["OPTION_TYPE"].isin(sides)
        & master["STRIKE"].isin(strikes)
    ].copy()
    return q[["SECURITY_ID", "EXPIRY", "STRIKE", "OPTION_TYPE"]].drop_duplicates()


def rolling_call(client: DhanClient, start: date, end_exclusive: date, offset: int, side: str) -> pd.DataFrame:
    if abs(offset) > 10:
        return pd.DataFrame()
    payload = {
        "exchangeSegment": "NSE_FNO",
        "interval": "1",
        "securityId": NIFTY_ID,
        "instrument": "OPTIDX",
        "expiryFlag": "WEEK",
        "expiryCode": 1,
        "strike": "ATM" if offset == 0 else f"ATM{offset:+d}",
        "drvOptionType": "CALL" if side == "CE" else "PUT",
        "requiredData": ["open", "high", "low", "close", "iv", "volume", "oi", "spot", "strike"],
        "fromDate": start.isoformat(),
        "toDate": end_exclusive.isoformat(),
    }
    body = client.post("/charts/rollingoption", payload)
    block = (body.get("data") or {}).get("ce" if side == "CE" else "pe") or {}
    ts = block.get("timestamp") or []
    if not ts:
        return pd.DataFrame()
    n = len(ts)
    def arr(key: str):
        values = block.get(key)
        return values if isinstance(values, list) else [None] * n
    timestamp = pd.to_datetime(ts, unit="s", utc=True).dt.tz_convert(IST)
    return pd.DataFrame({"timestamp": timestamp, "open": arr("open"), "high": arr("high"), "low": arr("low"), "close": arr("close"), "volume": arr("volume"), "oi": arr("oi"), "iv": arr("iv"), "spot": arr("spot"), "strike": arr("strike"), "option_type": side, "strike_offset": offset, "moneyness": "ATM" if offset == 0 else f"ATM{offset:+d}"})


def chunks(start: date, end_exclusive: date, days: int = 30):
    cur = start
    while cur < end_exclusive:
        nxt = min(cur + timedelta(days=days), end_exclusive)
        yield cur, nxt
        cur = nxt


@dataclass
class FetchResult:
    frame: pd.DataFrame
    errors: list[str]


class HistoricalCollector:
    def __init__(self, client: DhanClient, data_dir: Path = DATA_DIR):
        self.client = client
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def fetch_range(self, start: date, end: date, strike_range: int, sides: list[str], progress: Callable[[int, int, str], None] | None = None) -> FetchResult:
        requested = min(max(strike_range, 1), 20)
        native = min(requested, 10)
        windows = list(chunks(start, end + timedelta(days=1), 30))
        jobs = [(a, b, offset, side) for a, b in windows for side in sides for offset in range(-native, native + 1)]
        total = len(jobs)
        done = 0
        errors: list[str] = []
        output_files: list[Path] = []
        master = fetch_instrument_master()
        expiries = available_expiries(master, start, end)
        for a, b, offset, side in jobs:
            path = self.data_dir / f"{a:%Y%m%d}_{b:%Y%m%d}_{side}_{offset:+d}.parquet"
            try:
                if path.exists() and path.stat().st_size > 0:
                    frame = pd.read_parquet(path)
                else:
                    frame = rolling_call(self.client, a, b, offset, side)
                    if not frame.empty:
                        frame["expiry"] = frame["timestamp"].map(lambda x: expiry_for_session(x, expiries))
                        frame.to_parquet(path, index=False)
                if path.exists():
                    output_files.append(path)
            except Exception as exc:
                errors.append(f"{a}→{b} {side} ATM{offset:+d}: {exc}")
            done += 1
            if progress:
                progress(done, total, f"Fetching {side} ATM{offset:+d} • {a:%d-%b-%Y} → {b:%d-%b-%Y} • {done}/{total}")
        frames = []
        for path in output_files:
            try:
                frames.append(pd.read_parquet(path))
            except Exception:
                pass
        if not frames:
            return FetchResult(pd.DataFrame(), errors)
        df = pd.concat(frames, ignore_index=True)
        df = df[(df["timestamp"].dt.date >= start) & (df["timestamp"].dt.date <= end)]
        df = df.drop_duplicates(["timestamp", "option_type", "strike_offset"]).sort_values(["timestamp", "option_type", "strike_offset"]).reset_index(drop=True)
        return FetchResult(df, errors)
