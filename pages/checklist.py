"""
Field Checklist — manual per-county bird tracker.

Shows birds recently reported in any county (via public eBird API — no login
required).  User checks off what they see.  Checklist is saved per county+year
in browser localStorage and persists across sessions completely independently
of eBird scraping or personal-list sync.
"""
import json
from datetime import datetime

import folium
import streamlit as st
from streamlit_folium import st_folium
from streamlit_js_eval import st_javascript

from src.ebird.client import EBirdClient
from src.ui.cookies import cc_get, get_cc

_FERNET_KEY = b"ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
from cryptography.fernet import Fernet
_f = Fernet(_FERNET_KEY)

cc = get_cc()


# ── helpers ────────────────────────────────────────────────────────────────────
def _dec_json(raw):
    try:
        import json as _j
        return _j.loads(_f.decrypt(raw.encode()).decode())
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


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def _counties(api_key: str, state_code: str) -> list[dict]:
    """Return [{code, name}] for all counties in a state."""
    client = EBirdClient(api_key)
    return client._get(f"/ref/region/list/subnational2/{state_code}")


@st.cache_data(ttl=3600, show_spinner=False)
def _recent_obs(api_key: str, county_code: str, days_back: int) -> list[dict]:
    """Recent observations in the county, deduped to one per species."""
    client = EBirdClient(api_key)
    obs = client.recent_observations_in_region(county_code, days_back=days_back, max_results=3000)
    seen = {}
    for o in obs:
        code = o.get("speciesCode", "")
        if not code or "/" in o.get("comName", ""):
            continue
        if code not in seen or o.get("obsDt", "") > seen[code].get("obsDt", ""):
            seen[code] = o
    return sorted(seen.values(), key=lambda x: x.get("comName", ""))


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def _hotspots(api_key: str, county_code: str) -> list[dict]:
    client = EBirdClient(api_key)
    return client._get(f"/ref/hotspot/{county_code}?fmt=json") or []


# ── localStorage helpers ───────────────────────────────────────────────────────
def _ls_key(county_code: str, year: int) -> str:
    return f"bd_cl_{county_code.replace('-', '_')}_{year}"

def _ls_read(ls_key: str):
    """Returns Python list on 2nd+ render, None on first render."""
    return st_javascript(f"JSON.parse(localStorage.getItem('{ls_key}') || 'null')")

def _ls_write(ls_key: str, codes: set):
    st_javascript(
        f"localStorage.setItem('{ls_key}', JSON.stringify({json.dumps(list(codes))}));"
    )

def _ls_clear(ls_key: str):
    st_javascript(f"localStorage.removeItem('{ls_key}');")


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

    with st.spinner("Loading counties..."):
        try:
            county_list = _counties(api_key, state_code)
        except Exception as e:
            st.error(f"Could not load counties: {e}")
            st.stop()

    if not county_list:
        st.error("No counties found for that state code.")
        st.stop()

    county_names  = [c["name"] for c in county_list]
    county_codes  = [c["code"] for c in county_list]
    county_idx    = st.selectbox(
        "County", range(len(county_names)),
        format_func=lambda i: county_names[i]
    )
    county_code = county_codes[county_idx]
    county_name = county_names[county_idx]

    days_back = st.slider("Show birds reported in last", 1, 90, 30, 1, format="%d days")

    st.divider()
    st.subheader("Checklist Stats")
    _stats_placeholder = st.empty()   # filled after we know the checked set

    st.divider()
    if st.button("Clear checklist for this county", use_container_width=True):
        _ls_clear(_ls_key(county_code, year))
        sk = f"_cl_{county_code}_{year}"
        st.session_state.pop(sk, None)
        st.session_state.pop(f"_cl_ready_{county_code}_{year}", None)
        st.rerun()

# ── load checklist from localStorage ──────────────────────────────────────────
ls_key_val   = _ls_key(county_code, year)
session_key  = f"_cl_{county_code}_{year}"
ready_key    = f"_cl_ready_{county_code}_{year}"

if not st.session_state.get(ready_key):
    ls_raw = _ls_read(ls_key_val)
    if ls_raw is None:
        # Component hasn't sent data yet — wait one render
        st.info("Loading saved checklist…")
        st.stop()
    st.session_state[session_key] = set(ls_raw) if ls_raw else set()
    st.session_state[ready_key]   = True

checked: set = st.session_state[session_key]

# ── fetch species + observations ───────────────────────────────────────────────
st.title(f"Field Checklist · {county_name}")
st.caption(f"{state_code} · {year} · birds reported in the last {days_back} day(s)")

with st.spinner("Fetching recent birds…"):
    try:
        obs_list = _recent_obs(api_key, county_code, days_back)
    except Exception as e:
        st.error(f"eBird API error: {e}")
        st.stop()

if not obs_list:
    st.info("No observations found for this county and time window.")
    st.stop()

# ── map ────────────────────────────────────────────────────────────────────────
lats = [o["lat"] for o in obs_list if "lat" in o]
lngs = [o["lng"] for o in obs_list if "lng" in o]
center_lat = sum(lats) / len(lats) if lats else _prefs["lat"]
center_lng = sum(lngs) / len(lngs) if lngs else _prefs["lng"]

m = folium.Map(location=[center_lat, center_lng], zoom_start=10,
               tiles="OpenStreetMap")
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri", name="Satellite", overlay=False, control=True
).add_to(m)

for o in obs_list:
    if "lat" not in o:
        continue
    code   = o.get("speciesCode", "")
    name   = o.get("comName", code)
    is_ckd = code in checked
    color  = "green" if is_ckd else "blue"
    folium.CircleMarker(
        location=[o["lat"], o["lng"]],
        radius=5,
        color=color,
        fill=True,
        fill_opacity=0.7,
        popup=folium.Popup(
            f"<b>{name}</b><br>{o.get('locName','')}<br>{o.get('obsDt','')}"
            + (" ✓" if is_ckd else ""),
            max_width=220,
        ),
    ).add_to(m)

folium.LayerControl().add_to(m)
st_folium(m, use_container_width=True, height=380, returned_objects=[])
st.divider()

# ── checklist ─────────────────────────────────────────────────────────────────
filter_col, toggle_col = st.columns([3, 2])
name_filter  = filter_col.text_input("Filter species", placeholder="type to search…",
                                     label_visibility="collapsed")
show_all     = toggle_col.checkbox("Show all (including checked)", value=True)

filtered = [
    o for o in obs_list
    if name_filter.lower() in o.get("comName", "").lower()
    and (show_all or o.get("speciesCode") not in checked)
]

st.caption(f"Showing {len(filtered)} of {len(obs_list)} species")

new_checked = set(checked)   # working copy
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
    newly = col_cb.checkbox("", value=code in checked, key=f"cb_{county_code}_{year}_{code}",
                            label_visibility="collapsed")
    col_info.markdown(
        f"**{name}** &nbsp; *{sci}*  \n"
        f"<small>{dt}{cnt_s} &nbsp;·&nbsp; {loc}</small>",
        unsafe_allow_html=True,
    )
    if newly and code not in new_checked:
        new_checked.add(code);  changed = True
    elif not newly and code in new_checked:
        new_checked.discard(code); changed = True

# ── persist on change ─────────────────────────────────────────────────────────
if changed:
    st.session_state[session_key] = new_checked
    _ls_write(ls_key_val, new_checked)

# ── sidebar stats (now we know checked) ───────────────────────────────────────
total   = len(obs_list)
n_ckd   = len(new_checked)
_stats_placeholder.metric(f"Checked this year ({county_name})", f"{n_ckd} / {total}")

# ── footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Checklist saved locally in your browser · no eBird login required · "
    "data persists until you clear it"
)
