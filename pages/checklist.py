"""
Field Checklist — manual per-county bird tracker.

No eBird login required.  Checks are saved to browser localStorage
per county + year and persist across sessions.
"""
import json
import streamlit.components.v1 as _stcomp
from datetime import datetime

import folium
import streamlit as st
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval as _st_js, get_geolocation

from src.ebird.client import EBirdClient
from src.ui.cookies import cc_get, get_cc

from cryptography.fernet import Fernet
_FERNET_KEY = b"ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
_f = Fernet(_FERNET_KEY)
cc = get_cc()

# ── US state lookup ────────────────────────────────────────────────────────────
_STATES = {
    "US-AL":"Alabama","US-AK":"Alaska","US-AZ":"Arizona","US-AR":"Arkansas",
    "US-CA":"California","US-CO":"Colorado","US-CT":"Connecticut","US-DE":"Delaware",
    "US-DC":"Washington DC","US-FL":"Florida","US-GA":"Georgia","US-HI":"Hawaii",
    "US-ID":"Idaho","US-IL":"Illinois","US-IN":"Indiana","US-IA":"Iowa",
    "US-KS":"Kansas","US-KY":"Kentucky","US-LA":"Louisiana","US-ME":"Maine",
    "US-MD":"Maryland","US-MA":"Massachusetts","US-MI":"Michigan","US-MN":"Minnesota",
    "US-MS":"Mississippi","US-MO":"Missouri","US-MT":"Montana","US-NE":"Nebraska",
    "US-NV":"Nevada","US-NH":"New Hampshire","US-NJ":"New Jersey","US-NM":"New Mexico",
    "US-NY":"New York","US-NC":"North Carolina","US-ND":"North Dakota","US-OH":"Ohio",
    "US-OK":"Oklahoma","US-OR":"Oregon","US-PA":"Pennsylvania","US-RI":"Rhode Island",
    "US-SC":"South Carolina","US-SD":"South Dakota","US-TN":"Tennessee","US-TX":"Texas",
    "US-UT":"Utah","US-VT":"Vermont","US-VA":"Virginia","US-WA":"Washington",
    "US-WV":"West Virginia","US-WI":"Wisconsin","US-WY":"Wyoming",
}
_STATE_CODES = list(_STATES.keys())
_STATE_NAMES = [_STATES[c] for c in _STATE_CODES]

# ── cookie helpers ─────────────────────────────────────────────────────────────
def _dec_json(raw):
    try:
        return json.loads(_f.decrypt(raw.encode()).decode())
    except Exception:
        return {}

def _load_creds():
    try:
        raw = cc_get(cc, "bd_creds")
        d = _dec_json(raw) if raw else {}
        return d.get("u", ""), d.get("p", ""), d.get("k", "")
    except Exception:
        return "", "", ""

def _load_prefs():
    defaults = {"lat": 26.4615, "lng": -80.0728, "state": "US-FL"}
    try:
        raw = cc_get(cc, "bd_prefs")
        if raw:
            defaults.update(_dec_json(raw))
    except Exception:
        pass
    return defaults

# ── eBird API ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=7*24*3600, show_spinner=False)
def _counties(api_key: str, state_code: str) -> list[dict]:
    result = EBirdClient(api_key)._get(f"/ref/region/list/subnational2/{state_code}")
    return sorted(result or [], key=lambda x: x.get("name", ""))

@st.cache_data(ttl=3600, show_spinner=False)
def _recent_obs(api_key: str, county_code: str, days_back: int) -> list[dict]:
    obs = EBirdClient(api_key).recent_observations_in_region(
        county_code, days_back=days_back, max_results=3000
    )
    seen: dict = {}
    for o in obs:
        code = o.get("speciesCode", "")
        if not code or "/" in o.get("comName", ""):
            continue
        if code not in seen or o.get("obsDt", "") > seen[code].get("obsDt", ""):
            seen[code] = o
    return sorted(seen.values(), key=lambda x: x.get("comName", ""))

# ── localStorage ───────────────────────────────────────────────────────────────
def _ls_key(county_code: str, year: int) -> str:
    return f"bd_cl_{county_code.replace('-','_')}_{year}"

def _ls_read(ls_key: str):
    return _st_js(
        js_expressions=f"JSON.parse(localStorage.getItem('{ls_key}') || '[]')",
        want_output=True,
        key=f"lsr_{ls_key}",
    )

def _ls_write(ls_key: str, codes: set):
    _stcomp.html(
        f"<script>localStorage.setItem('{ls_key}',JSON.stringify({json.dumps(list(codes))}));</script>",
        height=0,
    )

def _ls_clear(ls_key: str):
    _stcomp.html(f"<script>localStorage.removeItem('{ls_key}');</script>", height=0)

# ── auth ───────────────────────────────────────────────────────────────────────
_, _, api_key = _load_creds()
if not api_key:
    st.title("Field Checklist")
    st.warning("Go to **Profile** to enter your eBird API key first.")
    st.stop()

_prefs = _load_prefs()
year   = datetime.now().year

# ── session state defaults ────────────────────────────────────────────────────
if "cl_state_code" not in st.session_state:
    st.session_state["cl_state_code"] = _prefs.get("state", "US-FL")
if "cl_county_code" not in st.session_state:
    st.session_state["cl_county_code"] = ""
if "cl_county_name" not in st.session_state:
    st.session_state["cl_county_name"] = ""
if "cl_days_back" not in st.session_state:
    st.session_state["cl_days_back"] = 30

# ── geolocation (must be before any columns / dialogs) ────────────────────────
if st.session_state.get("_cl_want_geo"):
    _geo = get_geolocation()
    if _geo and "coords" in _geo:
        st.session_state["_geo_lat"] = _geo["coords"]["latitude"]
        st.session_state["_geo_lng"] = _geo["coords"]["longitude"]
        st.session_state.pop("_cl_want_geo", None)

# ── filter dialog ─────────────────────────────────────────────────────────────
@st.dialog("📍 Location & Filters")
def _open_filter_dialog(api_key: str):
    # State
    cur_state = st.session_state["cl_state_code"]
    state_idx = _STATE_CODES.index(cur_state) if cur_state in _STATE_CODES else 9
    chosen_state_name = st.selectbox("State", _STATE_NAMES, index=state_idx)
    chosen_state_code = _STATE_CODES[_STATE_NAMES.index(chosen_state_name)]

    # County — reload if state changed
    try:
        county_list = _counties(api_key, chosen_state_code)
    except Exception as e:
        st.error(f"Could not load counties: {e}")
        return

    if not county_list:
        st.warning("No counties found for this state.")
        return

    county_names = [c["name"] for c in county_list]
    county_codes = [c["code"] for c in county_list]

    # Try to pre-select the saved county if it's in the same state
    saved_code = st.session_state.get("cl_county_code", "")
    try:
        c_idx = county_codes.index(saved_code) if saved_code in county_codes else 0
    except ValueError:
        c_idx = 0

    chosen_county_idx = st.selectbox(
        "County", range(len(county_names)),
        format_func=lambda i: county_names[i],
        index=c_idx,
    )

    st.divider()

    # Days filter
    new_days = st.select_slider(
        "Show birds reported in the last",
        options=[1, 7, 14, 30, 60, 90],
        value=st.session_state["cl_days_back"],
        format_func=lambda d: f"{d}d",
    )
    st.session_state["cl_days_back"] = new_days

    st.divider()

    # My Location
    geo_col, _ = st.columns([2, 1])
    if geo_col.button("📍 Use My Location", use_container_width=True):
        st.session_state["_cl_want_geo"] = True

    ulat = st.session_state.get("_geo_lat", _prefs["lat"])
    ulng = st.session_state.get("_geo_lng", _prefs["lng"])
    st.caption(f"Current coords: {ulat:.4f}, {ulng:.4f}")

    st.divider()
    if st.button("✅ Apply", type="primary", use_container_width=True):
        st.session_state["cl_state_code"]  = chosen_state_code
        st.session_state["cl_county_code"] = county_codes[chosen_county_idx]
        st.session_state["cl_county_name"] = county_names[chosen_county_idx]
        # Clear cached checklist if county changed
        old_code = st.session_state.get("_last_applied_county", "")
        new_code = county_codes[chosen_county_idx]
        if old_code != new_code:
            st.session_state.pop(f"_cl_{new_code}_{year}", None)
            st.session_state.pop(f"_cl_ready_{new_code}_{year}", None)
        st.session_state["_last_applied_county"] = new_code
        st.rerun()

# ── ensure a county is selected ───────────────────────────────────────────────
# On first visit, auto-load the default state's county list and pick the first
if not st.session_state.get("cl_county_code"):
    try:
        _default_counties = _counties(api_key, st.session_state["cl_state_code"])
        if _default_counties:
            st.session_state["cl_county_code"] = _default_counties[0]["code"]
            st.session_state["cl_county_name"] = _default_counties[0]["name"]
    except Exception:
        pass

state_code  = st.session_state["cl_state_code"]
county_code = st.session_state["cl_county_code"]
county_name = st.session_state["cl_county_name"] or county_code
days_back   = st.session_state["cl_days_back"]

# ── page header ───────────────────────────────────────────────────────────────
title_col, btn_col = st.columns([5, 2])
title_col.markdown("## 🗒️ Field Checklist")
if btn_col.button(
    f"📍 {county_name}, {_STATES.get(state_code, state_code)}  ·  {days_back}d  ✏️",
    use_container_width=True,
):
    _open_filter_dialog(api_key)

if not county_code:
    st.info("Click the location button above to choose a county.")
    st.stop()

# ── load localStorage checklist ────────────────────────────────────────────────
ls_key_val  = _ls_key(county_code, year)
session_key = f"_cl_{county_code}_{year}"
ready_key   = f"_cl_ready_{county_code}_{year}"

if not st.session_state.get(ready_key):
    ls_raw = _ls_read(ls_key_val)
    if ls_raw is None:
        st.info("Loading…")
        st.stop()
    st.session_state[session_key] = set(ls_raw)
    st.session_state[ready_key]   = True

checked: set = st.session_state[session_key]

# ── fetch observations ─────────────────────────────────────────────────────────
with st.spinner(f"Loading birds for {county_name}…"):
    try:
        obs_list = _recent_obs(api_key, county_code, days_back)
    except Exception as e:
        st.error(f"eBird API error: {e}")
        st.stop()

if not obs_list:
    st.info(f"No observations in {county_name} in the last {days_back} days. "
            f"Try a wider window — click the location button above.")
    st.stop()

# ── map (collapsible) ─────────────────────────────────────────────────────────
with st.expander("🗺️ Map", expanded=True):
    lats = [o["lat"] for o in obs_list if "lat" in o]
    lngs = [o["lng"] for o in obs_list if "lng" in o]
    clat = sum(lats)/len(lats) if lats else _prefs["lat"]
    clng = sum(lngs)/len(lngs) if lngs else _prefs["lng"]

    m = folium.Map(location=[clat, clng], zoom_start=10, tiles=None)
    folium.TileLayer("OpenStreetMap", name="Street").add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satellite",
    ).add_to(m)
    for o in obs_list:
        if "lat" not in o:
            continue
        code = o.get("speciesCode", "")
        folium.CircleMarker(
            location=[o["lat"], o["lng"]], radius=5,
            color="#2ecc71" if code in checked else "#3498db",
            fill=True, fill_opacity=0.8,
            tooltip=o.get("comName", code) + (" ✓" if code in checked else ""),
            popup=folium.Popup(
                f"<b>{o.get('comName','')}</b><br>{o.get('locName','')}<br>{o.get('obsDt','')[:10]}",
                max_width=200,
            ),
        ).add_to(m)
    ulat = st.session_state.get("_geo_lat", _prefs["lat"])
    ulng = st.session_state.get("_geo_lng", _prefs["lng"])
    folium.CircleMarker([ulat, ulng], radius=10, color="#fff", weight=2,
                        fill=True, fill_color="#4285F4", fill_opacity=1.0,
                        tooltip="You").add_to(m)
    folium.CircleMarker([ulat, ulng], radius=22, color="#4285F4", weight=1,
                        fill=True, fill_color="#4285F4", fill_opacity=0.15).add_to(m)
    folium.LayerControl().add_to(m)
    st_folium(m, use_container_width=True, height=340, returned_objects=[])

# ── checklist header ──────────────────────────────────────────────────────────
total     = len(obs_list)
n_checked = len(checked & {o["speciesCode"] for o in obs_list})

h_left, h_right = st.columns([4, 2])
name_filter = h_left.text_input(
    "search", placeholder="🔍  Search species…",
    label_visibility="collapsed", key="cl_filter",
)
show_all = h_right.radio(
    "show", ["All", "Unchecked"], horizontal=True,
    label_visibility="collapsed", key="cl_show",
) == "All"

st.markdown(
    f"**{county_name}** · {year} · "
    f"<span style='color:#2ecc71'>✓ {n_checked}</span> / {total} species",
    unsafe_allow_html=True,
)
st.divider()

# ── checklist rows ────────────────────────────────────────────────────────────
filtered = [
    o for o in obs_list
    if name_filter.lower() in o.get("comName", "").lower()
    and (show_all or o.get("speciesCode") not in checked)
]

new_checked = set(checked)
changed     = False

for o in filtered:
    code = o.get("speciesCode", "")
    name = o.get("comName", code)
    sci  = o.get("sciName", "")
    dt   = o.get("obsDt", "")[:10]
    loc  = o.get("locName", "")
    cnt  = o.get("howMany")

    cb_col, info_col = st.columns([1, 11])
    ticked = cb_col.checkbox(
        "", value=code in checked,
        key=f"cb_{county_code}_{year}_{code}",
        label_visibility="collapsed",
    )
    info_col.markdown(
        f"**{name}** &nbsp; <span style='color:#888;font-size:12px;font-style:italic'>{sci}</span>  \n"
        f"<span style='color:#999;font-size:12px'>{dt}"
        + (f" · {cnt} birds" if cnt else "")
        + f" · {loc}</span>",
        unsafe_allow_html=True,
    )
    if ticked and code not in new_checked:
        new_checked.add(code);     changed = True
    elif not ticked and code in new_checked:
        new_checked.discard(code); changed = True

if changed:
    st.session_state[session_key] = new_checked
    _ls_write(ls_key_val, new_checked)

# ── footer ────────────────────────────────────────────────────────────────────
st.divider()
foot_l, foot_r = st.columns([3, 2])
foot_l.caption(f"Saved locally · no eBird login · last {days_back}d · {len(filtered)} shown")
if foot_r.button("🗑️ Clear checklist", use_container_width=True):
    _ls_clear(ls_key_val)
    st.session_state.pop(session_key, None)
    st.session_state.pop(ready_key, None)
    st.rerun()
