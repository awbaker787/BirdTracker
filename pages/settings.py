"""
Settings page — default location, state, radius, and days.
"""
import json
import traceback

import streamlit as st
from cryptography.fernet import Fernet
from streamlit_cookies_controller import CookieController
from streamlit_js_eval import get_geolocation

_FERNET_KEY = b"ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
_f = Fernet(_FERNET_KEY)
cc = CookieController()


def _log_error(ctx, exc):
    st.session_state.setdefault("_err_log", []).append(
        {"ctx": ctx, "msg": str(exc), "tb": traceback.format_exc()}
    )


def _enc(obj):
    try:
        return _f.encrypt(json.dumps(obj).encode()).decode()
    except Exception as e:
        _log_error("enc", e); return ""


def _dec(raw):
    try:
        return json.loads(_f.decrypt(raw.encode()).decode())
    except Exception:
        return {}


def _load_prefs():
    defaults = {"lat": 26.4615, "lng": -80.0728, "state": "US-FL", "dist": 25, "days": 7}
    try:
        raw = cc.get("bd_prefs")
        if raw:
            defaults.update(_dec(raw))
    except Exception as e:
        _log_error("load_prefs", e)
    return defaults


_ONE_YEAR = 365 * 24 * 3600

def _save_prefs(lat, lng, state, dist, days):
    try:
        cc.set("bd_prefs", _enc({"lat": lat, "lng": lng, "state": state,
                                  "dist": dist, "days": days}), max_age=_ONE_YEAR)
        return True
    except Exception as e:
        _log_error("save_prefs", e); return False


# ── Page ──────────────────────────────────────────────────────────────────────
st.title("Settings")
st.caption("These values pre-fill the search sidebar. Override them any time per session.")

prefs = _load_prefs()

st.subheader("Location")

if st.button("📍 Use My Current Location", use_container_width=True):
    loc = get_geolocation()
    if loc and "coords" in loc:
        st.session_state["_geo_lat"] = loc["coords"]["latitude"]
        st.session_state["_geo_lng"] = loc["coords"]["longitude"]
        st.success(f"Location detected: {st.session_state['_geo_lat']:.4f}, {st.session_state['_geo_lng']:.4f}")
    else:
        st.warning("Could not detect location — browser may have blocked access.")

c1, c2 = st.columns(2)
lat   = c1.number_input("Latitude",  value=float(st.session_state.get("_geo_lat", prefs["lat"])),  format="%.4f")
lng   = c2.number_input("Longitude", value=float(st.session_state.get("_geo_lng", prefs["lng"])), format="%.4f")
state = st.text_input("State Code", value=prefs["state"],
                       help="e.g. US-FL, US-TX, US-WA").upper()

st.subheader("Search Defaults")
dist  = st.slider("Local radius (km)", 5, 100, int(prefs["dist"]), 5)
days  = st.number_input("Default days back", min_value=1, max_value=30, value=int(prefs["days"]))

if st.button("Save Settings", type="primary", use_container_width=True):
    if _save_prefs(lat, lng, state, dist, days):
        st.success("Settings saved!")
    else:
        st.error("Save failed — see Error Log below.")

# ── Error Log ─────────────────────────────────────────────────────────────────
errors = st.session_state.get("_err_log", [])
if errors:
    st.divider()
    with st.expander(f"Error Log ({len(errors)})", expanded=True):
        for e in reversed(errors):
            st.code(f"{e['ctx']}: {e['msg']}\n\n{e['tb']}", language="python")
        if st.button("Clear"):
            st.session_state["_err_log"] = []; st.rerun()
