"""
eBird authenticated scraper.
Logs in via Cornell SSO and scrapes the user's year list for any region.

Requires: playwright (pip install playwright && python -m playwright install chromium)
"""
import asyncio
import os
import re
from typing import Optional

from playwright.async_api import async_playwright


EBIRD_LOGIN_URL = (
    "https://secure.birds.cornell.edu/cassso/login"
    "?service=https%3A%2F%2Febird.org%2Flogin%2Fcas%3Fportal%3Debird"
)


async def _scrape_year_list_async(
    username: str,
    password: str,
    region: str = "world",
    year: int = None,
) -> dict[str, str]:
    """
    Log in to eBird and return {species_code: common_name} for the given region/year.

    region examples: 'world', 'US', 'US-FL', 'US-FL-099'
    """
    import datetime
    year = year or datetime.datetime.now().year

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # Log in
        await page.goto(EBIRD_LOGIN_URL, timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        await page.fill("#input-user-name", username)
        await page.fill("#input-password", password)
        await page.click("#form-submit")
        await page.wait_for_load_state("domcontentloaded", timeout=20000)

        if "ebird.org" not in page.url:
            raise RuntimeError(
                f"eBird login failed — check your username/password. (URL: {page.url})"
            )

        # Navigate to year list
        url = f"https://ebird.org/lifelist?r={region}&time=year"
        await page.goto(url, timeout=30000)
        await page.wait_for_timeout(3000)  # let JS render

        content = await page.content()
        await browser.close()

    entries = re.findall(
        r'data-species-code="([^"]+)"[^>]*>.*?<span class="Heading-main">([^<]+)</span>',
        content,
        re.DOTALL,
    )
    return {code: name for code, name in entries}


def fetch_year_list(
    username: Optional[str] = None,
    password: Optional[str] = None,
    region: str = "world",
    year: int = None,
) -> dict[str, str]:
    """
    Synchronous wrapper. Returns {species_code: common_name}.
    Falls back to EBIRD_USERNAME / EBIRD_PASSWORD env vars.
    """
    username = username or os.environ.get("EBIRD_USERNAME", "")
    password = password or os.environ.get("EBIRD_PASSWORD", "")
    if not username or not password:
        raise ValueError("EBIRD_USERNAME and EBIRD_PASSWORD must be set (env or args).")
    return asyncio.run(_scrape_year_list_async(username, password, region, year))


def fetch_year_list_multi_region(
    username: str,
    password: str,
    state_code: str,
    year: int = None,
) -> dict[str, set[str]]:
    """
    Fetch year lists for world, US, and a specific state in parallel.
    Returns {'world': {codes}, 'US': {codes}, state_code: {codes}}
    """
    async def _all():
        tasks = {
            "world": _scrape_year_list_async(username, password, "world", year),
            "US":    _scrape_year_list_async(username, password, "US", year),
            state_code: _scrape_year_list_async(username, password, state_code, year),
        }
        results = {}
        for key, coro in tasks.items():
            # Run sequentially to avoid session conflicts
            results[key] = await coro
        return results

    raw = asyncio.run(_all())
    return {k: set(v.keys()) for k, v in raw.items()}
