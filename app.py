"""
Birding Needs Finder — entry point.
"""
import streamlit as st
from streamlit_cookies_controller import CookieController

st.set_page_config(page_title="Birding Needs Finder", page_icon="🦅", layout="wide")

# CookieController must be instantiated EXACTLY ONCE per render cycle.
# Creating it again in any page with the same key raises:
#   StreamlitAPIException: st.session_state.bd_cc cannot be modified after
#   the widget with key bd_cc is instantiated.
# Solution: create it here, probe for readiness, then store the live instance
# in session_state so pages can call get_cc() without re-instantiating.
_cc = CookieController(key="bd_cc")
try:
    _cc.get("__probe__")
    st.session_state["_cc_instance"] = _cc   # share with pages
except TypeError:
    st.rerun()   # cookies not ready yet — component will trigger next render

pg = st.navigation([
    st.Page("pages/search.py",    title="Find My Needs",    icon="🔍", default=True),
    st.Page("pages/checklist.py", title="Field Checklist",  icon="✅"),
    st.Page("pages/profile.py",   title="Profile",          icon="👤"),
    st.Page("pages/settings.py",  title="Settings",         icon="⚙️"),
])
pg.run()
