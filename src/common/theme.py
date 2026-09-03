"""
App-wide visual theme: warm-sunset gradient, glassmorphism cards, editorial
typography. One function, called once at the top of every page, so all 3
pages stay visually identical (same rule as the shared chart component).
"""
from __future__ import annotations

import streamlit as st

# Sunset palette — peach -> coral -> dusty rose -> burgundy -> plum -> near-black purple
PEACH = "#F2A36B"
ROSE = "#E9B8B7"
BURGUNDY = "#A34054"
PLUM = "#662249"
DEEP_PLUM = "#44174E"
INK = "#1B1931"
OFF_WHITE = "#F7F1EC"

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Fraunces:opsz,wght@9..144,500;9..144,600&display=swap');

:root {{
  --peach: {PEACH};
  --rose: {ROSE};
  --burgundy: {BURGUNDY};
  --plum: {PLUM};
  --deep-plum: {DEEP_PLUM};
  --ink: {INK};
  --off-white: {OFF_WHITE};
}}

html, body, [class*="css"] {{
  font-family: 'Plus Jakarta Sans', -apple-system, sans-serif;
}}

.stApp {{
  background: linear-gradient(165deg,
    {PEACH} 0%,
    {ROSE} 22%,
    {BURGUNDY} 48%,
    {PLUM} 68%,
    {DEEP_PLUM} 85%,
    {INK} 100%);
  background-attachment: fixed;
  color: {OFF_WHITE};
}}

/* headings — editorial serif for a premium/lifestyle feel */
h1, h2, h3 {{
  font-family: 'Fraunces', 'Plus Jakarta Sans', serif;
  color: {OFF_WHITE} !important;
  letter-spacing: 0.2px;
}}
h1 {{ font-weight: 600 !important; }}

p, span, label, li, .stMarkdown, .stCaption, div[data-testid="stMetricLabel"] {{
  color: {OFF_WHITE} !important;
}}

/* sidebar — frosted glass panel */
[data-testid="stSidebar"] > div:first-child {{
  background: rgba(27, 25, 49, 0.55);
  backdrop-filter: blur(22px);
  -webkit-backdrop-filter: blur(22px);
  border-right: 1px solid rgba(247, 241, 236, 0.10);
}}
[data-testid="stSidebar"] * {{ color: {OFF_WHITE} !important; }}

/* header bar transparent so gradient shows through */
[data-testid="stHeader"] {{
  background: transparent;
}}

/* generous spacing, calm rhythm */
.block-container {{
  padding-top: 2.4rem;
  padding-bottom: 3rem;
  max-width: 1200px;
}}

/* --- glass cards: metrics, expanders, dataframes, containers --- */
div[data-testid="stMetric"] {{
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 20px;
  padding: 1.1rem 1.3rem;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 8px 32px rgba(27, 25, 49, 0.25);
}}
div[data-testid="stMetricValue"] {{
  color: {OFF_WHITE} !important;
  font-family: 'Fraunces', serif;
}}
div[data-testid="stMetricDelta"] {{ color: {PEACH} !important; }}

div[data-testid="stExpander"] {{
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  overflow: hidden;
}}
div[data-testid="stExpander"] summary {{ color: {OFF_WHITE} !important; }}

div[data-testid="stDataFrame"], div[data-testid="stTable"] {{
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 0 8px 32px rgba(27, 25, 49, 0.20);
}}

div[data-testid="stVerticalBlockBorderWrapper"] > div {{
  border-radius: 20px;
}}

/* pills / segmented control / multiselect chips */
[data-testid="stPills"] button, span[data-baseweb="tag"] {{
  border-radius: 999px !important;
  background: rgba(255, 255, 255, 0.10) !important;
  border: 1px solid rgba(255, 255, 255, 0.18) !important;
  color: {OFF_WHITE} !important;
}}
[data-testid="stPills"] button[aria-pressed="true"] {{
  background: linear-gradient(135deg, {PEACH}, {BURGUNDY}) !important;
  border: none !important;
  color: {INK} !important;
  font-weight: 600;
}}

/* buttons */
.stButton > button {{
  border-radius: 999px;
  background: linear-gradient(135deg, {PEACH}, {BURGUNDY});
  color: {INK};
  border: none;
  font-weight: 600;
  padding: 0.5rem 1.4rem;
  box-shadow: 0 6px 20px rgba(163, 64, 84, 0.35);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.stButton > button:hover {{
  transform: translateY(-1px);
  box-shadow: 0 10px 26px rgba(163, 64, 84, 0.45);
  color: {INK};
}}

/* inputs / select boxes */
div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input {{
  background: rgba(255, 255, 255, 0.08) !important;
  border-radius: 14px !important;
  border: 1px solid rgba(255, 255, 255, 0.16) !important;
  color: {OFF_WHITE} !important;
}}

hr, div[data-testid="stDivider"] {{
  border-color: rgba(247, 241, 236, 0.14) !important;
}}

/* muted pastel caption text */
.stCaption, [data-testid="stCaptionContainer"] {{
  color: rgba(247, 241, 236, 0.65) !important;
}}

/* alerts (warning/info) — restyle to fit palette instead of default yellow/blue */
div[data-testid="stAlert"] {{
  background: rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  color: {OFF_WHITE} !important;
}}
div[data-testid="stAlert"] * {{ color: {OFF_WHITE} !important; }}

/* native dataframe / json / dropdown surfaces — dark base theme handles most
   of this, but force it in case a component ignores the base theme */
div[data-testid="stDataFrame"] * {{
  background-color: transparent;
}}
ul[data-baseweb="menu"], div[data-baseweb="popover"] {{
  background: {DEEP_PLUM} !important;
}}

/* readable key/value block — replaces raw st.json dumps */
.kv-block {{
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  padding: 1rem 1.2rem;
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}}
.kv-row {{
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  font-size: 0.92rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  padding-bottom: 0.4rem;
}}
.kv-row:last-child {{ border-bottom: none; padding-bottom: 0; }}
.kv-label {{ color: rgba(247, 241, 236, 0.7); }}
.kv-value {{ color: {OFF_WHITE}; font-weight: 600; }}

/* pass/fail/neutral badge — replaces emoji check/cross markers */
.status-line {{
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.95rem;
  padding: 0.15rem 0;
}}
.status-dot {{
  width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0;
}}
.status-dot.pass {{ background: #8FD19E; }}
.status-dot.fail {{ background: #E38B8B; }}
.status-dot.pending {{ background: #E9C46A; }}
.status-dot.na {{ background: rgba(247, 241, 236, 0.35); }}

.verdict-badge {{
  display: inline-block;
  border: 1px solid;
  border-radius: 999px;
  padding: 0.3rem 0.9rem;
  font-weight: 600;
  font-size: 0.9rem;
}}
</style>
"""


def apply_theme() -> None:
    """Injects the sunset-palette CSS. Call once near the top of every page,
    right after st.set_page_config."""
    st.markdown(_CSS, unsafe_allow_html=True)
