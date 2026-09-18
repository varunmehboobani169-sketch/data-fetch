"""MCX futures intraday collection through Dhan's historical-candle API.

This module deliberately keeps the contract registry separate from the candle
collector.  Dhan's live scrip master can identify contracts that are currently
tradable, but it is not an archival registry of every already-expired contract.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from dhan_data import DATA_DIR, DhanClient, IST, fetch_instrument_master


MCX_SEGMENT = "MCX_COMM"
MCX_INSTRUMENT = "FUTCOM"
INTRADAY_ENDPOINT = "/charts/intraday"
SUPPORTED_INTERVALS = ("1", "5", "15", "25", "60")
MAX_DAYS_PER_REQUEST = 90


def _security_id(value: object) -> str:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.notna(numeric) and float(numeric).is_integer():
        return str(int(numeric))
    return str(value).strip()


def _find_column(frame: pd.DataFrame, *names: str) -> str | None:
    lookup = {str(column).upper().strip(): str(column) for column in frame.columns}
    for name in names:
        if name in lookup:
            return lookup[name]
    return None


def normalise_mcx_registry(frame: pd.DataFrame) -> pd.DataFrame:
    """Return the minimum contract registry needed for Dhan historical calls."""
    security = _find_column(frame, "SECURITY_ID", "SEM_SECURITY_ID")
    symbol = _find_column(frame, "UNDERLYING_SYMBOL", "SYMBOL_NAME", "DISPLAY_NAME")
    expiry = _find_column(frame, "SM_EXPIRY_DATE", "SEM_EXPIRY_DATE", "EXPIRY_DATE", "EXPIRY")
    exchange = _find_column(frame, "EXCH_ID", "EXCHANGE")
    instrument = _find_column(frame, "INSTRUMENT", "SEM_INSTRUMENT_NAME")

    if security is None or symbol is None:
        raise ValueError("Contract registry needs SECURITY_ID and UNDERLYING_SYMBOL (or SYMBOL_NAME).")

    result = pd.DataFrame(
        {
            "security_id": frame[security].map(_security_id),
            "symbol": frame[symbol].astype(str).str.upper().str.strip(),
            "expiry": pd.to_datetime(frame[expiry], errors="coerce").dt.date if expiry else pd.NaT,
            "exchange": frame[exchange].astype(str).str.upper().str.strip() if exchange else "MCX",
            "instrument": frame[instrument].astype(str).str.upper().str.strip() if instrument else "FUTCOM",
        }
    )
    result = result[
        result["security_id"].ne("")
        & result["symbol"].ne("")
        & result["exchange"].isin({"MCX", "MCX_COMM"})
        & result["instrument"].eq("FUTCOM")
    ]
    return result.drop_duplicates(["security_id"]).sort_values(["symbol", "expiry", "security_id"]).reset_index(drop=True)


def live_mcx_futures_master() -> pd.DataFrame:
    """Fetch the current Dhan master, filtered to currently listed MCX futures."""
    return normalise_mcx_registry(fetch_instrument_master())


def intraday_windows(start: date, end: date, days: int = MAX_DAYS_PER_REQUEST) -> Iterable[tuple[date, date]]:
    """Yield inclusive intervals no wider than Dhan's documented 90-day limit."""
    current = start
    while current <= end:
        window_end = min(current + timedelta(days=days - 1), end)
        yield current, window_end
        current = window_end + timedelta(days=1)


def _array(block: dict, key: str, length: int) -> list[object]:
    values = block.get(key)
    return values if isinstance(values, list) and len(values) == length else [None] * length


def intraday_call(
    client: DhanClient,
    security_id: str,
    start: date,
    end: date,
    interval: str,
) -> pd.DataFrame:
    """Request one exact MCX futures contract and return normalized candles."""
    if interval not in SUPPORTED_INTERVALS:
        raise ValueError(f"Unsupported interval {interval}; use one of {SUPPORTED_INTERVALS}.")
    payload = {
        "securityId": str(security_id),
        "exchangeSegment": MCX_SEGMENT,
        "instrument": MCX_INSTRUMENT,
        "interval": interval,
        "oi": True,
        "fromDate": f"{start.isoformat()} 00:00:00",
        "toDate": f"{(end + timedelta(days=1)).isoformat()} 00:00:00",
    }
    body = client.post(INTRADAY_ENDPOINT, payload)
    block = body.get("data", body) if isinstance(body, dict) else {}
    if not isinstance(block, dict):
        return pd.DataFrame()
    timestamps = block.get("timestamp") or []
    if not timestamps:
        return pd.DataFrame()
    n = len(timestamps)
    output = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(timestamps, unit="s", utc=True).tz_convert(IST),
            "open": _array(block, "open", n),
            "high": _array(block, "high", n),
            "low": _array(block, "low", n),
            "close": _array(block, "close", n),
            "volume": _array(block, "volume", n),
            "open_interest": _array(block, "open_interest", n),
        }
    )
    for column in ("open", "high", "low", "close", "volume", "open_interest"):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return output.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


def _safe_name(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("_") or "unknown"


@dataclass
class CollectionResult:
    manifest: pd.DataFrame
    errors: list[str]
    output_dir: Path


class MCXIntradayCollector:
    """Resumable, throttled 90-day collector for contract-specific MCX bars."""

    def __init__(self, client: DhanClient, data_dir: Path = DATA_DIR / "mcx_intraday"):
        self.client = client
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def collect(
        self,
        contracts: pd.DataFrame,
        start: date,
        end: date,
        interval: str,
        overwrite: bool = False,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> CollectionResult:
        contracts = normalise_mcx_registry(contracts)
        jobs = [(row, a, b) for _, row in contracts.iterrows() for a, b in intraday_windows(start, end)]
        total = len(jobs)
        manifest_rows: list[dict[str, object]] = []
        errors: list[str] = []

        for position, (contract, window_start, window_end) in enumerate(jobs, start=1):
            expiry_label = contract["expiry"].isoformat() if pd.notna(contract["expiry"]) else "unknown-expiry"
            folder = self.data_dir / _safe_name(contract["symbol"]) / f"{contract['security_id']}_{expiry_label}" / f"interval_{interval}m"
            folder.mkdir(parents=True, exist_ok=True)
            output = folder / f"{window_start.isoformat()}__{window_end.isoformat()}.parquet"
            status = "cached"
            rows = 0
            detail = ""
            try:
                if output.exists() and not overwrite:
                    rows = len(pd.read_parquet(output, columns=["timestamp"]))
                else:
                    frame = intraday_call(self.client, str(contract["security_id"]), window_start, window_end, interval)
                    rows = len(frame)
                    if not frame.empty:
                        frame["security_id"] = str(contract["security_id"])
                        frame["symbol"] = contract["symbol"]
                        frame["expiry"] = expiry_label
                        frame["exchange_segment"] = MCX_SEGMENT
                        frame["instrument"] = MCX_INSTRUMENT
                        frame.to_parquet(output, index=False)
                        status = "saved"
                    else:
                        status = "empty"
            except Exception as exc:
                status = "error"
                detail = str(exc)
                errors.append(f"{contract['symbol']} ({contract['security_id']}) {window_start} to {window_end}: {exc}")
            manifest_rows.append(
                {
                    "symbol": contract["symbol"],
                    "security_id": str(contract["security_id"]),
                    "expiry": expiry_label,
                    "interval_minutes": interval,
                    "from_date": window_start.isoformat(),
                    "to_date": window_end.isoformat(),
                    "status": status,
                    "rows": rows,
                    "path": str(output),
                    "detail": detail,
                }
            )
            if progress:
                progress(position, total, f"{contract['symbol']} · {window_start:%d-%b-%Y} to {window_end:%d-%b-%Y} · {position}/{total}")
            # Dhan documents a five-requests-per-second data API limit.  Keep a
            # conservative gap so a long resumable run does not hammer the API.
            if position < total:
                time.sleep(0.23)

        manifest = pd.DataFrame(manifest_rows)
        manifest.to_csv(self.data_dir / "collection_manifest.csv", index=False)
        return CollectionResult(manifest=manifest, errors=errors, output_dir=self.data_dir)

