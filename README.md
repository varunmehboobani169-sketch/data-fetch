# NIFTY Weekly Options Data Lab

Streamlit dashboard for fetching and exploring 1-minute historical NIFTY weekly-option data through DhanHQ.

## Target dataset

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
