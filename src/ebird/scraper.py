"""
eBird authenticated scraper.

Uses curl_cffi to impersonate Chrome's TLS fingerprint so Cornell's CAS
server doesn't reject the request.  Falls back to plain requests if
curl_cffi is unavailable (e.g. local dev without the wheel).

Login flow:
  1. GET ebird.org            — warms up the session / gets cookies
  2. GET ebird.org/login      — server 302s us to Cornell CAS
  3. Parse CAS form           — extracts lt / execution / _eventId tokens
  4. POST credentials to CAS  — redirects back to ebird.org on success
"""
import datetime
import os
import re
import time
from urllib.parse import urljoin

try:
    from curl_cffi.requests import Session as _CurlSession
    _HAVE_CURL_CFFI = True
except ImportError:
    _HAVE_CURL_CFFI = False
    import requests as _requests

_CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_HEADERS = {
    "User-Agent":      _CHROME_UA,
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}

_SPECIES_CODE_RE = re.compile(r'data-species-code="([^"]+)"')
_SPECIES_NAME_RE = re.compile(
    r'data-species-code="([^"]+)"[^>]*>.*?<span[^>]+class="Heading-main[^"]*">([^<]+)</span>',
    re.DOTALL,
)


class LoginError(RuntimeError):
    """Raised when eBird authentication fails (wrong password, IP block, etc.)."""


def _make_session():
    """Return a session that impersonates Chrome at the TLS level if possible."""
    if _HAVE_CURL_CFFI:
        # impersonate="chrome124" sets the exact TLS cipher / extension order
        # that Chrome 124 uses — defeats TLS-fingerprint-based bot detection.
        s = _CurlSession(impersonate="chrome124")
        s.headers.update(_HEADERS)
    else:
        s = _requests.Session()
        s.headers.update(_HEADERS)
    return s


def _parse_form(html: str, page_url: str) -> tuple[str, dict]:
    """Extract the form action URL and all <input> values."""
    action_m = re.search(r'<form[^>]+action="([^"]+)"', html)
    if action_m:
        action = action_m.group(1).replace("&amp;", "&")
        post_url = urljoin(page_url, action)
    else:
        post_url = page_url

    fields: dict[str, str] = {}
    for tag in re.findall(r"<input[^>]+>", html):
        name_m  = re.search(r'\bname="([^"]+)"',  tag)
        value_m = re.search(r'\bvalue="([^"]*)"', tag)
        if name_m:
            fields[name_m.group(1)] = value_m.group(1) if value_m else ""
    return post_url, fields


def _login(username: str, password: str):
    """
    Log in to eBird via Cornell SSO.
    Returns an authenticated session.
    Raises LoginError on auth failure or network/IP block.
    """
    session = _make_session()

    # Step 1: warm-up visit to establish session cookies
    try:
        session.get("https://ebird.org", allow_redirects=True, timeout=15)
    except Exception:
        pass

    # Step 2: get the login page (eBird redirects to Cornell CAS)
    try:
        resp = session.get("https://ebird.org/login", allow_redirects=True, timeout=25)
    except Exception as exc:
        raise LoginError(f"Could not reach eBird login page: {exc}") from exc

    if resp.status_code == 401:
        raise LoginError(
            f"eBird server returned 401 (URL: {resp.url}). "
            "This host may be IP-blocked by Cornell CAS."
        )
    if resp.status_code != 200:
        raise LoginError(
            f"Unexpected HTTP {resp.status_code} at login page (URL: {resp.url})."
        )

    # If we landed on eBird proper without hitting CAS, session is already live
    if "ebird.org" in resp.url and "cassso" not in resp.url and "login" not in resp.url:
        return session

    # Step 3: parse the CAS login form
    if 'name="username"' not in resp.text:
        raise LoginError(
            f"No login form found at {resp.url} (status {resp.status_code}). "
            "eBird may have changed their login page."
        )

    post_url, fields = _parse_form(resp.text, resp.url)
    fields["username"] = username
    fields["password"] = password
    fields["_eventId"] = fields.get("_eventId", "submit")

    # Step 4: POST credentials
    session.headers.update({"Referer": resp.url})
    try:
        resp2 = session.post(post_url, data=fields, allow_redirects=True, timeout=25)
    except Exception as exc:
        raise LoginError(f"Credential POST failed: {exc}") from exc

    if resp2.status_code == 401:
        raise LoginError(f"Login POST returned 401 (URL: {resp2.url}).")

    try:
        resp2.raise_for_status()
    except Exception as exc:
        raise LoginError(str(exc)) from exc

    if "ebird.org" not in resp2.url:
        if "cassso" in resp2.url or "login" in resp2.url.lower():
            raise LoginError(
                "eBird rejected the credentials. "
                "Check your username and password in Profile."
            )
        raise LoginError(f"Login failed — landed at: {resp2.url}")

    return session


def _scrape_year_list(session, region: str, year: int) -> dict[str, str]:
    """Fetch the eBird year list page for one region. Returns {code: name}."""
    url = f"https://ebird.org/lifelist?r={region}&time=year&year={year}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    html = resp.text

    entries = _SPECIES_NAME_RE.findall(html)
    if entries:
        return {code: name for code, name in entries}

    codes = _SPECIES_CODE_RE.findall(html)
    return {code: "" for code in codes}


def fetch_year_list_multi_region(
    username: str,
    password: str,
    state_code: str,
    year: int = None,
) -> dict[str, set[str]]:
    """
    Log in once and scrape world / US / state year lists.
    Returns {'world': {codes}, 'US': {codes}, state_code: {codes}}.
    Raises LoginError if authentication fails.
    """
    year = year or datetime.datetime.now().year
    session = _login(username, password)

    results: dict[str, set[str]] = {}
    for region in ["world", "US", state_code]:
        data = _scrape_year_list(session, region, year)
        results[region] = set(data.keys())
        time.sleep(0.5)

    return results


def fetch_year_list(
    username: str = None,
    password: str = None,
    region: str = "world",
    year: int = None,
) -> dict[str, str]:
    """Single-region convenience wrapper. Returns {species_code: common_name}."""
    username = username or os.environ.get("EBIRD_USERNAME", "")
    password = password or os.environ.get("EBIRD_PASSWORD", "")
    if not username or not password:
        raise ValueError("EBIRD_USERNAME and EBIRD_PASSWORD must be set.")
    year = year or datetime.datetime.now().year
    session = _login(username, password)
    return _scrape_year_list(session, region, year)
