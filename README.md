# Fuel Route Planner API

A Django REST API that plans cost-optimised fuel stops for a road trip between any two US locations.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Add your free ORS API key (see below)
export ORS_API_KEY=your_key_here

python manage.py migrate
python manage.py runserver
```

## Get a Free API Key

Sign up at **https://openrouteservice.org/dev/#/signup** — free tier gives 2,000 requests/day with no credit card.

## API Usage

### `POST /api/route/`

**Request:**
```json
{
  "start":  "Dallas, TX",
  "finish": "Chicago, IL",
  "fuel_type": "regular"
}
```
`fuel_type` is optional (default: `regular`). Options: `regular`, `midgrade`, `premium`, `diesel`.

**Response:**
```json
{
  "start_location": "Dallas, TX, USA",
  "finish_location": "Chicago, IL, USA",
  "total_distance_miles": 921.4,
  "total_duration_hours": 13.5,
  "fuel_stops": [
    {
      "stop_number": 1,
      "state": "OK",
      "station_name": "Woodshed Of Big Cabin",
      "city": "Big Cabin",
      "address": "I-44, EXIT 283 & US-69",
      "price_per_gallon": 3.007,
      "gallons_to_fill": 42.5,
      "cost_at_stop": 127.80,
      "approx_mile_marker": 245.0
    }
  ],
  "total_fuel_cost": 298.45,
  "total_gallons": 92.1,
  "vehicle_range_miles": 500,
  "vehicle_mpg": 10,
  "route_polyline": [[-96.796, 32.776], ...],
  "map_url": "https://www.openstreetmap.org/..."
}
```

### Example `curl`

```bash
curl -X POST http://localhost:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "New York, NY", "finish": "Los Angeles, CA"}'
```

## Design Decisions

### API Call Minimisation
The assignment asks for as few routing API calls as possible. This implementation uses:

| Call | Purpose |
|------|---------|
| `GET /geocode` (×2) | Convert start + finish text → coordinates |
| `POST /directions` (×1) | Fetch full route with geometry |

**Total: 3 ORS API calls per request.** All fuel-stop logic runs locally with zero additional calls.

### Fuel Stop Algorithm
1. The route geometry is analysed to determine which US states are crossed, in order.
2. The route distance is divided proportionally across those states.
3. A greedy look-ahead algorithm scans reachable states and stops at whichever offers the cheapest fuel, while ensuring the tank never runs dry (500-mile max range enforced with a 20-mile safety buffer).
4. All fuel data is loaded from the OPIS CSV once at startup and cached in memory (`lru_cache`) — no database reads per request.

### Fuel Data
The OPIS truckstop dataset (~8,000 stations) is loaded at startup. For stations with multiple price entries (different grades), the lowest retail price is used. Non-US entries (Canadian provinces) are filtered out.

### Map Output
- `route_polyline` — the full `[lon, lat]` coordinate array from ORS, ready to pass to Leaflet, Mapbox GL, or Google Maps JS SDK.
- `map_url` — a no-key-required OpenStreetMap link showing the route bounding box.

## Project Structure

```
fuel_route_project/
├── fuel_route_project/
│   ├── settings.py       # ORS_API_KEY, FUEL_PRICES_CSV path, vehicle defaults
│   └── urls.py
├── route_planner/
│   ├── fuel_data.py      # CSV loader + in-memory cache
│   ├── fuel_planner.py   # Stop-selection algorithm
│   ├── routing.py        # ORS geocoding + directions client + state inference
│   ├── serializers.py
│   └── views.py
├── fuel_prices.csv       # OPIS truckstop data
├── requirements.txt
└── README.md
```
