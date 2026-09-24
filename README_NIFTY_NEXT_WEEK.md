# NIFTY Next-Week 1-Minute Option Downloader

A Streamlit UI for downloading **active NIFTY option contracts for next week** from **DhanHQ API v2**.

## What it does

- Defaults the date selector to **next Monday through Friday**.
- Uses Dhan's **Expiry List** endpoint to find the active NIFTY option expiry for that week.
- Uses **Option Chain** to get the live NIFTY spot, identify the nearest ATM strike and resolve real Dhan `security_id` values.
- Lets you choose **ATM ±5 / ±10 / ±20 / ±30** strikes.
- Downloads **1-minute** CE + PE candles from `/v2/charts/intraday`.
- Includes OHLC, volume and optional OI.
- Exports a combined CSV, combined Parquet, or a ZIP containing one CSV per contract plus a manifest.
- Shows empty/error contracts separately instead of silently dropping them.

## Important future-data limitation

The app can discover next week's active option contracts before the week begins, but it **cannot download future 1-minute candles before they exist**. Dhan's intraday historical API returns historical bars for active instruments. Re-run the app during or after the week to collect the available candles.

## Run

The repository already includes the required packages in `requirements.txt`.

```bash
pip install -r requirements.txt
streamlit run nifty_next_week_ui.py
```

You can either enter credentials in the Streamlit sidebar or expose them as environment variables:

```bash
set DHAN_CLIENT_ID=your_client_id
set DHAN_ACCESS_TOKEN=your_access_token
streamlit run nifty_next_week_ui.py
```

On macOS/Linux:

```bash
export DHAN_CLIENT_ID=your_client_id
export DHAN_ACCESS_TOKEN=your_access_token
streamlit run nifty_next_week_ui.py
```

`.env` files and collected CSV/Parquet data are already ignored by this repository. Never commit your Dhan access token.

## Dhan endpoints used

- `POST /v2/optionchain/expirylist`
- `POST /v2/optionchain`
- `POST /v2/charts/intraday`

Dhan documentation:

- Option Chain: https://dhanhq.co/docs/v2/option-chain/
- Historical / Intraday: https://dhanhq.co/docs/v2/historical-data/
- Instrument list: https://dhanhq.co/docs/v2/instruments/

## Notes

- Default NIFTY underlying security ID is `13`, kept editable in the UI.
- Options are requested as `NSE_FNO` / `OPTIDX` with interval `1`.
- For a full ATM ±30 universe, the app can resolve up to 61 strikes × 2 sides, subject to the strikes Dhan exposes for that expiry.
