"""
Birding Needs Finder — entry point.
"""
import streamlit as st
from streamlit_cookies_controller import CookieController

st.set_page_config(page_title="Birding Needs Finder", page_icon="🦅", layout="wide")

# Render the cookie controller here so the browser-side component mounts before
# any page script runs.  __cookies is None on the very first render; probe it
# and rerun until the component has sent its data back (typically 1 extra cycle).
_cc = CookieController(key="bd_cc")
try:
    _cc.get("__probe__")
except TypeError:
    st.rerun()

pg = st.navigation([
    st.Page("pages/search.py",    title="Find My Needs",    icon="🔍", default=True),
    st.Page("pages/checklist.py", title="Field Checklist",  icon="✅"),
    st.Page("pages/profile.py",   title="Profile",          icon="👤"),
    st.Page("pages/settings.py",  title="Settings",         icon="⚙️"),
])
pg.run()
