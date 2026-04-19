"""
Find My Needs — main search page.
Credentials from cookies (set in Profile). Settings and Filters are separate sidebar sections.
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

cc = CookieController()


# ── Error log ─────────────────────────────────────────────────────────────────
def _log_error(context: str, exc: Exception) -> None:
    if "_err_log" not in st.session_state:
        st.session_state["_err_log"] = []
    st.session_state["_err_log"].append({
        "ctx": context,
        "msg": str(exc),
        "tb":  traceback.format_exc(),
    })


def _show_error_log():
    errors = st.session_state.get("_err_log", [])
    if not errors:
        return
    st.divider()
    with st.expander(f"Error Log ({len(errors)} entries)", expanded=True):
        for e in reversed(errors):
            st.markdown(f"**{e['ctx']}**: `{e['msg']}`")
            st.code(e["tb"], language="python")
        if st.button("Clear error log"):
            st.session_state["_err_log"] = []
            st.rerun()


# ── Cookie helpers ─────────────────────────────────────────────────────────────
def _dec_json(raw: str) -> dict:
    try:
        return json.loads(_f.decrypt(raw.encode()).decode())
    except Exception:
        return {}


def _enc_json(obj: dict) -> str:
    return _f.encrypt(json.dumps(obj).encode()).decode()


def _load_creds() -> tuple[str, str, str]:
    try:
        raw = cc.get("bd_creds")
        d = _dec_json(raw) if raw else {}
        return d.get("u", ""), d.get("p", ""), d.get("k", "")
    except Exception as e:
        _log_error("load_creds", e)
        return "", "", ""


def _load_prefs() -> dict:
    defaults = {"lat": 26.4615, "lng": -80.0728, "state": "US-FL", "dist": 25, "days": 7}
    try:
        raw = cc.get("bd_prefs")
        if raw:
            defaults.update(_dec_json(raw))
    except Exception as e:
        _log_error("load_prefs", e)
    return defaults


def _save_prefs(lat, lng, state, dist, days) -> None:
    try:
        cc.set("bd_prefs", _enc_json({"lat": lat, "lng": lng, "state": state,
                                       "dist": dist, "days": days}))
    except Exception as e:
        _log_error("save_prefs", e)


# ── Credentials from cookies ───────────────────────────────────────────────────
username, password, api_key = _load_creds()

if not (username and password and api_key):
    st.title("🦅 Birding Needs Finder")
    st.warning("Go to **Profile & Settings** to enter your eBird credentials first.")
    _show_error_log()
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
_prefs = _load_prefs()

with st.sidebar:
    st.caption(f"Signed in as **{username}**")
    st.divider()

    # ── SETTINGS: Location & Scope ────────────────────────────────────────────
    with st.expander("Settings — Location & Scope", expanded=False):
        if st.button("📍 Use My Current Location", use_container_width=True):
            loc = get_geolocation()
            if loc and "coords" in loc:
                st.session_state["_geo_lat"] = loc["coords"]["latitude"]
                st.session_state["_geo_lng"] = loc["coords"]["longitude"]
        c1, c2 = st.columns(2)
        lat = c1.number_input("Latitude",  value=float(st.session_state.get("_geo_lat", _prefs["lat"])),  format="%.4f")
        lng = c2.number_input("Longitude", value=float(st.session_state.get("_geo_lng", _prefs["lng"])), format="%.4f")
        state_code = st.text_input("State Code", value=_prefs["state"],
                                    help="e.g. US-FL, US-TX, US-WA").upper()
        dist_km = st.slider("Local radius (km)", 5, 100, int(_prefs["dist"]), 5)
        if st.button("Save as defaults", use_container_width=True):
            _save_prefs(lat, lng, state_code, dist_km,
                        st.session_state.get("days_back", int(_prefs["days"])))
            st.success("Saved!")

    st.divider()

    # ── FILTERS: Time window ──────────────────────────────────────────────────
    st.subheader("Filter")
    st.caption("Birds seen within last:")
    dc1, dc2, dc3, dc4 = st.columns(4)
    if dc1.button("1d",  use_container_width=True): st.session_state["days_back"] = 1
    if dc2.button("3d",  use_container_width=True): st.session_state["days_back"] = 3
    if dc3.button("7d",  use_container_width=True): st.session_state["days_back"] = 7
    if dc4.button("14d", use_container_width=True): st.session_state["days_back"] = 14
    days_back = st.number_input(
        "Custom days", min_value=1, max_value=30,
        value=st.session_state.get("days_back", int(_prefs["days"])),
        label_visibility="collapsed",
    )
    st.session_state["days_back"] = days_back

    st.divider()
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


def render_list(df: pd.DataFrame, label: str):
    display = ["Miles Away", "Common Name", "Scientific Name", "Last Seen", "Location", "Count"]
    if df.empty:
        st.success(f"Nothing missing for {label} — you've seen it all!")
        return
    st.metric(f"Species not yet seen ({label})", len(df))
    st.dataframe(
        df[display], use_container_width=True, hide_index=True,
        column_config={
            "Miles Away":  st.column_config.NumberColumn(format="%.1f mi", width="small"),
            "Common Name": st.column_config.TextColumn(width="medium"),
            "Location":    st.column_config.TextColumn(width="large"),
        },
    )
    st.download_button(
        f"Download {label} CSV",
        df[display].to_csv(index=False).encode(),
        f"needs_{label.lower().replace(' ', '_')}.csv",
        "text/csv",
        use_container_width=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────
st.title("Birding Needs Finder")
st.caption("Birds reported on eBird that you haven't seen yet this year — nearest first.")

if not run_btn:
    st.info("Adjust filters in the sidebar, then click **Find My Needs**.")
    _show_error_log()
    st.stop()

# Fetch year lists — cached for the session, re-scrapes only on refresh
cache_key = f"year_lists_{username}_{state_code}_{datetime.now().year}"
if cache_key not in st.session_state:
    with st.spinner("Logging into eBird and fetching your year lists... (~15 sec)"):
        try:
            year_lists = fetch_year_list_multi_region(username, password, state_code)
            st.session_state[cache_key] = year_lists
        except Exception as e:
            _log_error("fetch_year_list", e)
            st.error(f"eBird login failed: {e}")
            _show_error_log()
            st.stop()

year_lists = st.session_state[cache_key]
seen_world = year_lists.get("world", set())
seen_us    = year_lists.get("US", set())
seen_state = year_lists.get(state_code, set())

m1, m2, m3 = st.columns(3)
m1.metric("World this year",          len(seen_world))
m2.metric("US this year",             len(seen_us))
m3.metric(f"{state_code} this year",  len(seen_state))
st.divider()


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

# ── Interactive Map ────────────────────────────────────────────────────────────
st.subheader("Interactive Map")
st.caption(
    "Click any marker for details. Toggle **Local / State / US** layers top-right. "
    "Switch between Street and Satellite tiles."
)
try:
    bird_map = build_needs_map(lat, lng, local_df, state_df, usa_df)
    st_folium(bird_map, use_container_width=True, height=520, returned_objects=[])
except Exception as e:
    _log_error("build_map", e)
    st.warning("Map failed to render — see Error Log below.")

st.divider()

# ── List tabs ─────────────────────────────────────────────────────────────────
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
    del st.session_state[cache_key]
    st.rerun()

_show_error_log()
