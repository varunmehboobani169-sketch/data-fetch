import streamlit as st

try:
    import nifty_next_week_ui  # noqa: F401
except Exception as exc:
    st.set_page_config(page_title="NIFTY Dhan Collector", layout="wide")
    st.title("NIFTY Dhan Collector")
    st.error("The collector failed to start.")
    st.exception(exc)
    st.info("Copy the error shown above and send it here if the app still does not load.")
