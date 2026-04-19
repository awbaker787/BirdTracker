"""
eBird authenticated scraper — requests-based (no browser needed).

Logs in via Cornell SSO by properly parsing the login form action URL
and all hidden CSRF fields, then scrapes year lists for each region.
"""
import datetime
import os
import re
import time
from urllib.parse import urljoin

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
    """
    Extract the form action URL and all input field values.
    Returns (post_url, {field_name: value}).
    """
    # Form action
    action_m = re.search(r'<form[^>]+action="([^"]+)"', html)
    if action_m:
        action = action_m.group(1).replace("&amp;", "&")
        post_url = urljoin(page_url, action)
    else:
        post_url = page_url

    # All input fields (hidden + visible)
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
    """
    session = requests.Session()
    session.headers.update(_HEADERS)

    # Step 1: GET login page
    resp = session.get(EBIRD_LOGIN_URL, timeout=25)
    resp.raise_for_status()

    # Step 2: Parse form — action URL contains lt token in query string
    post_url, fields = _parse_form(resp.text, resp.url)

    # Step 3: Fill credentials (CAS field names are 'username' / 'password')
    fields["username"]   = username
    fields["password"]   = password
    fields["_eventId"]   = fields.get("_eventId", "submit")

    # Step 4: POST with Referer so the server accepts the submission
    session.headers["Referer"] = resp.url
    resp2 = session.post(post_url, data=fields, allow_redirects=True, timeout=25)
    resp2.raise_for_status()

    if "ebird.org" not in resp2.url:
        # Check if login page was returned again (wrong password)
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

    # Fallback: JS-rendered page may only embed species codes
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
