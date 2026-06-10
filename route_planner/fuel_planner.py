"""
Core fuel-stop planning logic.

Strategy (zero extra API calls after the initial route fetch):
1. Get the ordered list of states from the route geometry.
2. For each ~500-mile segment, find the cheapest truckstop in the upcoming states.
3. Prefer stations in states where fuel is cheaper, but always stop before running out.

The algorithm is a greedy look-ahead:
  - Current fuel level starts full (500 miles range).
  - As we "drive" through states, when range drops below the miles remaining to the
    next cheap state, we stop at the cheapest available station.
"""
from django.conf import settings
from .fuel_data import cheapest_in_state, get_national_average

MAX_RANGE = getattr(settings, 'VEHICLE_MAX_RANGE_MILES', 500)
MPG = getattr(settings, 'VEHICLE_MPG', 10)
TANK_GALLONS = MAX_RANGE / MPG  # 50 gallons


def plan_fuel_stops(
    total_distance_miles: float,
    state_sequence: list[str],
    fuel_type: str = 'regular',
) -> dict:
    """
    Given total route distance and ordered state sequence, return:
    {
      'stops': [
          {
            'stop_number': 1,
            'state': 'TX',
            'station_name': '...',
            'city': '...',
            'price_per_gallon': 2.92,
            'gallons_needed': 45.0,
            'cost_at_stop': 131.40,
            'approx_mile_marker': 480,
          }, ...
      ],
      'total_fuel_cost': float,
      'total_gallons': float,
      'start_full': True,   # assume driver starts with full tank
    }
    """
    if not state_sequence:
        # No state info — fall back to evenly-spaced stops using national avg
        return _fallback_plan(total_distance_miles)

    # Build a list of (approx_start_mile, state) segments
    # We divide total distance evenly across states crossed
    n_states = len(state_sequence)
    miles_per_state = total_distance_miles / max(n_states, 1)

    state_segments = []
    for i, state in enumerate(state_sequence):
        seg_start = i * miles_per_state
        seg_end = (i + 1) * miles_per_state
        station = cheapest_in_state(state)
        if station is None:
            # No data for this state — use national average placeholder
            station = {
                'name': f'Best station in {state}',
                'city': '',
                'state': state,
                'price': get_national_average(),
            }
        state_segments.append({
            'state': state,
            'seg_start_mile': seg_start,
            'seg_end_mile': seg_end,
            'cheapest_station': station,
        })

    # -----------------------------------------------------------------------
    # Greedy look-ahead pass
    # -----------------------------------------------------------------------
    stops = []
    current_mile = 0.0
    current_range = float(MAX_RANGE)  # start with full tank
    stop_number = 1

    while current_mile < total_distance_miles:
        remaining_trip = total_distance_miles - current_mile

        if remaining_trip <= current_range:
            # We can reach the destination without stopping
            break

        # Find the cheapest station we can reach from here within current range,
        # but also look one "segment" ahead to decide if we should wait for cheaper fuel.
        reachable_segments = [
            seg for seg in state_segments
            if seg['seg_start_mile'] >= current_mile
            and seg['seg_start_mile'] < current_mile + current_range
        ]

        if not reachable_segments:
            break

        # Among reachable segments, pick the one with the cheapest fuel
        best_seg = min(reachable_segments, key=lambda s: s['cheapest_station']['price'])

        # The stop happens at the midpoint of that state's segment
        stop_mile = max(
            current_mile + 50,  # at least 50 miles from current position
            (best_seg['seg_start_mile'] + best_seg['seg_end_mile']) / 2
        )
        stop_mile = min(stop_mile, current_mile + current_range - 20)  # safety buffer

        miles_driven_to_stop = stop_mile - current_mile
        gallons_used = miles_driven_to_stop / MPG
        range_at_stop = current_range - miles_driven_to_stop

        # Fill up enough to either reach destination or cover next MAX_RANGE miles
        gallons_to_fill = TANK_GALLONS - (range_at_stop / MPG)
        gallons_to_fill = max(0, round(gallons_to_fill, 2))

        station = best_seg['cheapest_station']
        cost = round(gallons_to_fill * station['price'], 2)

        stops.append({
            'stop_number': stop_number,
            'state': station['state'],
            'station_name': station['name'],
            'city': station.get('city', ''),
            'address': station.get('address', ''),
            'price_per_gallon': round(station['price'], 3),
            'gallons_to_fill': gallons_to_fill,
            'cost_at_stop': cost,
            'approx_mile_marker': round(stop_mile, 1),
        })

        current_mile = stop_mile
        current_range = TANK_GALLONS * MPG  # refilled to full
        stop_number += 1

    # -----------------------------------------------------------------------
    # Calculate fuel used for the final leg and total cost
    # -----------------------------------------------------------------------
    # Driver starts with a full tank — account for fuel already in the tank at start
    total_gallons_needed = total_distance_miles / MPG
    total_fuel_cost = round(sum(s['cost_at_stop'] for s in stops), 2)

    # If no stops needed (short route), cost = distance/mpg * price in start state
    if not stops and state_sequence:
        start_price = (cheapest_in_state(state_sequence[0]) or {}).get('price', get_national_average())
        total_gallons_needed = round(total_distance_miles / MPG, 2)
        total_fuel_cost = round(total_gallons_needed * start_price, 2)

    return {
        'stops': stops,
        'total_fuel_cost': total_fuel_cost,
        'total_gallons': round(total_gallons_needed, 2),
        'vehicle_range_miles': MAX_RANGE,
        'vehicle_mpg': MPG,
    }


def _fallback_plan(total_distance_miles: float) -> dict:
    """Used when no state sequence is available."""
    avg_price = get_national_average()
    total_gallons = total_distance_miles / MPG
    num_stops = int(total_distance_miles // MAX_RANGE)
    stops = []
    for i in range(num_stops):
        mile = (i + 1) * MAX_RANGE - 20
        stops.append({
            'stop_number': i + 1,
            'state': 'N/A',
            'station_name': 'Nearest station',
            'city': '',
            'price_per_gallon': avg_price,
            'gallons_to_fill': TANK_GALLONS,
            'cost_at_stop': round(TANK_GALLONS * avg_price, 2),
            'approx_mile_marker': mile,
        })
    return {
        'stops': stops,
        'total_fuel_cost': round(total_gallons * avg_price, 2),
        'total_gallons': round(total_gallons, 2),
        'vehicle_range_miles': MAX_RANGE,
        'vehicle_mpg': MPG,
    }
