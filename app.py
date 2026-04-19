"""
Birding Needs Finder — Streamlit UI
Run: streamlit run app.py
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta

import extra_streamlit_components as stx
import pandas as pd
import pydeck as pdk
import streamlit as st
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from src.ebird.client import EBirdClient
from src.ebird.scraper import fetch_year_list_multi_region
from src.tracker.needs_finder import Need, NeedsFinder

load_dotenv()

# ── Cookie-based encrypted credential storage ─────────────────────────────────
# Fernet key for encrypting credentials stored in browser cookies.
_FERNET_KEY = b"ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
_f = Fernet(_FERNET_KEY)


def _enc(s: str) -> str:
    return _f.encrypt(s.encode()).decode()


def _dec(s: str) -> str:
    try:
        return _f.decrypt(s.encode()).decode()
    except Exception:
        return ""


cookie_manager = stx.CookieManager(key="bd")


def _get_cookie(name: str) -> str:
    """Read a cookie, decrypting its value. Returns '' if missing."""
    raw = cookie_manager.get(name)
    return _dec(raw) if raw else ""


def _set_cookie(name: str, value: str) -> None:
    cookie_manager.set(name, _enc(value), max_age=365 * 24 * 3600)


@st.cache_resource(show_spinner="Installing browser for eBird login...")
def _install_playwright_browser():
    """Install Chromium once per deployment (needed on Streamlit Cloud)."""
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True, capture_output=True,
    )

_install_playwright_browser()

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Birding Needs Finder", page_icon="🦅", layout="wide")
st.title("🦅 Birding Needs Finder")
st.caption("Birds reported on eBird that you haven't seen yet this year — sorted by distance from you.")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("eBird Account")
    _cu = _get_cookie("bd_username")
    _cp = _get_cookie("bd_password")
    _ck = _get_cookie("bd_apikey")

    if _cu and _cp and _ck:
        username = _cu
        password = _cp
        api_key  = _ck
        st.success(f"Connected as **{username}**")
        if st.button("Change credentials", use_container_width=True):
            for _name in ("bd_username", "bd_password", "bd_apikey"):
                cookie_manager.delete(_name)
            st.rerun()
    else:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        api_key  = st.text_input("API Key",  type="password",
                                  help="Free key at ebird.org/api/keygen")
        if st.button("Save & remember me", type="primary", use_container_width=True):
            if username and password and api_key:
                _set_cookie("bd_username", username)
                _set_cookie("bd_password", password)
                _set_cookie("bd_apikey",   api_key)
                st.rerun()
            else:
                st.warning("Fill in all three fields.")

    st.divider()
    st.subheader("Your Location")
    col1, col2 = st.columns(2)
    with col1:
        lat = st.number_input("Latitude",  value=26.4615, format="%.4f")
    with col2:
        lng = st.number_input("Longitude", value=-80.0728, format="%.4f")
    state_code = st.text_input("State Code", value="US-FL",
                                help="e.g. US-FL, US-WA, US-TX").upper()

    st.divider()
    st.subheader("Search Settings")
    dist_km = st.slider("Local radius (km)", 5, 100, 25, 5)

    st.markdown("**Seen within last:**")
    d_col1, d_col2, d_col3, d_col4 = st.columns(4)
    if d_col1.button("1d",  use_container_width=True): st.session_state["days_back"] = 1
    if d_col2.button("3d",  use_container_width=True): st.session_state["days_back"] = 3
    if d_col3.button("7d",  use_container_width=True): st.session_state["days_back"] = 7
    if d_col4.button("14d", use_container_width=True): st.session_state["days_back"] = 14
    days_back = st.number_input("or custom days", min_value=1, max_value=30,
                                 value=st.session_state.get("days_back", 7))
    st.session_state["days_back"] = days_back

    run_btn = st.button("Find My Needs", type="primary", use_container_width=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def needs_to_df(needs: list[Need], days_back: int) -> pd.DataFrame:
    cutoff = datetime.now() - timedelta(days=days_back)
    rows = []
    for n in needs:
        try:
            obs_dt = datetime.strptime(n.last_seen[:10], "%Y-%m-%d")
        except ValueError:
            continue
        if obs_dt < cutoff:
            continue
        rows.append({
            "Miles Away":      n.dist_miles,
            "Common Name":     n.common_name,
            "Scientific Name": n.scientific_name,
            "Last Seen":       n.last_seen[:10],
            "Location":        n.location_name,
            "Count":           n.count or "—",
            "lat": n.lat, "lng": n.lng,
        })
    return pd.DataFrame(rows)


def render_map(df: pd.DataFrame, color: list[int], user_lat: float, user_lng: float):
    if df.empty:
        return
    bird_layer = pdk.Layer(
        "ScatterplotLayer", data=df,
        get_position="[lng, lat]", get_color=color,
        get_radius=3000, pickable=True,
    )
    you_layer = pdk.Layer(
        "ScatterplotLayer",
        data=[{"lat": user_lat, "lng": user_lng}],
        get_position="[lng, lat]",
        get_color=[255, 255, 0, 230],
        get_radius=1500,
    )
    view = pdk.ViewState(latitude=user_lat, longitude=user_lng, zoom=8)
    st.pydeck_chart(pdk.Deck(
        layers=[bird_layer, you_layer],
        initial_view_state=view,
        tooltip={"text": "{Common Name}\n{Location}\nLast seen: {Last Seen}\n{Miles Away} mi away"},
    ))


def render_tab(needs: list[Need], color: list[int], user_lat: float, user_lng: float, days_back: int = 7):
    df = needs_to_df(needs, days_back)
    display = ["Miles Away", "Common Name", "Scientific Name", "Last Seen", "Location", "Count"]
    if df.empty:
        st.success("Nothing missing — you've seen everything reported here!")
        return
    st.metric("Species not yet seen this year", len(df))
    t_list, t_map = st.tabs(["List", "Map"])
    with t_list:
        st.dataframe(
            df[display],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Miles Away":  st.column_config.NumberColumn(format="%.1f mi", width="small"),
                "Common Name": st.column_config.TextColumn(width="medium"),
                "Location":    st.column_config.TextColumn(width="large"),
            },
        )
        st.download_button("Download CSV",
                           df[display].to_csv(index=False).encode(),
                           "needs.csv", "text/csv")
    with t_map:
        render_map(df, color, user_lat, user_lng)

# ── Main ──────────────────────────────────────────────────────────────────────

if not run_btn:
    st.info("Configure your settings in the sidebar, then click **Find My Needs**.")
    st.stop()

if not username or not password:
    st.error("Enter your eBird username and password in the sidebar.")
    st.stop()
if not api_key:
    st.error("Enter your eBird API key in the sidebar.")
    st.stop()

# Fetch year lists — cached per session so re-scrape only on explicit refresh
cache_key = f"year_lists_{username}_{state_code}_{datetime.now().year}"
if cache_key not in st.session_state:
    with st.spinner("Logging into eBird and fetching your year lists... (~15 sec)"):
        try:
            year_lists = fetch_year_list_multi_region(username, password, state_code)
            st.session_state[cache_key] = year_lists
        except Exception as e:
            st.error(f"eBird login failed: {e}")
            st.stop()

year_lists = st.session_state[cache_key]
seen_world = year_lists.get("world", set())
seen_us    = year_lists.get("US", set())
seen_state = year_lists.get(state_code, set())

# Summary metrics
c1, c2, c3 = st.columns(3)
c1.metric("Species this year (world)", len(seen_world))
c2.metric("Species this year (US)",    len(seen_us))
c3.metric(f"Species this year ({state_code})", len(seen_state))
st.divider()

# Personal shims — each scope filters against the right list
class _World:
    def species_seen_this_year(self, year=None): return seen_world

class _State:
    def species_seen_this_year_in_state(self, state, year=None): return seen_state

class _US:
    def species_seen_this_year(self, year=None): return seen_us

client = EBirdClient(api_key)
local_finder = NeedsFinder(client, _World(), user_lat=lat, user_lng=lng)
state_finder = NeedsFinder(client, _State(), user_lat=lat, user_lng=lng)
usa_finder   = NeedsFinder(client, _US(),    user_lat=lat, user_lng=lng)

with st.spinner("Fetching eBird observations..."):
    try:
        local_needs = local_finder.local_needs(lat, lng, dist_km, days_back)
        state_needs = state_finder.state_needs(state_code, days_back)
        usa_needs   = usa_finder.usa_needs(days_back)
    except Exception as e:
        st.error(f"eBird API error: {e}")
        st.stop()

local_tab, state_tab, usa_tab = st.tabs([
    f"🏠 Local  ({len(local_needs)})",
    f"🗺️ {state_code}  ({len(state_needs)})",
    f"🇺🇸 USA  ({len(usa_needs)})",
])

with local_tab:
    st.caption(f"Birds seen within {dist_km} km of Delray Beach in the **last {days_back} day(s)** — not yet recorded anywhere this year.")
    render_tab(local_needs, [255, 100, 50, 180], lat, lng, days_back)

with state_tab:
    st.caption(f"Birds reported in {state_code} in the **last {days_back} day(s)** — not yet seen in {state_code} this year.")
    render_tab(state_needs, [50, 150, 255, 180], lat, lng, days_back)

with usa_tab:
    st.caption(f"Birds reported anywhere in the US in the **last {days_back} day(s)** — not yet seen in the US this year.")
    render_tab(usa_needs, [80, 200, 100, 180], lat, lng, days_back)

st.divider()
if st.button("🔄 Refresh Year List from eBird"):
    del st.session_state[cache_key]
    st.rerun()
