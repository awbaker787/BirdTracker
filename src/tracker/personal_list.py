"""
Loads and queries the user's personal eBird data.

How to get your data:
  1. Go to ebird.org → My eBird → Download My Data
  2. Save the CSV to data/lists/MyEBirdData.csv
"""
import csv
from datetime import datetime
from pathlib import Path


class PersonalList:
    def __init__(self, csv_path: str | Path):
        self.csv_path = Path(csv_path)
        self._records: list[dict] = []
        self._load()

    def _load(self):
        if not self.csv_path.exists():
            raise FileNotFoundError(
                f"eBird data CSV not found at {self.csv_path}. "
                "Download it from ebird.org → My eBird → Download My Data."
            )
        with open(self.csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self._records = list(reader)

    # eBird CSV columns we care about:
    #   "Species Code", "Common Name", "Scientific Name",
    #   "Date", "State/Province", "County", "Location", "Latitude", "Longitude"

    def _year_records(self, year: int) -> list[dict]:
        return [
            r for r in self._records
            if datetime.strptime(r["Date"], "%Y-%m-%d").year == year
        ]

    def species_seen_this_year(self, year: int = None) -> set[str]:
        """Set of species codes seen in the given year (defaults to current year)."""
        year = year or datetime.now().year
        return {r["Species Code"] for r in self._year_records(year)}

    def species_seen_this_year_in_state(self, state_code: str, year: int = None) -> set[str]:
        """Species codes seen this year in a specific state (e.g. 'US-WA')."""
        year = year or datetime.now().year
        return {
            r["Species Code"]
            for r in self._year_records(year)
            if r.get("State/Province", "").upper() == state_code.upper()
        }

    def life_list(self) -> set[str]:
        """All species codes ever seen."""
        return {r["Species Code"] for r in self._records}

    def summary(self, year: int = None) -> dict:
        year = year or datetime.now().year
        year_records = self._year_records(year)
        return {
            "year": year,
            "year_species_count": len({r["Species Code"] for r in year_records}),
            "life_list_count": len(self.life_list()),
            "total_checklists_this_year": len({r.get("Submission ID") for r in year_records}),
        }
