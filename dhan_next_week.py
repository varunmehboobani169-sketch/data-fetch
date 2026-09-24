from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta
from typing import Iterable

import pandas as pd
import requests

DHAN_BASE_URL = "https://api.dhan.co/v2"
NIFTY_UNDERLYING_SECURITY_ID = 13
NIFTY_UNDERLYING_SEGMENT = "IDX_I"
OPTION_EXCHANGE_SEGMENT = "NSE_FNO"
OPTION_INSTRUMENT = "OPTIDX"


class DhanAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class OptionContract:
    expiry: str
    strike: float
    side: str
    security_id: int
    offset: int


def next_week_window(anchor: date | None = None) -> tuple[date, date]:
    """Return next calendar Monday-Friday window after the anchor date."""
    anchor = anchor or date.today()
    days_until_monday = (7 - anchor.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    monday = anchor + timedelta(days=days_until_monday)
    friday = monday + timedelta(days=4)
    return monday, friday


def clamp_end_to_now(start: datetime, end: datetime) -> datetime:
    """Historical API cannot return future bars; cap end at current local time."""
    now = datetime.now()
    if start > now:
        return start
    return min(end, now)


class DhanClient:
    def __init__(self, client_id: str, access_token: str, timeout: int = 30):
        self.client_id = client_id.strip()
        self.access_token = access_token.strip()
        self.timeout = timeout
        if not self.client_id or not self.access_token:
            raise ValueError("Both Dhan Client ID and Access Token are required.")

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "access-token": self.access_token,
            "client-id": self.client_id,
        }

    def _post(self, path: str, payload: dict) -> dict:
        response = requests.post(
            f"{DHAN_BASE_URL}{path}",
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        if not response.ok:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise DhanAPIError(f"Dhan API {response.status_code}: {detail}")
        data = response.json()
        if isinstance(data, dict) and data.get("status") == "failure":
            raise DhanAPIError(str(data))
        return data

    def expiry_list(
        self,
        underlying_security_id: int = NIFTY_UNDERLYING_SECURITY_ID,
        underlying_segment: str = NIFTY_UNDERLYING_SEGMENT,
    ) -> list[str]:
        payload = {
            "UnderlyingScrip": int(underlying_security_id),
            "UnderlyingSeg": underlying_segment,
        }
        data = self._post("/optionchain/expirylist", payload)
        expiries = data.get("data", [])
        return [str(x) for x in expiries]

    def option_chain(
        self,
        expiry: str,
        underlying_security_id: int = NIFTY_UNDERLYING_SECURITY_ID,
        underlying_segment: str = NIFTY_UNDERLYING_SEGMENT,
    ) -> dict:
        payload = {
            "UnderlyingScrip": int(underlying_security_id),
            "UnderlyingSeg": underlying_segment,
            "Expiry": expiry,
        }
        return self._post("/optionchain", payload)

    def intraday(
        self,
        security_id: int,
        start: datetime,
        end: datetime,
        include_oi: bool = True,
        interval: str = "1",
    ) -> pd.DataFrame:
        payload = {
            "securityId": str(security_id),
            "exchangeSegment": OPTION_EXCHANGE_SEGMENT,
            "instrument": OPTION_INSTRUMENT,
            "interval": str(interval),
            "oi": bool(include_oi),
            "fromDate": start.strftime("%Y-%m-%d %H:%M:%S"),
            "toDate": end.strftime("%Y-%m-%d %H:%M:%S"),
        }
        raw = self._post("/charts/intraday", payload)
        return intraday_response_to_frame(raw)


def choose_expiry_for_week(expiries: Iterable[str], week_start: date, week_end: date) -> str:
    parsed = sorted(datetime.strptime(x, "%Y-%m-%d").date() for x in expiries)
    in_week = [d for d in parsed if week_start <= d <= week_end]
    if in_week:
        return in_week[0].isoformat()
    after_start = [d for d in parsed if d >= week_start]
    if after_start:
        return after_start[0].isoformat()
    raise DhanAPIError("No active NIFTY option expiry found for or after the selected week.")


def contracts_from_chain(chain_response: dict, strikes_each_side: int = 30) -> tuple[list[OptionContract], float, float]:
    data = chain_response.get("data") or {}
    spot = float(data.get("last_price"))
    oc = data.get("oc") or {}
    if not oc:
        raise DhanAPIError("Option chain returned no strikes.")

    strike_values = sorted(float(k) for k in oc.keys())
    atm = min(strike_values, key=lambda x: abs(x - spot))
    atm_idx = strike_values.index(atm)
    lo = max(0, atm_idx - strikes_each_side)
    hi = min(len(strike_values), atm_idx + strikes_each_side + 1)
    selected = strike_values[lo:hi]

    contracts: list[OptionContract] = []
    expiry = str(data.get("expiry") or chain_response.get("expiry") or "")
    for strike in selected:
        node = oc.get(f"{strike:.6f}") or oc.get(str(strike)) or oc.get(f"{strike}")
        if node is None:
            for k, v in oc.items():
                if abs(float(k) - strike) < 1e-9:
                    node = v
                    break
        if not node:
            continue
        offset = strike_values.index(strike) - atm_idx
        for side_key, side in (("ce", "CE"), ("pe", "PE")):
            leg = node.get(side_key) or {}
            sec = leg.get("security_id")
            if sec is None:
                continue
            contracts.append(
                OptionContract(
                    expiry=expiry,
                    strike=strike,
                    side=side,
                    security_id=int(sec),
                    offset=offset,
                )
            )
    return contracts, spot, atm


def intraday_response_to_frame(raw: dict) -> pd.DataFrame:
    keys = ["timestamp", "open", "high", "low", "close", "volume", "oi"]
    lengths = [len(raw.get(k, [])) for k in keys if raw.get(k) is not None]
    n = max(lengths, default=0)
    if n == 0:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume", "oi"])

    def col(name: str, fill=None):
        values = raw.get(name)
        if values is None:
            return [fill] * n
        values = list(values)
        if len(values) < n:
            values += [fill] * (n - len(values))
        return values[:n]

    frame = pd.DataFrame({k: col(k) for k in keys})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
    return frame


def fetch_contracts(
    client: DhanClient,
    contracts: Iterable[OptionContract],
    start_date: date,
    end_date: date,
    include_oi: bool = True,
    pause_seconds: float = 0.05,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    start_dt = datetime.combine(start_date, dtime(9, 15))
    requested_end = datetime.combine(end_date, dtime(15, 30))
    end_dt = clamp_end_to_now(start_dt, requested_end)

    rows: list[pd.DataFrame] = []
    manifest: list[dict] = []

    if start_dt > datetime.now():
        return pd.DataFrame(), pd.DataFrame([
            {
                "status": "future_window",
                "message": "The selected week has not started yet. Re-run during or after the week to fetch 1-minute candles.",
            }
        ])

    for contract in contracts:
        try:
            frame = client.intraday(contract.security_id, start_dt, end_dt, include_oi=include_oi)
            if not frame.empty:
                frame.insert(0, "security_id", contract.security_id)
                frame.insert(1, "expiry", contract.expiry)
                frame.insert(2, "strike", contract.strike)
                frame.insert(3, "option_type", contract.side)
                frame.insert(4, "atm_offset", contract.offset)
                rows.append(frame)
            manifest.append(
                {
                    "security_id": contract.security_id,
                    "expiry": contract.expiry,
                    "strike": contract.strike,
                    "option_type": contract.side,
                    "atm_offset": contract.offset,
                    "rows": int(len(frame)),
                    "status": "ok" if len(frame) else "empty",
                    "error": "",
                }
            )
        except Exception as exc:
            manifest.append(
                {
                    "security_id": contract.security_id,
                    "expiry": contract.expiry,
                    "strike": contract.strike,
                    "option_type": contract.side,
                    "atm_offset": contract.offset,
                    "rows": 0,
                    "status": "error",
                    "error": str(exc),
                }
            )
        if pause_seconds:
            time.sleep(pause_seconds)

    combined = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    manifest_df = pd.DataFrame(manifest)
    return combined, manifest_df
