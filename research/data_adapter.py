from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

ALIASES = {
    "timestamp": ["timestamp", "datetime", "date_time", "time"],
    "spot": ["spot", "nifty", "underlying", "underlying_price"],
    "strike": ["strike", "strike_price"],
    "option_type": ["option_type", "optiontype", "type", "ce_pe"],
    "expiry": ["expiry", "expiry_date"],
    "open": ["open", "o"],
    "high": ["high", "h"],
    "low": ["low", "l"],
    "close": ["close", "ltp", "price", "c"],
    "iv": ["iv", "implied_volatility"],
    "oi": ["oi", "open_interest"],
    "volume": ["volume", "vol"],
}


def _find_column(columns: Iterable[str], candidates: list[str]) -> str | None:
    normalized = {str(c).strip().lower(): c for c in columns}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    return None


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    rename: dict[str, str] = {}
    for target, candidates in ALIASES.items():
        found = _find_column(frame.columns, candidates)
        if found is not None:
            rename[found] = target
    df = frame.rename(columns=rename).copy()

    required = {"timestamp", "spot", "strike", "option_type", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["spot"] = pd.to_numeric(df["spot"], errors="coerce")
    df["strike"] = pd.to_numeric(df["strike"], errors="coerce")
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["option_type"] = df["option_type"].astype(str).str.upper().str.strip()
    if "expiry" in df.columns:
        df["expiry"] = pd.to_datetime(df["expiry"], errors="coerce")
    for col in ["iv", "oi", "volume", "open", "high", "low"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["timestamp", "spot", "strike", "close"])
    df = df[df["option_type"].isin(["CE", "PE"])].copy()
    df = df.drop_duplicates().sort_values("timestamp").reset_index(drop=True)
    return df


def load_uploaded_files(paths: list[str | Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        p = Path(path)
        if p.suffix.lower() == ".parquet":
            raw = pd.read_parquet(p)
        elif p.suffix.lower() == ".csv":
            raw = pd.read_csv(p)
        else:
            raise ValueError(f"Unsupported file type: {p.name}")
        frames.append(normalize_frame(raw))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
