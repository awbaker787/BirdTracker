"""
Birding Needs Finder — entry point.
"""
import streamlit as st
from streamlit_cookies_controller import CookieController

st.set_page_config(page_title="Birding Needs Finder", page_icon="🦅", layout="wide")

# Render the cookie controller once here so it initialises (sends browser cookies
# back to Python) before any page script runs its auth check.
# On the very first render the component hasn't sent its data yet, so we do one
# controlled rerun — after that cookies are available for the rest of the session.
_cc = CookieController(key="bd_cc")
if "cc_ready" not in st.session_state:
    st.session_state["cc_ready"] = True
    st.rerun()

pg = st.navigation([
    st.Page("pages/search.py",   title="Find My Needs", icon="🔍", default=True),
    st.Page("pages/profile.py",  title="Profile",       icon="👤"),
    st.Page("pages/settings.py", title="Settings",      icon="⚙️"),
])
pg.run()
