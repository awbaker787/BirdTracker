"""
Thin wrapper around CookieController that handles the async-init timing issue.

streamlit-cookies-controller uses a React component to read/write browser cookies.
On the very first render the Python-side __cookies dict is None; calling .get()
or .set() raises TypeError.  This module provides safe wrappers that return
graceful defaults while the component initialises.
"""
import streamlit as st
from streamlit_cookies_controller import CookieController


def get_cc() -> CookieController:
    """Return the CookieController instance created in app.py.

    app.py creates CookieController(key='bd_cc') once per render and stores it
    in st.session_state['_cc_instance'].  Pages must NOT create their own
    instance with the same key — Streamlit raises StreamlitAPIException for
    duplicate widget keys within a single render cycle.
    """
    return st.session_state.get("_cc_instance")


def cc_get(cc: CookieController, name: str):
    """Safe cc.get() — returns None if controller is None or not yet ready."""
    if cc is None:
        return None
    try:
        return cc.get(name)
    except TypeError:
        return None


def cc_set(cc: CookieController, name: str, value: str, **kwargs) -> bool:
    """Safe cc.set() — returns False if controller is None or not yet ready."""
    if cc is None:
        return False
    try:
        cc.set(name, value, **kwargs)
        return True
    except TypeError:
        return False


def cc_remove(cc: CookieController, name: str) -> bool:
    """Safe cc.remove() — returns False if controller is None or not yet ready."""
    if cc is None:
        return False
    try:
        cc.remove(name)
        return True
    except TypeError:
        return False
