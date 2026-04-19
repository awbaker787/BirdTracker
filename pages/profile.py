"""
Profile & Settings page.
Manages eBird credentials and search defaults — all stored as encrypted browser cookies.
"""
import extra_streamlit_components as stx
import streamlit as st
from cryptography.fernet import Fernet

_FERNET_KEY = b"ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
_f = Fernet(_FERNET_KEY)


def _enc(s: str) -> str:
    return _f.encrypt(s.encode()).decode()


def _dec(s: str) -> str:
    try:
        return _f.decrypt(s.encode()).decode()
    except Exception:
        return ""


cm = stx.CookieManager(key="bd")


def _get(name: str) -> str:
    raw = cm.get(name)
    return _dec(raw) if raw else ""


def _set(name: str, value: str) -> None:
    cm.set(name, _enc(value), max_age=365 * 24 * 3600)


# ── Page ──────────────────────────────────────────────────────────────────────
st.title("Profile & Settings")

# ── Credentials ───────────────────────────────────────────────────────────────
st.subheader("eBird Credentials")
cu = _get("bd_username")
cp = _get("bd_password")
ck = _get("bd_apikey")

if cu and cp and ck:
    st.success(f"Connected as **{cu}**")
    with st.expander("Edit credentials"):
        u2 = st.text_input("Username", value=cu, key="u2")
        p2 = st.text_input("Password", value=cp, type="password", key="p2")
        k2 = st.text_input("API Key",  value=ck, type="password", key="k2",
                            help="Free at ebird.org/api/keygen")
        c1, c2 = st.columns(2)
        if c1.button("Save changes", type="primary", use_container_width=True):
            _set("bd_username", u2)
            _set("bd_password", p2)
            _set("bd_apikey",   k2)
            st.success("Saved!")
            st.rerun()
        if c2.button("Clear & log out", use_container_width=True):
            for n in ("bd_username", "bd_password", "bd_apikey"):
                cm.delete(n)
            st.rerun()
else:
    st.info("Enter your eBird credentials. They'll be encrypted and saved in your browser.")
    u2 = st.text_input("Username", key="u2")
    p2 = st.text_input("Password", type="password", key="p2")
    k2 = st.text_input("API Key",  type="password", key="k2",
                        help="Free at ebird.org/api/keygen")
    if st.button("Save & remember me", type="primary", use_container_width=True):
        if u2 and p2 and k2:
            _set("bd_username", u2)
            _set("bd_password", p2)
            _set("bd_apikey",   k2)
            st.success("Credentials saved! Go to **Find My Needs** to search.")
            st.rerun()
        else:
            st.warning("Fill in all three fields.")

# ── Search Defaults ────────────────────────────────────────────────────────────
st.divider()
st.subheader("Search Defaults")
st.caption("These pre-fill the search sidebar. You can still override them each session.")

c1, c2 = st.columns(2)
lat   = c1.number_input("Latitude",  value=float(_get("bd_lat")  or "26.4615"), format="%.4f")
lng   = c2.number_input("Longitude", value=float(_get("bd_lng")  or "-80.0728"), format="%.4f")
state = st.text_input("State Code", value=_get("bd_state") or "US-FL",
                       help="e.g. US-FL, US-TX, US-WA").upper()
dist  = st.slider("Default radius (km)", 5, 100, int(_get("bd_dist") or "25"), 5)
days  = st.number_input("Default days back", min_value=1, max_value=30,
                         value=int(_get("bd_days") or "7"))

if st.button("Save defaults", type="primary", use_container_width=True):
    for name, val in [("bd_lat", str(lat)), ("bd_lng", str(lng)),
                      ("bd_state", state), ("bd_dist", str(dist)), ("bd_days", str(days))]:
        _set(name, val)
    st.success("Search defaults saved!")
