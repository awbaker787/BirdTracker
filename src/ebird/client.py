"""
eBird API v2 client.
Docs: https://documenter.getpostman.com/view/664302/S1ENwy59
"""
import os
import requests
from functools import lru_cache
from typing import Optional

EBIRD_BASE_URL = "https://api.ebird.org/v2"


class EBirdClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ["EBIRD_API_KEY"]
        self.session = requests.Session()
        self.session.headers.update({"X-eBirdApiToken": self.api_key})

    def _get(self, path: str, params: dict = None) -> list | dict:
        resp = self.session.get(f"{EBIRD_BASE_URL}{path}", params=params or {})
        resp.raise_for_status()
        return resp.json()

    # --- Recent observations ---

    def recent_observations_in_region(self, region_code: str, days_back: int = 14, max_results: int = 10000) -> list[dict]:
        """All recent observations in a region (e.g. 'US-WA', 'US', 'US-WA-033')."""
        return self._get(f"/data/obs/{region_code}/recent", {
            "back": days_back,
            "maxResults": max_results,
            "includeProvisional": True,
        })

    def recent_observations_nearby(self, lat: float, lng: float, dist_km: int = 25, days_back: int = 14) -> list[dict]:
        """Recent observations near a lat/lng (within dist_km radius)."""
        return self._get("/data/obs/geo/recent", {
            "lat": lat,
            "lng": lng,
            "dist": dist_km,
            "back": days_back,
            "maxResults": 10000,
            "includeProvisional": True,
        })

    # --- Checklists / personal data ---

    def my_year_list(self, region_code: str) -> list[dict]:
        """
        Species the authenticated user has observed in a region this year.
        NOTE: eBird API does not expose personal year lists directly.
        Export your eBird data from ebird.org/downloadMyData and use the
        local tracker instead — see src/tracker/personal_list.py.
        """
        raise NotImplementedError(
            "eBird API doesn't expose personal year lists. "
            "Download your data CSV from ebird.org/downloadMyData and load it with PersonalList."
        )

    # --- Taxonomy ---

    @lru_cache(maxsize=1)
    def taxonomy(self) -> list[dict]:
        """Full eBird taxonomy (species codes, common names, scientific names)."""
        return self._get("/ref/taxonomy/ebird", {"fmt": "json"})

    def species_list_for_region(self, region_code: str) -> list[str]:
        """All species codes ever reported in a region."""
        return self._get(f"/product/spplist/{region_code}")

    # --- Hotspots ---

    def hotspots_nearby(self, lat: float, lng: float, dist_km: int = 25) -> list[dict]:
        """Birding hotspots near a location."""
        return self._get("/ref/hotspot/geo", {
            "lat": lat,
            "lng": lng,
            "dist": dist_km,
            "fmt": "json",
        })

    # --- Notable / rare birds ---

    def notable_observations_nearby(self, lat: float, lng: float, dist_km: int = 25, days_back: int = 14) -> list[dict]:
        """Recently reported notable/rare birds near a location."""
        return self._get("/data/obs/geo/recent/notable", {
            "lat": lat,
            "lng": lng,
            "dist": dist_km,
            "back": days_back,
            "detail": "full",
        })

    def notable_observations_in_region(self, region_code: str, days_back: int = 14) -> list[dict]:
        """Recently reported notable/rare birds in a region."""
        return self._get(f"/data/obs/{region_code}/recent/notable", {
            "back": days_back,
            "detail": "full",
        })
