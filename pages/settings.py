"""
Settings page — default location, state, radius, and days.
"""
import traceback

import streamlit as st
from cryptography.fernet import Fernet
from streamlit_js_eval import get_geolocation

from src.ui.cookies import cc_get, cc_set, get_cc

_FERNET_KEY = b"ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
_f = Fernet(_FERNET_KEY)
cc = get_cc()
_ONE_YEAR = 365 * 24 * 3600


def _log_error(ctx, exc):
    st.session_state.setdefault("_err_log", []).append(
        {"ctx": ctx, "msg": str(exc), "tb": traceback.format_exc()}
    )


def _enc(obj):
    import json
    try:
        return _f.encrypt(json.dumps(obj).encode()).decode()
    except Exception as e:
        _log_error("enc", e); return ""


def _dec(raw):
    import json
    try:
        return json.loads(_f.decrypt(raw.encode()).decode())
    except Exception:
        return {}


def _load_prefs():
    defaults = {"lat": 26.4615, "lng": -80.0728, "state": "US-FL", "dist": 25, "days": 7}
    try:
        raw = cc_get(cc, "bd_prefs")
        if raw:
            defaults.update(_dec(raw))
    except Exception as e:
        _log_error("load_prefs", e)
    return defaults


def _save_prefs(lat, lng, state, dist, days):
    try:
        ok = cc_set(cc, "bd_prefs", _enc({"lat": lat, "lng": lng, "state": state,
                                           "dist": dist, "days": days}), max_age=_ONE_YEAR)
        if not ok:
            _log_error("save_prefs", RuntimeError("Cookie controller not ready — please try again."))
        return ok
    except Exception as e:
        _log_error("save_prefs", e); return False


# ── Page ──────────────────────────────────────────────────────────────────────
st.title("Settings")
st.caption("These values pre-fill the search sidebar. Override them any time per session.")

prefs = _load_prefs()

st.subheader("Location")

# get_geolocation() is async — must live outside the button block
if st.session_state.get("_want_geo"):
    _geo = get_geolocation()
    if _geo and "coords" in _geo:
        st.session_state["_geo_lat"] = _geo["coords"]["latitude"]
        st.session_state["_geo_lng"] = _geo["coords"]["longitude"]
        st.session_state.pop("_want_geo", None)
        st.success(f"Location detected: {st.session_state['_geo_lat']:.4f}, {st.session_state['_geo_lng']:.4f}")

if st.button("📍 Use My Current Location", use_container_width=True):
    st.session_state["_want_geo"] = True
    st.rerun()
elif st.session_state.get("_want_geo"):
    st.info("Waiting for browser location…")

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
