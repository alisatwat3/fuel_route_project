"""
OpenRouteService (ORS) integration.
Free tier: https://openrouteservice.org/ — 2,000 requests/day, no credit card needed.

Strategy: ONE call to ORS to get the full route geometry + waypoints.
Then all fuel-stop logic is handled locally using the route's step-by-step
instructions which include city/state names — no extra API calls needed.
"""
import requests
import re
from django.conf import settings


ORS_BASE = "https://api.openrouteservice.org/v2"
HEADERS = lambda: {"Authorization": settings.ORS_API_KEY, "Content-Type": "application/json"}


def geocode(location: str) -> tuple[float, float]:
    """
    Convert a free-text location (e.g. 'Dallas, TX') to (longitude, latitude).
    Uses ORS Geocoding — counts as one API call.
    Returns (lon, lat).
    """
    url = f"{ORS_BASE}/geocode/search"
    params = {
        "api_key": settings.ORS_API_KEY,
        "text": location,
        "boundary.country": "US",
        "size": 1,
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    features = data.get("features", [])
    if not features:
        raise ValueError(f"Could not geocode location: {location!r}")
    coords = features[0]["geometry"]["coordinates"]  # [lon, lat]
    label = features[0]["properties"].get("label", location)
    return coords[0], coords[1], label


def get_route(start_lon, start_lat, end_lon, end_lat) -> dict:
    """
    Single ORS directions call.
    Returns the full GeoJSON feature with geometry + step-by-step instructions.
    Each step contains: distance, duration, instruction, name, way_points.
    """
    url = f"{ORS_BASE}/directions/driving-car/geojson"
    payload = {
        "coordinates": [[start_lon, start_lat], [end_lon, end_lat]],
        "instructions": True,
        "instructions_format": "text",
        "units": "mi",
        "geometry": True,
    }
    resp = requests.post(url, json=payload, headers=HEADERS(), timeout=15)
    resp.raise_for_status()
    return resp.json()


def extract_route_info(geojson: dict) -> dict:
    """
    Parse the ORS GeoJSON response into a clean structure.
    Returns:
      {
        'total_distance_miles': float,
        'total_duration_seconds': float,
        'coordinates': [[lon, lat], ...],   # full polyline
        'segments': [{'distance_miles': float, 'steps': [...]}],
        'state_sequence': ['TX', 'OK', 'KS', ...],  # states crossed in order
      }
    """
    feature = geojson["features"][0]
    props = feature["properties"]
    summary = props["summary"]
    coords = feature["geometry"]["coordinates"]  # list of [lon, lat]
    segments = props.get("segments", [])

    state_seq = _infer_state_sequence(coords)

    return {
        "total_distance_miles": round(summary["distance"], 1),
        "total_duration_seconds": summary["duration"],
        "coordinates": coords,
        "segments": segments,
        "state_sequence": state_seq,
    }


# ---------------------------------------------------------------------------
# State boundary inference via bounding boxes
# ---------------------------------------------------------------------------
# Rough bounding boxes (min_lon, min_lat, max_lon, max_lat) for each state.
# Good enough to determine which state a coordinate falls in without extra API calls.
STATE_BBOXES = {
    "AL": (-88.47, 30.14, -84.89, 35.01), "AK": (-179.1, 51.2, -129.9, 71.4),
    "AZ": (-114.82, 31.33, -109.04, 37.00), "AR": (-94.62, 33.00, -89.64, 36.50),
    "CA": (-124.41, 32.53, -114.13, 42.01), "CO": (-109.05, 36.99, -102.04, 41.00),
    "CT": (-73.73, 40.98, -71.79, 42.05), "DE": (-75.79, 38.45, -74.98, 39.84),
    "FL": (-87.63, 24.54, -79.97, 31.00), "GA": (-85.61, 30.36, -80.84, 35.00),
    "HI": (-160.25, 18.91, -154.80, 22.24), "ID": (-117.24, 41.99, -111.04, 49.00),
    "IL": (-91.51, 36.97, -87.49, 42.51), "IN": (-88.10, 37.77, -84.78, 41.76),
    "IA": (-96.64, 40.37, -90.14, 43.50), "KS": (-102.05, 36.99, -94.59, 40.00),
    "KY": (-89.57, 36.49, -81.96, 39.15), "LA": (-94.04, 28.92, -88.82, 33.02),
    "ME": (-71.08, 43.06, -66.95, 47.46), "MD": (-79.49, 37.89, -75.05, 39.72),
    "MA": (-73.51, 41.24, -69.93, 42.89), "MI": (-90.42, 41.69, -82.41, 48.31),
    "MN": (-97.24, 43.50, -89.49, 49.38), "MS": (-91.65, 30.17, -88.10, 35.01),
    "MO": (-95.77, 35.99, -89.10, 40.62), "MT": (-116.05, 44.35, -104.04, 49.00),
    "NE": (-104.05, 39.99, -95.31, 43.00), "NV": (-120.00, 35.00, -114.04, 42.00),
    "NH": (-72.56, 42.70, -70.61, 45.31), "NJ": (-75.56, 38.92, -73.89, 41.36),
    "NM": (-109.05, 31.33, -103.00, 37.00), "NY": (-79.76, 40.50, -71.85, 45.02),
    "NC": (-84.32, 33.84, -75.46, 36.59), "ND": (-104.05, 45.93, -96.55, 49.00),
    "OH": (-84.82, 38.40, -80.52, 41.98), "OK": (-103.00, 33.62, -94.43, 37.00),
    "OR": (-124.57, 41.99, -116.46, 46.24), "PA": (-80.52, 39.72, -74.69, 42.27),
    "RI": (-71.91, 41.31, -71.12, 42.02), "SC": (-83.35, 32.04, -78.54, 35.22),
    "SD": (-104.06, 42.48, -96.44, 45.95), "TN": (-90.31, 34.98, -81.65, 36.68),
    "TX": (-106.65, 25.84, -93.51, 36.50), "UT": (-114.05, 36.99, -109.04, 42.00),
    "VT": (-73.44, 42.73, -71.47, 45.02), "VA": (-83.68, 36.54, -75.17, 39.47),
    "WA": (-124.73, 45.54, -116.92, 49.00), "WV": (-82.64, 37.20, -77.72, 40.64),
    "WI": (-92.89, 42.49, -86.25, 47.08), "WY": (-111.06, 40.99, -104.05, 45.01),
    "DC": (-77.12, 38.79, -76.91, 38.99),
}


def _coord_to_state(lon: float, lat: float) -> str | None:
    """Best-match state for a coordinate using bounding boxes."""
    candidates = []
    for state, (min_lon, min_lat, max_lon, max_lat) in STATE_BBOXES.items():
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            candidates.append(state)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Multiple matches (border areas) — pick the one whose center is closest
    def center_dist(s):
        b = STATE_BBOXES[s]
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        return (cx - lon) ** 2 + (cy - lat) ** 2
    return min(candidates, key=center_dist)


def _infer_state_sequence(coords: list) -> list[str]:
    """
    Walk the route coordinates and return the ordered list of unique states crossed.
    Samples every 10th coordinate for speed on long routes.
    """
    seen = []
    step = max(1, len(coords) // 200)  # sample ~200 points max
    for i in range(0, len(coords), step):
        lon, lat = coords[i][0], coords[i][1]
        state = _coord_to_state(lon, lat)
        if state and (not seen or seen[-1] != state):
            seen.append(state)
    # Always check the last coordinate
    if coords:
        last_state = _coord_to_state(coords[-1][0], coords[-1][1])
        if last_state and (not seen or seen[-1] != last_state):
            seen.append(last_state)
    return seen
