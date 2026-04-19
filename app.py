"""
Birding Needs Finder — entry point.
Sets page config, installs Playwright once, then hands off to st.navigation pages.
"""
import subprocess
import sys

import streamlit as st

st.set_page_config(page_title="Birding Needs Finder", page_icon="🦅", layout="wide")


@st.cache_resource(show_spinner="Installing browser for eBird login...")
def _install_playwright_browser():
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True, capture_output=True,
    )


_install_playwright_browser()

pg = st.navigation([
    st.Page("pages/search.py",   title="Find My Needs", icon="🔍", default=True),
    st.Page("pages/profile.py",  title="Profile",       icon="👤"),
    st.Page("pages/settings.py", title="Settings",      icon="⚙️"),
])
pg.run()
