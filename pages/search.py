"""
Find My Needs — main search page.
All key controls (location, days filter, search) are on the main page for fast access.
Sidebar holds less-frequently-changed settings.
"""
import json
import traceback
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from streamlit_cookies_controller import CookieController
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation

from src.ebird.client import EBirdClient
from src.ebird.scraper import fetch_year_list_multi_region
from src.tracker.needs_finder import Need, NeedsFinder
from src.ui.map_builder import build_needs_map

load_dotenv()

_FERNET_KEY = b"ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
_f = Fernet(_FERNET_KEY)
cc = CookieController(key="bd_cc")
_ONE_YEAR = 365 * 24 * 3600


# ── Helpers ────────────────────────────────────────────────────────────────────
def _log_error(ctx, exc):
    st.session_state.setdefault("_err_log", []).append(
        {"ctx": ctx, "msg": str(exc), "tb": traceback.format_exc()}
    )

def _show_error_log():
    errors = st.session_state.get("_err_log", [])
    if not errors:
        return
    st.divider()
    with st.expander(f"Error Log ({len(errors)})", expanded=True):
        for e in reversed(errors):
            st.code(f"{e['ctx']}: {e['msg']}\n\n{e['tb']}", language="python")
        if st.button("Clear error log"):
            st.session_state["_err_log"] = []
            st.rerun()

def _dec_json(raw):
    try:
        return json.loads(_f.decrypt(raw.encode()).decode())
    except Exception:
        return {}

def _enc_json(obj):
    return _f.encrypt(json.dumps(obj).encode()).decode()

def _load_creds():
    try:
        raw = cc.get("bd_creds")
        d = _dec_json(raw) if raw else {}
        return d.get("u", ""), d.get("p", ""), d.get("k", "")
    except Exception as e:
        _log_error("load_creds", e)
        return "", "", ""

def _load_prefs():
    defaults = {"lat": 26.4615, "lng": -80.0728, "state": "US-FL", "dist": 25, "days": 7}
    try:
        raw = cc.get("bd_prefs")
        if raw:
            defaults.update(_dec_json(raw))
    except Exception as e:
        _log_error("load_prefs", e)
    return defaults

def _save_prefs(lat, lng, state, dist, days):
    try:
        cc.set("bd_prefs", _enc_json({"lat": lat, "lng": lng, "state": state,
                                       "dist": dist, "days": days}), max_age=_ONE_YEAR)
    except Exception as e:
        _log_error("save_prefs", e)

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
            "Miles Away": n.dist_miles, "Common Name": n.common_name,
            "Scientific Name": n.scientific_name, "Last Seen": n.last_seen[:10],
            "Location": n.location_name, "Count": n.count or "—",
            "lat": n.lat, "lng": n.lng,
        })
    return pd.DataFrame(rows)

def render_list(df, label):
    display = ["Miles Away", "Common Name", "Scientific Name", "Last Seen", "Location", "Count"]
    if df.empty:
        st.success(f"Nothing missing for {label} — you've seen it all!")
        return
    st.metric(f"Species not yet seen ({label})", len(df))
    st.dataframe(df[display], use_container_width=True, hide_index=True,
        column_config={
            "Miles Away":  st.column_config.NumberColumn(format="%.1f mi", width="small"),
            "Common Name": st.column_config.TextColumn(width="medium"),
            "Location":    st.column_config.TextColumn(width="large"),
        })
    st.download_button(f"Download {label} CSV",
        df[display].to_csv(index=False).encode(),
        f"needs_{label.lower().replace(' ','_')}.csv", "text/csv",
        use_container_width=True)


# ── Cached year list fetch (persists across page reloads) ─────────────────────
@st.cache_data(ttl=23 * 3600, show_spinner=False)
def _cached_year_list(username: str, password: str, state_code: str, year: int) -> dict:
    """Fetch year lists once; cached 23 h so the scrape runs at most once per day."""
    result = fetch_year_list_multi_region(username, password, state_code, year)
    # cache_data needs JSON-serialisable data — convert sets to lists
    return {k: list(v) for k, v in result.items()}


# ── Auth check ────────────────────────────────────────────────────────────────
username, password, api_key = _load_creds()
if not (username and password and api_key):
    st.title("Birding Needs Finder")
    st.warning("Go to **Profile** to enter your eBird credentials first.")
    _show_error_log()
    st.stop()

_prefs = _load_prefs()

# ── Sidebar: less-frequent settings ───────────────────────────────────────────
with st.sidebar:
    st.caption(f"Signed in as **{username}**")
    st.divider()
    st.subheader("Location & Scope")
    lat       = st.number_input("Latitude",  value=float(st.session_state.get("_geo_lat", _prefs["lat"])),  format="%.4f")
    lng       = st.number_input("Longitude", value=float(st.session_state.get("_geo_lng", _prefs["lng"])), format="%.4f")
    state_code = st.text_input("State Code", value=_prefs["state"], help="e.g. US-FL, US-TX").upper()
    dist_km   = st.slider("Local radius (km)", 5, 100, int(_prefs["dist"]), 5)
    if st.button("Save as defaults", use_container_width=True):
        _save_prefs(lat, lng, state_code, dist_km,
                    st.session_state.get("days_back", int(_prefs["days"])))
        st.success("Saved!")

# ── Main page ─────────────────────────────────────────────────────────────────
st.title("Birding Needs Finder")

# ── Action bar ────────────────────────────────────────────────────────────────
loc_col, day_col, run_col = st.columns([2, 4, 2])

with loc_col:
    if st.button("📍 My Location", use_container_width=True):
        loc = get_geolocation()
        if loc and "coords" in loc:
            st.session_state["_geo_lat"] = loc["coords"]["latitude"]
            st.session_state["_geo_lng"] = loc["coords"]["longitude"]
            st.rerun()
    lat_disp = st.session_state.get("_geo_lat", _prefs["lat"])
    lng_disp = st.session_state.get("_geo_lng", _prefs["lng"])
    st.caption(f"{lat_disp:.3f}, {lng_disp:.3f} · {state_code} · {dist_km} km")

with day_col:
    st.caption("Seen within last:")
    d1, d2, d3, d4, d5 = st.columns(5)
    if d1.button("1d",  use_container_width=True): st.session_state["days_back"] = 1
    if d2.button("3d",  use_container_width=True): st.session_state["days_back"] = 3
    if d3.button("7d",  use_container_width=True): st.session_state["days_back"] = 7
    if d4.button("14d", use_container_width=True): st.session_state["days_back"] = 14
    days_back = d5.number_input("days", min_value=1, max_value=30,
        value=st.session_state.get("days_back", int(_prefs["days"])),
        label_visibility="collapsed")
    st.session_state["days_back"] = days_back

with run_col:
    st.caption(" ")   # align vertically with other columns
    run_btn = st.button("Find My Needs", type="primary", use_container_width=True)

st.divider()

if not run_btn:
    st.info("Choose a time filter and click **Find My Needs** to search.")
    _show_error_log()
    st.stop()

# ── Fetch year list (cached 23 h across page reloads) ─────────────────────────
year = datetime.now().year
with st.spinner("Fetching your eBird year list..."):
    try:
        raw_lists = _cached_year_list(username, password, state_code, year)
    except Exception as e:
        _log_error("fetch_year_list", e)
        st.error(f"eBird login failed: {e}")
        _show_error_log()
        st.stop()

seen_world = set(raw_lists.get("world", []))
seen_us    = set(raw_lists.get("US", []))
seen_state = set(raw_lists.get(state_code, []))

m1, m2, m3 = st.columns(3)
m1.metric("World this year",         len(seen_world))
m2.metric("US this year",            len(seen_us))
m3.metric(f"{state_code} this year", len(seen_state))
st.divider()

# ── Fetch observations ─────────────────────────────────────────────────────────
class _World:
    def species_seen_this_year(self, year=None): return seen_world
class _State:
    def species_seen_this_year_in_state(self, state, year=None): return seen_state
class _US:
    def species_seen_this_year(self, year=None): return seen_us

client       = EBirdClient(api_key)
local_finder = NeedsFinder(client, _World(), user_lat=lat, user_lng=lng)
state_finder = NeedsFinder(client, _State(), user_lat=lat, user_lng=lng)
usa_finder   = NeedsFinder(client, _US(),    user_lat=lat, user_lng=lng)

with st.spinner("Fetching eBird observations..."):
    try:
        local_needs = local_finder.local_needs(lat, lng, dist_km, days_back)
        state_needs = state_finder.state_needs(state_code, days_back)
        usa_needs   = usa_finder.usa_needs(days_back)
    except Exception as e:
        _log_error("fetch_observations", e)
        st.error(f"eBird API error: {e}")
        _show_error_log()
        st.stop()

local_df = needs_to_df(local_needs, days_back)
state_df = needs_to_df(state_needs, days_back)
usa_df   = needs_to_df(usa_needs,   days_back)

# ── Map ────────────────────────────────────────────────────────────────────────
st.subheader("Interactive Map")
st.caption("Click markers for details · Toggle Local / State / US layers · Switch Street / Satellite")
try:
    st_folium(build_needs_map(lat, lng, local_df, state_df, usa_df),
              use_container_width=True, height=500, returned_objects=[])
except Exception as e:
    _log_error("build_map", e)
    st.warning("Map failed to render — see Error Log below.")

st.divider()

# ── Lists ──────────────────────────────────────────────────────────────────────
local_tab, state_tab, usa_tab = st.tabs([
    f"Local ({len(local_df)})",
    f"{state_code} ({len(state_df)})",
    f"USA ({len(usa_df)})",
])
with local_tab:
    st.caption(f"Within {dist_km} km — last {days_back} day(s)")
    render_list(local_df, "Local")
with state_tab:
    st.caption(f"Reported in {state_code} — last {days_back} day(s)")
    render_list(state_df, state_code)
with usa_tab:
    st.caption(f"Reported anywhere in the US — last {days_back} day(s)")
    render_list(usa_df, "USA")

st.divider()
if st.button("Refresh Year List from eBird"):
    _cached_year_list.clear()
    st.rerun()

_show_error_log()
