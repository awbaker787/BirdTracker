"""
Birding Needs Finder — entry point.
"""
import streamlit as st

st.set_page_config(page_title="Birding Needs Finder", page_icon="🦅", layout="wide")

pg = st.navigation([
    st.Page("pages/search.py",   title="Find My Needs", icon="🔍", default=True),
    st.Page("pages/profile.py",  title="Profile",       icon="👤"),
    st.Page("pages/settings.py", title="Settings",      icon="⚙️"),
])
pg.run()
