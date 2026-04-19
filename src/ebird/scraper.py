"""
eBird authenticated scraper.
Logs in via Cornell SSO once and scrapes the user's year list for multiple regions
in a single browser session to minimize memory usage on cloud deployments.

Requires: playwright (pip install playwright && python -m playwright install chromium)
"""
import asyncio
import datetime
import os
import re
from typing import Optional

from playwright.async_api import async_playwright


EBIRD_LOGIN_URL = (
    "https://secure.birds.cornell.edu/cassso/login"
    "?service=https%3A%2F%2Febird.org%2Flogin%2Fcas%3Fportal%3Debird"
)

# Cloud-safe Chromium flags — avoids OOM kills on Streamlit Cloud free tier.
# --no-zygote is safer than --single-process (which causes instability).
_BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-zygote",
    "--disable-extensions",
    "--disable-plugins",
    "--blink-settings=imagesEnabled=false",   # skip image loading = less RAM
]

_SPECIES_RE = re.compile(
    r'data-species-code="([^"]+)"[^>]*>.*?<span class="Heading-main">([^<]+)</span>',
    re.DOTALL,
)


def _parse_species(html: str) -> dict[str, str]:
    return {code: name for code, name in _SPECIES_RE.findall(html)}


async def _scrape_all_regions_async(
    username: str,
    password: str,
    regions: list[str],
    year: int,
) -> dict[str, dict[str, str]]:
    """
    Log in ONCE and scrape year lists for all requested regions in the same
    browser session. Returns {region: {species_code: common_name}}.
    """
    results: dict[str, dict[str, str]] = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=_BROWSER_ARGS)
        ctx = await browser.new_context(
            viewport={"width": 800, "height": 600},
            java_script_enabled=True,
        )
        page = await ctx.new_page()

        try:
            # ── Login ─────────────────────────────────────────────────────────
            await page.goto(EBIRD_LOGIN_URL, timeout=40000)
            await page.wait_for_load_state("domcontentloaded")
            await page.fill("#input-user-name", username)
            await page.fill("#input-password", password)
            await page.click("#form-submit")
            await page.wait_for_load_state("domcontentloaded", timeout=25000)

            if "ebird.org" not in page.url:
                raise RuntimeError(
                    f"Login failed — wrong username/password? (landed at {page.url})"
                )

            # ── Scrape each region with the same authenticated session ────────
            for region in regions:
                url = f"https://ebird.org/lifelist?r={region}&time=year&year={year}"
                await page.goto(url, timeout=40000)
                await page.wait_for_timeout(4000)   # allow JS to render the list
                html = await page.content()
                results[region] = _parse_species(html)

        finally:
            await browser.close()

    return results


def fetch_year_list_multi_region(
    username: str,
    password: str,
    state_code: str,
    year: int = None,
) -> dict[str, set[str]]:
    """
    Fetch year lists for world, US, and a specific state using ONE browser session.
    Returns {'world': {codes}, 'US': {codes}, state_code: {codes}}.
    """
    year = year or datetime.datetime.now().year
    regions = ["world", "US", state_code]
    raw = asyncio.run(_scrape_all_regions_async(username, password, regions, year))
    return {k: set(v.keys()) for k, v in raw.items()}


def fetch_year_list(
    username: Optional[str] = None,
    password: Optional[str] = None,
    region: str = "world",
    year: int = None,
) -> dict[str, str]:
    """Single-region convenience wrapper. Returns {species_code: common_name}."""
    username = username or os.environ.get("EBIRD_USERNAME", "")
    password = password or os.environ.get("EBIRD_PASSWORD", "")
    if not username or not password:
        raise ValueError("EBIRD_USERNAME and EBIRD_PASSWORD must be set.")
    year = year or datetime.datetime.now().year
    raw = asyncio.run(_scrape_all_regions_async(username, password, [region], year))
    return raw.get(region, {})
