# NIFTY Next-Week 1-Minute Option Data Collector

A focused Streamlit data collector for **DhanHQ API v2**.

This repository now contains only the code required to discover next-week NIFTY option contracts and download their **1-minute OHLC, volume and OI data**.

## Files

- `app.py` — Streamlit Cloud / local entrypoint
- `nifty_next_week_ui.py` — Streamlit user interface
- `dhan_next_week.py` — DhanHQ API integration and data collection logic
- `requirements.txt` — Python dependencies
- `.gitignore` — keeps credentials and downloaded market data out of GitHub

## Features

- Defaults to next Monday-Friday.
- Finds the relevant active NIFTY expiry through DhanHQ.
- Reads the option chain and identifies ATM automatically.
- Supports ATM ±5, ±10, ±20 and ±30 strikes.
- Resolves actual CE/PE Dhan security IDs automatically.
- Downloads 1-minute candles.
- Includes optional open interest.
- Exports combined CSV, Parquet, and ZIP files split by contract.
- Produces a manifest showing successful, empty, and failed contracts.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Enter your Dhan Client ID and Access Token in the sidebar.

You can also set environment variables:

Windows:

```bat
set DHAN_CLIENT_ID=your_client_id
set DHAN_ACCESS_TOKEN=your_access_token
streamlit run nifty_next_week_ui.py
```

macOS/Linux:

```bash
export DHAN_CLIENT_ID=your_client_id
export DHAN_ACCESS_TOKEN=your_access_token
streamlit run nifty_next_week_ui.py
```

## Important

Do not commit your Dhan token or downloaded market data. The repository ignores `.env`, `data/`, CSV, and Parquet files.

The collector can identify next week's active contracts before trading begins, but **future 1-minute candles do not exist yet**. Run the collector during or after the trading week to retrieve candles that have already been generated.

## DhanHQ v2 endpoints used

- `POST /v2/optionchain/expirylist`
- `POST /v2/optionchain`
- `POST /v2/charts/intraday`

Documentation:

- https://dhanhq.co/docs/v2/option-chain/
- https://dhanhq.co/docs/v2/historical-data/
