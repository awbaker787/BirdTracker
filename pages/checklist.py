"""
Field Checklist — manual per-county bird tracker.

Shows birds recently reported in any county (via public eBird API — no login
required).  User checks off what they see.  Checklist is saved per county+year
in browser localStorage and persists across sessions completely independently
of eBird scraping or personal-list sync.
"""
import json
import streamlit.components.v1 as _stcomp
from datetime import datetime

import folium
import streamlit as st
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval as _st_js

from src.ebird.client import EBirdClient
from src.ui.cookies import cc_get, get_cc

from cryptography.fernet import Fernet
_FERNET_KEY = b"ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
_f = Fernet(_FERNET_KEY)

cc = get_cc()


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
    defaults = {"lat": 26.4615, "lng": -80.0728, "state": "US-FL", "dist": 25, "days": 7}
    try:
        raw = cc_get(cc, "bd_prefs")
        if raw:
            defaults.update(_dec_json(raw))
    except Exception:
        pass
    return defaults


# ── eBird API helpers ──────────────────────────────────────────────────────────
@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def _counties(api_key: str, state_code: str) -> list[dict]:
    """Return [{code, name}] for all counties in a state."""
    client = EBirdClient(api_key)
    result = client._get(f"/ref/region/list/subnational2/{state_code}")
    return result if result else []


@st.cache_data(ttl=3600, show_spinner=False)
def _recent_obs(api_key: str, county_code: str, days_back: int) -> list[dict]:
    """Recent observations in the county, deduped to one per species."""
    client = EBirdClient(api_key)
    obs = client.recent_observations_in_region(county_code, days_back=days_back, max_results=3000)
    seen: dict = {}
    for o in obs:
        code = o.get("speciesCode", "")
        if not code or "/" in o.get("comName", ""):
            continue
        if code not in seen or o.get("obsDt", "") > seen[code].get("obsDt", ""):
            seen[code] = o
    return sorted(seen.values(), key=lambda x: x.get("comName", ""))


# ── localStorage helpers ───────────────────────────────────────────────────────
# IMPORTANT: _ls_read uses a STABLE key so the component persists across reruns
# and returns the cached browser value instead of None on every render.
# _ls_write / _ls_clear use components.html (fire-and-forget, no rerun triggered).

def _ls_key(county_code: str, year: int) -> str:
    return f"bd_cl_{county_code.replace('-', '_')}_{year}"

def _ls_read(ls_key: str):
    """Returns Python list on 2nd+ render, None on 1st render.
    Stable key is critical — without it a new random key is generated each render,
    the component never persists, and this always returns None (infinite loop)."""
    # Return [] (not null) for missing key so Python gets [] vs None.
    # None = component not ready yet (1st render).
    # [] = component ready, localStorage has no entry for this key.
    # [...] = component ready, saved checklist found.
    return _st_js(
        js_expressions=f"JSON.parse(localStorage.getItem('{ls_key}') || '[]')",
        want_output=True,
        key=f"lsr_{ls_key}",
    )

def _ls_write(ls_key: str, codes: set):
    """Write codes to localStorage. Uses components.html so no rerun is triggered."""
    data_str = json.dumps(list(codes))
    _stcomp.html(
        f"<script>localStorage.setItem('{ls_key}', JSON.stringify({data_str}));</script>",
        height=0,
    )

def _ls_clear(ls_key: str):
    """Remove key from localStorage. Uses components.html so no rerun is triggered."""
    _stcomp.html(
        f"<script>localStorage.removeItem('{ls_key}');</script>",
        height=0,
    )


# ── auth ───────────────────────────────────────────────────────────────────────
_, _, api_key = _load_creds()
if not api_key:
    st.title("Field Checklist")
    st.warning("Go to **Profile** to enter your eBird API key first.")
    st.stop()

_prefs = _load_prefs()
year = datetime.now().year

# ── sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Location")
    state_code = st.text_input(
        "State Code", value=_prefs["state"], help="e.g. US-FL, US-TX"
    ).upper().strip()

    try:
        county_list = _counties(api_key, state_code)
    except Exception as e:
        st.error(f"Could not load counties: {e}")
        st.stop()

    if not county_list:
        st.error("No counties found — check the state code (e.g. US-FL).")
        st.stop()

    county_names = [c["name"] for c in county_list]
    county_codes = [c["code"] for c in county_list]
    county_idx   = st.selectbox(
        "County", range(len(county_names)),
        format_func=lambda i: county_names[i],
    )
    county_code = county_codes[county_idx]
    county_name = county_names[county_idx]

    days_back = st.slider("Show birds reported in last", 1, 90, 30, 1, format="%d days")

    st.divider()
    st.subheader("Checklist Stats")
    _stats_slot = st.empty()   # filled after we know the checked set

    st.divider()
    if st.button("Clear checklist for this county", use_container_width=True):
        _ls_clear(_ls_key(county_code, year))
        st.session_state.pop(f"_cl_{county_code}_{year}", None)
        st.session_state.pop(f"_cl_ready_{county_code}_{year}", None)
        st.rerun()


# ── load checklist from localStorage ──────────────────────────────────────────
ls_key_val  = _ls_key(county_code, year)
session_key = f"_cl_{county_code}_{year}"
ready_key   = f"_cl_ready_{county_code}_{year}"

if not st.session_state.get(ready_key):
    ls_raw = _ls_read(ls_key_val)
    if ls_raw is None:
        # Component hasn't sent data yet (1st render) — wait for 2nd render
        st.info("Loading saved checklist…")
        st.stop()
    st.session_state[session_key] = set(ls_raw) if ls_raw else set()
    st.session_state[ready_key]   = True

checked: set = st.session_state[session_key]


# ── fetch species ──────────────────────────────────────────────────────────────
st.title(f"Field Checklist · {county_name}")
st.caption(f"{state_code} · {year} · birds reported in the last {days_back} day(s)")

with st.spinner("Fetching recent birds…"):
    try:
        obs_list = _recent_obs(api_key, county_code, days_back)
    except Exception as e:
        st.error(f"eBird API error: {e}")
        st.stop()

if not obs_list:
    st.info("No observations found for this county / time window. Try increasing the days.")
    st.stop()


# ── map ────────────────────────────────────────────────────────────────────────
lats = [o["lat"] for o in obs_list if "lat" in o]
lngs = [o["lng"] for o in obs_list if "lng" in o]
center_lat = sum(lats) / len(lats) if lats else _prefs["lat"]
center_lng = sum(lngs) / len(lngs) if lngs else _prefs["lng"]

m = folium.Map(location=[center_lat, center_lng], zoom_start=10, tiles=None)
folium.TileLayer("OpenStreetMap", name="Street map").add_to(m)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri", name="Satellite",
).add_to(m)

for o in obs_list:
    if "lat" not in o:
        continue
    code   = o.get("speciesCode", "")
    name   = o.get("comName", code)
    is_ckd = code in checked
    folium.CircleMarker(
        location=[o["lat"], o["lng"]],
        radius=5,
        color="#2ecc71" if is_ckd else "#3498db",
        fill=True,
        fill_opacity=0.75,
        popup=folium.Popup(
            f"<b>{name}</b><br>{o.get('locName','')}<br>{o.get('obsDt','')}"
            + (" ✓" if is_ckd else ""),
            max_width=220,
        ),
        tooltip=name + (" ✓" if is_ckd else ""),
    ).add_to(m)

# User location — blue dot
user_lat = st.session_state.get("_geo_lat", _prefs["lat"])
user_lng = st.session_state.get("_geo_lng", _prefs["lng"])
folium.CircleMarker(
    location=[user_lat, user_lng],
    radius=10, color="#ffffff", weight=2,
    fill=True, fill_color="#4285F4", fill_opacity=1.0,
    tooltip="Your location",
).add_to(m)
folium.CircleMarker(
    location=[user_lat, user_lng],
    radius=22, color="#4285F4", weight=1,
    fill=True, fill_color="#4285F4", fill_opacity=0.15,
).add_to(m)

folium.LayerControl().add_to(m)
st_folium(m, use_container_width=True, height=380, returned_objects=[])
st.divider()


# ── checklist ─────────────────────────────────────────────────────────────────
filter_col, toggle_col = st.columns([3, 2])
name_filter = filter_col.text_input(
    "Filter species", placeholder="type to search…", label_visibility="collapsed"
)
show_all = toggle_col.checkbox("Show all (including checked)", value=True)

filtered = [
    o for o in obs_list
    if name_filter.lower() in o.get("comName", "").lower()
    and (show_all or o.get("speciesCode") not in checked)
]

st.caption(f"Showing {len(filtered)} of {len(obs_list)} species")

new_checked = set(checked)
changed     = False

for o in filtered:
    code  = o.get("speciesCode", "")
    name  = o.get("comName", code)
    sci   = o.get("sciName", "")
    dt    = o.get("obsDt", "")[:10]
    loc   = o.get("locName", "")
    cnt   = o.get("howMany")
    cnt_s = f" · {cnt}" if cnt else ""

    col_cb, col_info = st.columns([1, 8])
    ticked = col_cb.checkbox(
        "", value=code in checked,
        key=f"cb_{county_code}_{year}_{code}",
        label_visibility="collapsed",
    )
    col_info.markdown(
        f"**{name}** &nbsp; *{sci}*  \n"
        f"<small>{dt}{cnt_s} &nbsp;·&nbsp; {loc}</small>",
        unsafe_allow_html=True,
    )
    if ticked and code not in new_checked:
        new_checked.add(code);    changed = True
    elif not ticked and code in new_checked:
        new_checked.discard(code); changed = True

# ── persist on change (fire-and-forget, no rerun triggered) ───────────────────
if changed:
    st.session_state[session_key] = new_checked
    _ls_write(ls_key_val, new_checked)

# ── sidebar stats ──────────────────────────────────────────────────────────────
_stats_slot.metric(
    f"Checked this year ({county_name})",
    f"{len(new_checked)} / {len(obs_list)}",
)

# ── footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Checklist saved in your browser — no eBird login required · "
    "persists until you clear it"
)
