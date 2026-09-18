# Project Friday Data Lab

Streamlit dashboard for Project Friday research. It includes the original NIFTY
backtest workspace and an MCX futures intraday collector through DhanHQ.

## MCX futures collector

The MCX workspace requests exact contract candles using Dhan's historical
intraday endpoint with `MCX_COMM` and `FUTCOM`. It supports 1, 5, 15, 25 and
60-minute bars, OI, 90-day request windows, throttling, resume-safe Parquet
storage and a downloadable manifest.

### Coverage boundary

The Dhan master fetched today lists *currently tradable* MCX futures. It does
not contain already-expired contracts from 2024–2026, so it cannot by itself
fulfil an "every historical contract" request. The dashboard accepts an
archived Dhan contract-master CSV with historical `SECURITY_ID` values. It will
then attempt the exact contracts, record empty/failing windows honestly, and
retain all successful data by contract and expiry.

Never commit Dhan tokens or collected data. The repository ignores `.env` and
`data/` by design.

## Original NIFTY weekly-options target dataset

- Date range: 1 January 2024 through the current date
- Expiry: NIFTY weekly
- Frequency: 1 minute
- Requested strike universe: ATM-20 through ATM+20
- Sides: CE and PE
- Fields: OHLC, volume, OI, IV, spot, strike, relative strike offset and mapped weekly expiry

## Dhan login

Enter the Dhan Client ID and Access Token in the left sidebar. Credentials are stored only in the active Streamlit session and are never committed to this repository.

## Important coverage note

Dhan's Expired Options Data API currently documents 1-minute rolling expired-option data for up to five years, including OHLC, IV, volume, OI and spot, with index options available from ATM-10 through ATM+10. The dashboard keeps ATM±20 as the requested target, but it does not fabricate ATM±11…ATM±20 values. An extended historical data adapter can be added later for those strikes.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Dhan API documentation: https://dhanhq.co/docs/v2/expired-options-data/

