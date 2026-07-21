"""POST /api/trips/ -- the one endpoint the frontend needs.

Geocode and route the three addresses, run the HOS simulation, persist the result
so it has a shareable id, and return the whole `{ trip, route, logs }` payload.

`plan_route` is injected rather than imported-and-called so the tests can supply a
fake without any HTTP mocking, and so a future provider swap needs no change here.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from hos import plan_trip
from services import TripPlanningError, plan_route

from .models import DutySegment, LogDay, RouteStop, Trip
from .payload import build_logs, build_stops, build_trip_summary
from .serializers import TripRequestSerializer, TripResponseSerializer


@api_view(["POST"])
def create_trip(request, route_planner=None):
    # Resolved at call time, not bound as a default: that keeps the module-level
    # name patchable in tests, and lets a caller inject a planner explicitly.
    route_planner = route_planner or plan_route

    serializer = TripRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {"error": _first_message(serializer.errors), "details": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    inputs = serializer.validated_data
    try:
        routed = route_planner(
            inputs["current_location"],
            inputs["pickup_location"],
            inputs["dropoff_location"],
        )
    except TripPlanningError as exc:
        # AddressNotFound, GeocodingError and RoutingError all carry a message
        # that is already safe to show a driver.
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    plan = plan_trip(routed.legs, inputs["current_cycle_used"])
    trip = _persist(inputs, routed, plan)
    return Response(TripResponseSerializer(trip).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def retrieve_trip(request, pk):
    """What makes the persisted id worth having -- a result you can link to."""
    trip = get_object_or_404(Trip, pk=pk)
    return Response(TripResponseSerializer(trip).data)


@transaction.atomic
def _persist(inputs, routed, plan) -> Trip:
    summary = build_trip_summary(plan, routed)
    trip = Trip.objects.create(
        current_location=inputs["current_location"],
        pickup_location=inputs["pickup_location"],
        dropoff_location=inputs["dropoff_location"],
        current_cycle_used=inputs["current_cycle_used"],
        total_distance_miles=summary["total_distance_miles"],
        total_drive_hours=summary["total_drive_hours"],
        total_days=summary["total_days"],
        cycle_hours_remaining=summary["cycle_hours_remaining"],
        provider_eta_hours=summary["provider_eta_hours"],
        provider_eta_source=summary["provider_eta_source"],
        geometry=[[lat, lng] for lat, lng in routed.geometry],
    )

    RouteStop.objects.bulk_create(
        RouteStop(
            trip=trip,
            kind=stop["kind"],
            label=stop["label"],
            latitude=stop["lat"],
            longitude=stop["lng"],
            arrive_at=stop["arrive_at"],
            depart_at=stop["depart_at"],
            sequence=stop["sequence"],
        )
        for stop in build_stops(plan, routed)
    )

    for day in build_logs(plan):
        log_day = LogDay.objects.create(
            trip=trip,
            date=day["date"],
            total_off_duty=day["totals"]["off_duty"],
            total_sleeper=day["totals"]["sleeper"],
            total_driving=day["totals"]["driving"],
            total_on_duty=day["totals"]["on_duty"],
            total_miles=day["total_miles"],
        )
        DutySegment.objects.bulk_create(
            DutySegment(
                log_day=log_day,
                status=segment["status"],
                start_minute=segment["start_minute"],
                end_minute=segment["end_minute"],
                remark=segment["remark"],
            )
            for segment in day["segments"]
        )

    return trip


def _first_message(errors) -> str:
    """Pull one human-readable line out of DRF's nested error structure."""
    for value in errors.values():
        if isinstance(value, dict):
            return _first_message(value)
        if isinstance(value, list) and value:
            return str(value[0])
        return str(value)
    return "Invalid request."
