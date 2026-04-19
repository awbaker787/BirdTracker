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
    """Return the shared CookieController instance (key='bd_cc')."""
    return CookieController(key="bd_cc")


def cc_get(cc: CookieController, name: str):
    """
    Safe cc.get() — returns None if the controller is not yet initialised
    instead of raising TypeError.
    """
    try:
        return cc.get(name)
    except TypeError:
        return None


def cc_set(cc: CookieController, name: str, value: str, **kwargs) -> bool:
    """
    Safe cc.set() — returns False if the controller is not yet initialised.
    """
    try:
        cc.set(name, value, **kwargs)
        return True
    except TypeError:
        return False


def cc_remove(cc: CookieController, name: str) -> bool:
    """Safe cc.remove() — returns False on TypeError."""
    try:
        cc.remove(name)
        return True
    except TypeError:
        return False
