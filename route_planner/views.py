import math
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import RouteRequestSerializer
from .routing import geocode, get_route, extract_route_info
from .fuel_planner import plan_fuel_stops


class RoutePlannerView(APIView):
    """
    POST /api/route/
    Plan a fuel-optimised road trip between two US locations.

    Request body:
        {
          "start":  "Dallas, TX",
          "finish": "Chicago, IL",
          "fuel_type": "regular"   // optional, default "regular"
        }

    Response includes:
        - Full route polyline (for map rendering)
        - Optimal fuel stops with prices and costs
        - Total fuel cost for the trip
    """

    def post(self, request):
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        start_input = data['start']
        finish_input = data['finish']
        fuel_type = data.get('fuel_type', 'regular')

        # ------------------------------------------------------------------
        # 1. Geocode start & finish  (2 calls to ORS geocoding)
        # ------------------------------------------------------------------
        try:
            start_lon, start_lat, start_label = geocode(start_input)
            finish_lon, finish_lat, finish_label = geocode(finish_input)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {'error': f'Geocoding failed: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # ------------------------------------------------------------------
        # 2. Fetch route — ONE call to ORS directions
        # ------------------------------------------------------------------
        try:
            geojson = get_route(start_lon, start_lat, finish_lon, finish_lat)
        except Exception as e:
            return Response(
                {'error': f'Routing failed: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        route_info = extract_route_info(geojson)

        # ------------------------------------------------------------------
        # 3. Plan fuel stops — pure local computation, no more API calls
        # ------------------------------------------------------------------
        fuel_plan = plan_fuel_stops(
            total_distance_miles=route_info['total_distance_miles'],
            state_sequence=route_info['state_sequence'],
            fuel_type=fuel_type,
        )

        # ------------------------------------------------------------------
        # 4. Build map URL (OpenStreetMap, no API key required)
        # ------------------------------------------------------------------
        map_url = _build_osm_url(
            start_lat, start_lon, finish_lat, finish_lon,
            route_info['coordinates'],
        )

        # ------------------------------------------------------------------
        # 5. Compose response
        # ------------------------------------------------------------------
        duration_hours = round(route_info['total_duration_seconds'] / 3600, 1)

        response_data = {
            'start_location': start_label,
            'finish_location': finish_label,
            'total_distance_miles': route_info['total_distance_miles'],
            'total_duration_hours': duration_hours,
            'fuel_stops': fuel_plan['stops'],
            'total_fuel_cost': fuel_plan['total_fuel_cost'],
            'total_gallons': fuel_plan['total_gallons'],
            'vehicle_range_miles': fuel_plan['vehicle_range_miles'],
            'vehicle_mpg': fuel_plan['vehicle_mpg'],
            'route_polyline': route_info['coordinates'],
            'map_url': map_url,
        }

        return Response(response_data, status=status.HTTP_200_OK)


def _build_osm_url(
    start_lat, start_lon, end_lat, end_lon, coords: list
) -> str:
    """
    Build an OpenStreetMap URL that shows the bounding box of the route.
    No API key needed — just a shareable link.
    """
    if coords:
        lats = [c[1] for c in coords]
        lons = [c[0] for c in coords]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"
        return (
            f"https://www.openstreetmap.org/?"
            f"mlat={start_lat}&mlon={start_lon}"
            f"#map=5/{(min_lat+max_lat)/2:.4f}/{(min_lon+max_lon)/2:.4f}"
            f"&layers=N"
        )
    return (
        f"https://www.openstreetmap.org/directions?"
        f"from={start_lat},{start_lon}&to={end_lat},{end_lon}"
    )
