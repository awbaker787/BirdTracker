"""
eBird authenticated scraper — requests-based (no browser needed).

Logs in via Cornell SSO using a requests.Session, then calls eBird's
internal JSON API to retrieve the user's year list for each region.
No Playwright / Chromium required, so it runs fine on low-memory hosts.
"""
import datetime
import os
import re
import time

import requests


EBIRD_LOGIN_URL = (
    "https://secure.birds.cornell.edu/cassso/login"
    "?service=https%3A%2F%2Febird.org%2Flogin%2Fcas%3Fportal%3Debird"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_SPECIES_CODE_RE = re.compile(r'data-species-code="([^"]+)"')
_SPECIES_NAME_RE = re.compile(
    r'data-species-code="([^"]+)"[^>]*>.*?<span[^>]+class="Heading-main[^"]*">([^<]+)</span>',
    re.DOTALL,
)


def _extract_form_field(html: str, name: str) -> str:
    """Pull a hidden input field value from an HTML form."""
    m = re.search(
        rf'<input[^>]+name="{re.escape(name)}"[^>]+value="([^"]*)"',
        html,
    )
    if not m:
        m = re.search(
            rf'<input[^>]+value="([^"]*)"[^>]+name="{re.escape(name)}"',
            html,
        )
    return m.group(1) if m else ""


def _login(username: str, password: str) -> requests.Session:
    """
    Log in to eBird via Cornell SSO.
    Returns an authenticated requests.Session with eBird cookies set.
    """
    session = requests.Session()
    session.headers.update(_HEADERS)

    # Step 1: GET the login page to collect CSRF / execution tokens
    resp = session.get(EBIRD_LOGIN_URL, timeout=20)
    resp.raise_for_status()

    lt        = _extract_form_field(resp.text, "lt")
    execution = _extract_form_field(resp.text, "execution")

    # Step 2: POST credentials
    post_data = {
        "username":  username,
        "password":  password,
        "lt":        lt,
        "execution": execution,
        "_eventId":  "submit",
        "submit":    "Sign in",
    }
    resp2 = session.post(resp.url, data=post_data, allow_redirects=True, timeout=20)
    resp2.raise_for_status()

    if "ebird.org" not in resp2.url:
        raise RuntimeError(
            f"eBird login failed — check username/password. (Landed at: {resp2.url})"
        )

    return session


def _scrape_year_list(
    session: requests.Session,
    region: str,
    year: int,
) -> dict[str, str]:
    """
    Fetch the year list page for one region and parse species from the HTML.
    Returns {species_code: common_name}.
    """
    url = f"https://ebird.org/lifelist?r={region}&time=year&year={year}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    html = resp.text

    entries = _SPECIES_NAME_RE.findall(html)
    if entries:
        return {code: name for code, name in entries}

    # Fallback: if the page is JS-rendered, we may only get species codes
    # without names. Return codes with empty names so the needs filter still works.
    codes = _SPECIES_CODE_RE.findall(html)
    return {code: "" for code in codes}


def fetch_year_list_multi_region(
    username: str,
    password: str,
    state_code: str,
    year: int = None,
) -> dict[str, set[str]]:
    """
    Log in once, scrape world / US / state year lists.
    Returns {'world': {codes}, 'US': {codes}, state_code: {codes}}.
    """
    year = year or datetime.datetime.now().year
    session = _login(username, password)

    results: dict[str, set[str]] = {}
    for region in ["world", "US", state_code]:
        data = _scrape_year_list(session, region, year)
        results[region] = set(data.keys())
        time.sleep(0.5)   # be polite to eBird's servers

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
