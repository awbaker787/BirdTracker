"""
eBird authenticated scraper — requests-based (no browser needed).

Login flow:
  1. GET ebird.org (homepage) — establishes session cookies
  2. GET ebird.org/login        — server redirects us to Cornell CAS
  3. Parse the CAS form         — extracts lt/execution/eventId tokens
  4. POST credentials to CAS   — follows redirect back to ebird.org
"""
import datetime
import os
import re
import time
from urllib.parse import urljoin

import requests


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
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


def _parse_form(html: str, page_url: str) -> tuple[str, dict]:
    """Extract form action URL and all input field values."""
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


def _login(username: str, password: str) -> requests.Session:
    """
    Log in to eBird via Cornell SSO.
    Returns an authenticated requests.Session with eBird session cookies.
    Raises RuntimeError with a diagnostic message on any failure.
    """
    session = requests.Session()
    session.headers.update(_HEADERS)

    # ── Step 1: warm up the session on the eBird homepage ──────────────────
    # This sets initial cookies and makes the subsequent login redirect look
    # like natural browser navigation rather than a cold hit on the CAS server.
    try:
        session.get("https://ebird.org", allow_redirects=True, timeout=15)
    except Exception:
        pass  # Non-fatal — continue even if homepage is slow

    # ── Step 2: GET ebird.org/login (redirects us to Cornell CAS) ──────────
    resp = session.get("https://ebird.org/login", allow_redirects=True, timeout=25)

    if resp.status_code == 401:
        raise RuntimeError(
            f"Server returned 401 at login step. "
            f"Final URL: {resp.url} — the server may be blocking this IP range."
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Unexpected {resp.status_code} at login page. URL: {resp.url}"
        )

    # If we ended up straight on ebird.org (no CAS redirect), we may already
    # have a valid session from a prior warm-up cookie.
    if "ebird.org" in resp.url and "cassso" not in resp.url and "login" not in resp.url.lower():
        return session

    # ── Step 3: parse the CAS login form ───────────────────────────────────
    if 'name="username"' not in resp.text:
        raise RuntimeError(
            f"Could not find login form at {resp.url} "
            f"(status {resp.status_code}). "
            "eBird may have changed their login page — check the error log."
        )

    post_url, fields = _parse_form(resp.text, resp.url)
    fields["username"] = username
    fields["password"] = password
    fields["_eventId"] = fields.get("_eventId", "submit")

    # ── Step 4: POST credentials ────────────────────────────────────────────
    session.headers["Referer"] = resp.url
    resp2 = session.post(post_url, data=fields, allow_redirects=True, timeout=25)

    if resp2.status_code == 401:
        raise RuntimeError(
            f"Server returned 401 on credential POST. URL: {resp2.url}"
        )
    resp2.raise_for_status()

    if "ebird.org" not in resp2.url:
        if "cassso" in resp2.url or "login" in resp2.url.lower():
            raise RuntimeError(
                "eBird login rejected — check your username and password in Profile."
            )
        raise RuntimeError(f"Login failed. Landed at: {resp2.url}")

    return session


def _scrape_year_list(session: requests.Session, region: str, year: int) -> dict[str, str]:
    """
    Fetch the eBird year list page for one region.
    Returns {species_code: common_name}.
    """
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
