"""
Profile & Settings page.
Credentials + search defaults stored as two encrypted JSON cookies.
"""
import json
import traceback

import streamlit as st
from cryptography.fernet import Fernet
from streamlit_cookies_controller import CookieController

_FERNET_KEY = b"ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
_f = Fernet(_FERNET_KEY)

cc = CookieController()

_MAX_AGE = 365 * 24 * 3600  # 1 year


# ── Error log helpers ──────────────────────────────────────────────────────────
def _log_error(context: str, exc: Exception) -> None:
    if "_err_log" not in st.session_state:
        st.session_state["_err_log"] = []
    st.session_state["_err_log"].append({
        "ctx": context,
        "msg": str(exc),
        "tb":  traceback.format_exc(),
    })


# ── Cookie helpers ─────────────────────────────────────────────────────────────
def _enc(obj: dict) -> str:
    try:
        return _f.encrypt(json.dumps(obj).encode()).decode()
    except Exception as e:
        _log_error("_enc", e)
        return ""


def _dec(raw: str) -> dict:
    try:
        return json.loads(_f.decrypt(raw.encode()).decode())
    except Exception:
        return {}


def _load_creds() -> tuple[str, str, str]:
    try:
        raw = cc.get("bd_creds")
        d = _dec(raw) if raw else {}
        return d.get("u", ""), d.get("p", ""), d.get("k", "")
    except Exception as e:
        _log_error("_load_creds", e)
        return "", "", ""


def _save_creds(u: str, p: str, k: str) -> bool:
    try:
        cc.set("bd_creds", _enc({"u": u, "p": p, "k": k}))
        return True
    except Exception as e:
        _log_error("_save_creds", e)
        return False


def _load_prefs() -> dict:
    defaults = {"lat": 26.4615, "lng": -80.0728, "state": "US-FL", "dist": 25, "days": 7}
    try:
        raw = cc.get("bd_prefs")
        if raw:
            defaults.update(_dec(raw))
    except Exception as e:
        _log_error("_load_prefs", e)
    return defaults


def _save_prefs(lat, lng, state, dist, days) -> bool:
    try:
        cc.set("bd_prefs", _enc({"lat": lat, "lng": lng, "state": state,
                                  "dist": dist, "days": days}))
        return True
    except Exception as e:
        _log_error("_save_prefs", e)
        return False


# ── Page ──────────────────────────────────────────────────────────────────────
st.title("Profile & Settings")

# ── Credentials ───────────────────────────────────────────────────────────────
st.subheader("eBird Credentials")
cu, cp, ck = _load_creds()

if cu and cp and ck:
    st.success(f"Connected as **{cu}**")
    with st.expander("Edit credentials"):
        u2 = st.text_input("Username", value=cu, key="u2")
        p2 = st.text_input("Password", value=cp, type="password", key="p2")
        k2 = st.text_input("API Key",  value=ck, type="password", key="k2",
                            help="Free at ebird.org/api/keygen")
        c1, c2 = st.columns(2)
        if c1.button("Save changes", type="primary", use_container_width=True):
            ok = _save_creds(u2, p2, k2)
            if ok:
                st.success("Saved!")
                st.rerun()
            else:
                st.error("Save failed — check Error Log below.")
        if c2.button("Clear & log out", use_container_width=True):
            try:
                cc.remove("bd_creds")
            except Exception as e:
                _log_error("clear_creds", e)
            st.rerun()
else:
    st.info("Enter your eBird credentials. They'll be encrypted and saved in your browser.")
    u2 = st.text_input("Username", key="u2")
    p2 = st.text_input("Password", type="password", key="p2")
    k2 = st.text_input("API Key",  type="password", key="k2",
                        help="Free at ebird.org/api/keygen")
    if st.button("Save & remember me", type="primary", use_container_width=True):
        if u2 and p2 and k2:
            ok = _save_creds(u2, p2, k2)
            if ok:
                st.success("Credentials saved! Go to **Find My Needs** to search.")
                st.rerun()
            else:
                st.error("Save failed — check Error Log below.")
        else:
            st.warning("Fill in all three fields.")

# ── Search Defaults ────────────────────────────────────────────────────────────
st.divider()
st.subheader("Search Defaults")
st.caption("Pre-fill the search sidebar. You can still override per session.")

prefs = _load_prefs()
c1, c2 = st.columns(2)
lat   = c1.number_input("Latitude",  value=float(prefs["lat"]),  format="%.4f")
lng   = c2.number_input("Longitude", value=float(prefs["lng"]), format="%.4f")
state = st.text_input("State Code", value=prefs["state"],
                       help="e.g. US-FL, US-TX, US-WA").upper()
dist  = st.slider("Default radius (km)", 5, 100, int(prefs["dist"]), 5)
days  = st.number_input("Default days back", min_value=1, max_value=30, value=int(prefs["days"]))

if st.button("Save defaults", type="primary", use_container_width=True):
    ok = _save_prefs(lat, lng, state, dist, days)
    if ok:
        st.success("Search defaults saved!")
    else:
        st.error("Save failed — check Error Log below.")

# ── Error Log ─────────────────────────────────────────────────────────────────
errors = st.session_state.get("_err_log", [])
if errors:
    st.divider()
    with st.expander(f"Error Log ({len(errors)} entries)", expanded=True):
        for i, e in enumerate(reversed(errors)):
            st.markdown(f"**{e['ctx']}**: `{e['msg']}`")
            st.code(e["tb"], language="python")
        if st.button("Clear error log"):
            st.session_state["_err_log"] = []
            st.rerun()
