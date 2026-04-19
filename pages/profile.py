"""
Profile & Settings page.
Credentials + search defaults stored as two encrypted JSON cookies.
"""
import json

import extra_streamlit_components as stx
import streamlit as st
from cryptography.fernet import Fernet

_FERNET_KEY = b"ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
_f = Fernet(_FERNET_KEY)

cm = stx.CookieManager(key="bd")

_MAX_AGE = 365 * 24 * 3600  # 1 year


def _enc(obj: dict) -> str:
    return _f.encrypt(json.dumps(obj).encode()).decode()


def _dec(raw: str) -> dict:
    try:
        return json.loads(_f.decrypt(raw.encode()).decode())
    except Exception:
        return {}


def _load_creds() -> tuple[str, str, str]:
    raw = cm.get("bd_creds")
    d = _dec(raw) if raw else {}
    return d.get("u", ""), d.get("p", ""), d.get("k", "")


def _save_creds(u: str, p: str, k: str) -> None:
    cm.set("bd_creds", _enc({"u": u, "p": p, "k": k}), max_age=_MAX_AGE)


def _load_prefs() -> dict:
    raw = cm.get("bd_prefs")
    defaults = {"lat": 26.4615, "lng": -80.0728, "state": "US-FL", "dist": 25, "days": 7}
    if raw:
        defaults.update(_dec(raw))
    return defaults


def _save_prefs(lat: float, lng: float, state: str, dist: int, days: int) -> None:
    cm.set("bd_prefs", _enc({"lat": lat, "lng": lng, "state": state,
                              "dist": dist, "days": days}), max_age=_MAX_AGE)


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
            _save_creds(u2, p2, k2)
            st.success("Saved!")
            st.rerun()
        if c2.button("Clear & log out", use_container_width=True):
            cm.delete("bd_creds")
            st.rerun()
else:
    st.info("Enter your eBird credentials. They'll be encrypted and saved in your browser.")
    u2 = st.text_input("Username", key="u2")
    p2 = st.text_input("Password", type="password", key="p2")
    k2 = st.text_input("API Key",  type="password", key="k2",
                        help="Free at ebird.org/api/keygen")
    if st.button("Save & remember me", type="primary", use_container_width=True):
        if u2 and p2 and k2:
            _save_creds(u2, p2, k2)
            st.success("Credentials saved! Go to **Find My Needs** to search.")
            st.rerun()
        else:
            st.warning("Fill in all three fields.")

# ── Search Defaults ────────────────────────────────────────────────────────────
st.divider()
st.subheader("Search Defaults")
st.caption("These pre-fill the search sidebar. You can still override them each session.")

prefs = _load_prefs()
c1, c2 = st.columns(2)
lat   = c1.number_input("Latitude",  value=float(prefs["lat"]),  format="%.4f")
lng   = c2.number_input("Longitude", value=float(prefs["lng"]), format="%.4f")
state = st.text_input("State Code", value=prefs["state"],
                       help="e.g. US-FL, US-TX, US-WA").upper()
dist  = st.slider("Default radius (km)", 5, 100, int(prefs["dist"]), 5)
days  = st.number_input("Default days back", min_value=1, max_value=30, value=int(prefs["days"]))

if st.button("Save defaults", type="primary", use_container_width=True):
    _save_prefs(lat, lng, state, dist, days)
    st.success("Search defaults saved!")
