"""
Loads and caches fuel price data from the OPIS truckstop CSV.
Each row is an individual truckstop with city, state, and retail price.
Multiple rows can exist for the same truckstop ID (different fuel grades).
We take the minimum retail price per station (best deal for the driver).
"""
import csv
import functools
from pathlib import Path
from django.conf import settings


@functools.lru_cache(maxsize=1)
def load_fuel_stations() -> list[dict]:
    """
    Load all truckstop stations from CSV, deduplicated to one entry per
    (Truckstop ID + City + State) with the lowest retail price.
    Returns a list of dicts:
      [{'id': '7', 'name': '...', 'city': '...', 'state': 'OK', 'price': 3.007}, ...]
    """
    csv_path = Path(settings.FUEL_PRICES_CSV)
    if not csv_path.exists():
        return []

    # Group by truckstop ID → keep lowest price
    best: dict[str, dict] = {}
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            state = row.get('State', '').strip()
            # Skip non-US entries (AB = Alberta CA, BC = British Columbia, etc.)
            if len(state) != 2 or state in ('AB', 'BC', 'MB', 'NB', 'NL', 'NS', 'ON', 'PE', 'QC', 'SK'):
                continue
            try:
                price = float(row['Retail Price'].strip())
            except (ValueError, TypeError):
                continue

            tid = row.get('OPIS Truckstop ID', '').strip()
            key = tid  # one entry per truckstop ID

            if key not in best or price < best[key]['price']:
                best[key] = {
                    'id': tid,
                    'name': row.get('Truckstop Name', '').strip().title(),
                    'address': row.get('Address', '').strip(),
                    'city': row.get('City', '').strip(),
                    'state': state.upper(),
                    'price': price,
                }

    return list(best.values())


@functools.lru_cache(maxsize=1)
def stations_by_state() -> dict[str, list[dict]]:
    """Return stations grouped by state abbreviation."""
    result: dict[str, list[dict]] = {}
    for s in load_fuel_stations():
        result.setdefault(s['state'], []).append(s)
    return result


def cheapest_in_state(state: str) -> dict | None:
    """Return the single cheapest station in a given state."""
    stations = stations_by_state().get(state.upper(), [])
    if not stations:
        return None
    return min(stations, key=lambda s: s['price'])


def get_national_average() -> float:
    """Fallback national average across all stations."""
    stations = load_fuel_stations()
    if not stations:
        return 3.50
    return round(sum(s['price'] for s in stations) / len(stations), 3)
