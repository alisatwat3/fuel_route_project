from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        max_length=200,
        help_text="Starting location (e.g. 'New York, NY' or '350 Fifth Ave, New York, NY')"
    )
    finish = serializers.CharField(
        max_length=200,
        help_text="Destination location (e.g. 'Los Angeles, CA')"
    )
    fuel_type = serializers.ChoiceField(
        choices=['regular', 'midgrade', 'premium', 'diesel'],
        default='regular',
        required=False,
    )

    def validate_start(self, value):
        return value.strip()

    def validate_finish(self, value):
        return value.strip()


class FuelStopSerializer(serializers.Serializer):
    stop_number = serializers.IntegerField()
    state = serializers.CharField()
    station_name = serializers.CharField()
    city = serializers.CharField()
    address = serializers.CharField()
    price_per_gallon = serializers.FloatField()
    gallons_to_fill = serializers.FloatField()
    cost_at_stop = serializers.FloatField()
    approx_mile_marker = serializers.FloatField()


class RouteResponseSerializer(serializers.Serializer):
    start_location = serializers.CharField()
    finish_location = serializers.CharField()
    total_distance_miles = serializers.FloatField()
    total_duration_hours = serializers.FloatField()
    fuel_stops = FuelStopSerializer(many=True)
    total_fuel_cost = serializers.FloatField()
    total_gallons = serializers.FloatField()
    vehicle_range_miles = serializers.IntegerField()
    vehicle_mpg = serializers.IntegerField()
    route_polyline = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField()),
        help_text="List of [lon, lat] coordinates for rendering the route on a map"
    )
    map_url = serializers.CharField(help_text="OpenStreetMap URL to preview the route")
