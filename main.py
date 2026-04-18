"""
Birding Needs Finder — CLI entry point

Usage:
  python main.py --lat 47.6062 --lng -122.3321 --state US-WA
  python main.py --lat 47.6062 --lng -122.3321 --state US-WA --scope local
  python main.py --lat 47.6062 --lng -122.3321 --state US-WA --days 30 --dist 50
"""
import argparse
from pathlib import Path

from dotenv import load_dotenv

from src.ebird.client import EBirdClient
from src.tracker.personal_list import PersonalList
from src.tracker.needs_finder import NeedsFinder
from src.ui.display import print_needs, print_summary

load_dotenv()

DEFAULT_CSV = Path("data/lists/MyEBirdData.csv")


def main():
    parser = argparse.ArgumentParser(description="Find birds you haven't seen this year.")
    parser.add_argument("--lat",   type=float, required=True,  help="Your latitude")
    parser.add_argument("--lng",   type=float, required=True,  help="Your longitude")
    parser.add_argument("--state", type=str,   required=True,  help="State code, e.g. US-WA")
    parser.add_argument("--scope", type=str,   default="all",  choices=["local", "state", "usa", "all"])
    parser.add_argument("--dist",  type=int,   default=25,     help="Search radius in km (default: 25)")
    parser.add_argument("--days",  type=int,   default=14,     help="Days back to search eBird (default: 14)")
    parser.add_argument("--limit", type=int,   default=50,     help="Max species to display per scope")
    parser.add_argument("--csv",   type=Path,  default=DEFAULT_CSV, help="Path to your eBird data CSV")
    args = parser.parse_args()

    client = EBirdClient()
    personal = PersonalList(args.csv)
    finder = NeedsFinder(client, personal)

    print_summary(personal.summary())

    if args.scope == "all":
        results = finder.all_needs(args.lat, args.lng, args.state, args.dist, args.days)
        for scope, needs in results.items():
            print_needs(needs, scope, args.limit)
    elif args.scope == "local":
        print_needs(finder.local_needs(args.lat, args.lng, args.dist, args.days), "local", args.limit)
    elif args.scope == "state":
        print_needs(finder.state_needs(args.state, args.days), "state", args.limit)
    elif args.scope == "usa":
        print_needs(finder.usa_needs(args.days), "usa", args.limit)


if __name__ == "__main__":
    main()
