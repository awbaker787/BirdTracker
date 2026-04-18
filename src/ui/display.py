"""
Terminal display helpers for birding needs.
"""
from src.tracker.needs_finder import Need

SCOPE_LABELS = {
    "local": "LOCAL AREA",
    "state": "STATE",
    "usa":   "USA",
}


def print_needs(needs: list[Need], scope: str, limit: int = 50):
    label = SCOPE_LABELS.get(scope, scope.upper())
    print(f"\n{'=' * 60}")
    print(f"  {label} NEEDS  ({len(needs)} species not yet seen this year)")
    print(f"{'=' * 60}")
    if not needs:
        print("  Nothing missing — great job!")
        return
    for i, n in enumerate(needs[:limit], 1):
        count_str = f"  (x{n.count})" if n.count else ""
        print(f"  {i:>3}. {n.common_name:<35} {n.last_seen[:10]}  {n.location_name[:30]}{count_str}")
    if len(needs) > limit:
        print(f"\n  ... and {len(needs) - limit} more. Use --limit to show all.")


def print_summary(summary: dict):
    print(f"\n{'─' * 60}")
    print(f"  Year {summary['year']} stats:")
    print(f"    Species this year : {summary['year_species_count']}")
    print(f"    Life list         : {summary['life_list_count']}")
    print(f"    Checklists (YTD)  : {summary['total_checklists_this_year']}")
    print(f"{'─' * 60}")
