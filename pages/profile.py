"""
Profile page — eBird credentials only.
"""
import json
import traceback

import streamlit as st
from cryptography.fernet import Fernet
from streamlit_cookies_controller import CookieController

from src.ebird.scraper import _login

_FERNET_KEY = b"ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="
_f = Fernet(_FERNET_KEY)
cc = CookieController(key="bd_cc")


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


def _load_creds():
    try:
        raw = cc.get("bd_creds")
        d = _dec(raw) if raw else {}
        return d.get("u", ""), d.get("p", ""), d.get("k", "")
    except Exception as e:
        _log_error("load_creds", e); return "", "", ""


_ONE_YEAR = 365 * 24 * 3600

def _save_creds(u, p, k):
    try:
        cc.set("bd_creds", _enc({"u": u, "p": p, "k": k}), max_age=_ONE_YEAR); return True
    except Exception as e:
        _log_error("save_creds", e); return False


def _test_login(u, p):
    try:
        _login(u, p)
        return True, None
    except Exception as e:
        return False, str(e)


# ── Page ──────────────────────────────────────────────────────────────────────
st.title("Profile")
st.subheader("eBird Credentials")

cu, cp, ck = _load_creds()

if cu and cp and ck:
    st.success(f"Connected as **{cu}**")

    c_test, c_edit = st.columns(2)
    if c_test.button("Test Login", use_container_width=True):
        with st.spinner("Testing eBird login..."):
            ok, err = _test_login(cu, cp)
        if ok:
            st.success("Login successful — credentials are working.")
        else:
            st.error(f"Login failed: {err}")

    with st.expander("Edit credentials"):
        u2 = st.text_input("Username", value=cu, key="u2")
        p2 = st.text_input("Password", value=cp, type="password", key="p2")
        k2 = st.text_input("API Key",  value=ck, type="password", key="k2",
                            help="Free at ebird.org/api/keygen")
        col1, col2, col3 = st.columns(3)
        if col1.button("Save changes", type="primary", use_container_width=True):
            if _save_creds(u2, p2, k2):
                st.success("Saved!"); st.rerun()
            else:
                st.error("Save failed — see Error Log below.")
        if col2.button("Test", use_container_width=True):
            with st.spinner("Testing..."):
                ok, err = _test_login(u2, p2)
            if ok:
                st.success("Login successful.")
            else:
                st.error(f"Login failed: {err}")
        if col3.button("Clear & log out", use_container_width=True):
            try:
                cc.remove("bd_creds")
            except Exception as e:
                _log_error("clear_creds", e)
            st.rerun()
else:
    st.info("Enter your eBird credentials. Saved encrypted in your browser — never re-enter them.")
    u2 = st.text_input("Username", key="u2")
    p2 = st.text_input("Password", type="password", key="p2")
    k2 = st.text_input("API Key",  type="password", key="k2",
                        help="Free at ebird.org/api/keygen")
    if st.button("Save & remember me", type="primary", use_container_width=True):
        if u2 and p2 and k2:
            if _save_creds(u2, p2, k2):
                st.success("Saved! Head to **Find My Needs** to search."); st.rerun()
            else:
                st.error("Save failed — see Error Log below.")
        else:
            st.warning("Fill in all three fields.")

# ── Error Log ─────────────────────────────────────────────────────────────────
errors = st.session_state.get("_err_log", [])
if errors:
    st.divider()
    with st.expander(f"Error Log ({len(errors)})", expanded=True):
        for e in reversed(errors):
            st.code(f"{e['ctx']}: {e['msg']}\n\n{e['tb']}", language="python")
        if st.button("Clear"):
            st.session_state["_err_log"] = []; st.rerun()
