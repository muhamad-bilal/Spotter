"""Request validation and the response shape from the API contract."""

from rest_framework import serializers

from .models import DutySegment, LogDay, RouteStop, Trip
from .payload import DRIVE_HOURS_BASIS

CYCLE_LIMIT_HOURS = 70


class TripRequestSerializer(serializers.Serializer):
    """The four inputs from the form.

    Everything a reviewer is likely to try -- a blank field, a cycle over 70, the
    same address twice -- is rejected here with a message the form can display.
    """

    current_location = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)
    pickup_location = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)
    dropoff_location = serializers.CharField(max_length=255, allow_blank=False, trim_whitespace=True)
    current_cycle_used = serializers.FloatField(
        min_value=0,
        max_value=CYCLE_LIMIT_HOURS,
        error_messages={
            "min_value": "Cycle hours used cannot be negative.",
            "max_value": (
                f"Cycle hours used cannot exceed {CYCLE_LIMIT_HOURS} -- that is the "
                f"whole 8-day limit, leaving no hours to drive."
            ),
        },
    )

    def validate(self, attrs):
        if attrs["pickup_location"].strip().lower() == attrs["dropoff_location"].strip().lower():
            raise serializers.ValidationError(
                {"dropoff_location": "Pickup and dropoff must be different locations."}
            )
        return attrs


# --- response ---------------------------------------------------------------


class RouteStopSerializer(serializers.ModelSerializer):
    lat = serializers.FloatField(source="latitude")
    lng = serializers.FloatField(source="longitude")

    class Meta:
        model = RouteStop
        fields = ["kind", "label", "lat", "lng", "arrive_at", "depart_at"]


class DutySegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DutySegment
        fields = ["status", "start_minute", "end_minute", "remark"]


class LogDaySerializer(serializers.ModelSerializer):
    totals = serializers.SerializerMethodField()
    segments = DutySegmentSerializer(many=True, read_only=True)

    class Meta:
        model = LogDay
        fields = ["date", "totals", "total_miles", "segments"]

    def get_totals(self, day) -> dict:
        return {
            "off_duty": day.total_off_duty,
            "sleeper": day.total_sleeper,
            "driving": day.total_driving,
            "on_duty": day.total_on_duty,
        }


class TripSummarySerializer(serializers.ModelSerializer):
    """The headline numbers, including both durations under unambiguous names."""

    # The basis of the HOS figure is a project-wide assumption, so it stays a
    # constant. The provider name is a property of the individual trip and is
    # read from the row, so an old trip keeps naming the provider that served it.
    drive_hours_basis = serializers.SerializerMethodField()

    class Meta:
        model = Trip
        fields = [
            "id",
            "total_distance_miles",
            "total_drive_hours",
            "drive_hours_basis",
            "provider_eta_hours",
            "provider_eta_source",
            "total_days",
            "cycle_hours_remaining",
        ]

    def get_drive_hours_basis(self, _trip) -> str:
        return DRIVE_HOURS_BASIS


class TripResponseSerializer(serializers.ModelSerializer):
    """The whole `{ trip, route, logs }` payload in one response."""

    trip = serializers.SerializerMethodField()
    route = serializers.SerializerMethodField()
    logs = LogDaySerializer(many=True, read_only=True)

    class Meta:
        model = Trip
        fields = ["trip", "route", "logs"]

    def get_trip(self, trip) -> dict:
        return TripSummarySerializer(trip).data

    def get_route(self, trip) -> dict:
        return {
            "geometry": trip.geometry,
            "stops": RouteStopSerializer(trip.stops.all(), many=True).data,
        }
