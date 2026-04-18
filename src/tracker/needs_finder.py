"""
Core logic: find birds reported near you that you haven't seen yet this year.

Scopes:
  - local   : birds seen recently near your coordinates (or a hotspot)
  - state   : birds reported in your state this year that you haven't seen in-state
  - usa     : birds reported anywhere in the US this year that you haven't seen at all
"""
import math
from dataclasses import dataclass, field
from datetime import datetime

from src.ebird.client import EBirdClient
from src.tracker.personal_list import PersonalList


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Straight-line distance in miles between two lat/lng points."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


@dataclass
class Need:
    species_code: str
    common_name: str
    scientific_name: str
    scope: str              # 'local', 'state', or 'usa'
    last_seen: str          # most recent observation date in eBird
    location_name: str
    lat: float
    lng: float
    count: int | None       # observed count, None if not reported
    dist_miles: float = field(default=0.0)  # distance from user's location


class NeedsFinder:
    def __init__(self, client: EBirdClient, personal_list, user_lat: float = 0.0, user_lng: float = 0.0):
        self.client = client
        self.personal = personal_list
        self.user_lat = user_lat
        self.user_lng = user_lng

    # --- helpers ---

    def _parse_obs(self, obs: dict, scope: str, seen_codes: set[str]) -> Need | None:
        code = obs.get("speciesCode", "")
        if code in seen_codes:
            return None
        # skip subspecies / slash / spuh entries (no species code or contains '/')
        if not code or "/" in obs.get("comName", ""):
            return None
        bird_lat = obs.get("lat", 0.0)
        bird_lng = obs.get("lng", 0.0)
        dist = _haversine_miles(self.user_lat, self.user_lng, bird_lat, bird_lng) if (self.user_lat and self.user_lng) else 0.0
        return Need(
            species_code=code,
            common_name=obs.get("comName", ""),
            scientific_name=obs.get("sciName", ""),
            scope=scope,
            last_seen=obs.get("obsDt", ""),
            location_name=obs.get("locName", ""),
            lat=bird_lat,
            lng=bird_lng,
            count=obs.get("howMany"),
            dist_miles=round(dist, 1),
        )

    def _dedupe(self, needs: list[Need]) -> list[Need]:
        """Keep closest sighting per species."""
        seen = {}
        for n in needs:
            if n.species_code not in seen or n.dist_miles < seen[n.species_code].dist_miles:
                seen[n.species_code] = n
        return sorted(seen.values(), key=lambda n: n.dist_miles)

    # --- public API ---

    def local_needs(self, lat: float, lng: float, dist_km: int = 25, days_back: int = 14, year: int = None) -> list[Need]:
        """Birds seen near lat/lng that you haven't recorded this year."""
        year = year or datetime.now().year
        seen = self.personal.species_seen_this_year(year)
        obs = self.client.recent_observations_nearby(lat, lng, dist_km, days_back)
        needs = [self._parse_obs(o, "local", seen) for o in obs]
        return self._dedupe([n for n in needs if n])

    def state_needs(self, state_code: str, days_back: int = 14, year: int = None) -> list[Need]:
        """Birds reported in your state that you haven't seen in-state this year."""
        year = year or datetime.now().year
        seen_in_state = self.personal.species_seen_this_year_in_state(state_code, year)
        obs = self.client.recent_observations_in_region(state_code, days_back)
        needs = [self._parse_obs(o, "state", seen_in_state) for o in obs]
        return self._dedupe([n for n in needs if n])

    def usa_needs(self, days_back: int = 14, year: int = None) -> list[Need]:
        """Birds reported anywhere in the US that you haven't seen at all this year."""
        year = year or datetime.now().year
        seen = self.personal.species_seen_this_year(year)
        obs = self.client.recent_observations_in_region("US", days_back)
        needs = [self._parse_obs(o, "usa", seen) for o in obs]
        return self._dedupe([n for n in needs if n])

    def all_needs(
        self,
        lat: float,
        lng: float,
        state_code: str,
        dist_km: int = 25,
        days_back: int = 14,
        year: int = None,
    ) -> dict[str, list[Need]]:
        """Run all three scopes at once."""
        return {
            "local": self.local_needs(lat, lng, dist_km, days_back, year),
            "state": self.state_needs(state_code, days_back, year),
            "usa": self.usa_needs(days_back, year),
        }
