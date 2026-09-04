import streamlit as st

from src.common.theme import apply_theme

st.set_page_config(page_title="Stock Intel & Health Scorecard", layout="wide")
apply_theme()

# st.navigation controls the sidebar explicitly — only the pages listed below
# appear (no separate "Home" entry auto-generated from this entry script).
# The app opens directly on Market Pulse.
pages = [
    st.Page("pages/1_Market_Pulse.py", title="Market Pulse", default=True),
    st.Page("pages/2_Trading_Scanner.py", title="Trading Scanner"),
    st.Page("pages/3_Health_Scorecard.py", title="Health Scorecard"),
]
st.navigation(pages).run()
