"""Turn the engine's timeline plus the routed geometry into the API contract.

The engine emits a duty-status timeline; the map needs typed stops with positions.
Both come from the same timeline walk here, so the stop list and the log sheets can
never disagree about what happened when.

Nothing in this module changes the engine's numbers -- it only reshapes them.
"""

from hos.constants import AVG_SPEED_MPH
from hos.types import TripPlan
from services.route_planner import RoutedTrip

from .stop_locator import PolylineLocator

# Timeline kinds that are stops on the map. "drive" is movement, not a stop, and
# "off" is the idle tail after the trip finishes.
MAPPED_STOP_KINDS = {"start", "pickup", "dropoff", "fuel", "break_30", "rest_10", "restart_34"}

DRIVE_HOURS_BASIS = f"distance / {AVG_SPEED_MPH:.0f} mph (assumed)"


def build_stops(plan: TripPlan, routed: RoutedTrip) -> list[dict]:
    """Every mappable stop, positioned along the route by odometer reading."""
    locator = PolylineLocator(routed.geometry)
    total_miles = routed.total_distance_miles

    # The three geocoded addresses have real coordinates; prefer them over
    # anything interpolated.
    known = {
        "start": routed.places.get("current"),
        "pickup": routed.places.get("pickup"),
        "dropoff": routed.places.get("dropoff"),
    }

    stops = []
    odometer = 0.0
    for segment in plan.timeline:
        if segment.status == "driving":
            odometer += segment.minutes / 60 * AVG_SPEED_MPH
            continue
        if segment.kind not in MAPPED_STOP_KINDS:
            continue

        place = known.get(segment.kind)
        if place is not None:
            latitude, longitude = place.latitude, place.longitude
        else:
            position = locator.at_odometer(odometer, total_miles)
            latitude, longitude = position if position else (None, None)

        stops.append(
            {
                "kind": segment.kind,
                "label": segment.remark,
                "lat": latitude,
                "lng": longitude,
                "arrive_at": segment.start,
                "depart_at": segment.end,
                "sequence": len(stops),
            }
        )
    return stops


def build_logs(plan: TripPlan) -> list[dict]:
    return [
        {
            "date": day.date,
            "totals": _totals_in_hours(day.totals),
            "total_miles": day.total_miles,
            "segments": [
                {
                    "status": segment.status,
                    "start_minute": segment.start_minute,
                    "end_minute": segment.end_minute,
                    "remark": segment.remark,
                }
                for segment in day.segments
            ],
        }
        for day in plan.log_days
    ]


def build_trip_summary(plan: TripPlan, routed: RoutedTrip) -> dict:
    """The headline numbers.

    Two durations travel together and must never be confused: `total_drive_hours`
    is what the logs are built on (distance / 55 mph), while `provider_eta_hours`
    is the routing provider's own estimate, carried for display only. Each has a
    sibling string naming its basis so the UI can label them without hardcoding.

    The provider name comes from the router that actually answered, not from a
    constant here: the app supports more than one, and a summary that names the
    wrong one is worse than no label at all.
    """
    return {
        "total_distance_miles": round(routed.total_distance_miles, 1),
        "total_drive_hours": _hours(plan.total_drive_minutes),
        "drive_hours_basis": DRIVE_HOURS_BASIS,
        "provider_eta_hours": _hours(routed.provider_duration_seconds / 60),
        "provider_eta_source": routed.provider_name,
        "total_days": len(plan.log_days),
        "cycle_hours_remaining": _hours(plan.cycle_minutes_remaining),
    }


def _hours(minutes: float) -> float:
    return round(minutes / 60, 2)


def _totals_in_hours(totals: dict[str, int]) -> dict[str, float]:
    """The day's four totals in hours, guaranteed to sum to exactly 24.00.

    The engine works in whole minutes that always sum to 1440, but rounding each
    of the four to two decimal places independently can land on 23.99 or 24.01 --
    and "the four totals sum to exactly 24:00" is the headline invariant a
    reviewer checks by adding up the column. The residual is folded into the
    largest bucket, where a hundredth of an hour is invisible.
    """
    hours = {status: _hours(minutes) for status, minutes in totals.items()}
    residual = round(24.0 - sum(hours.values()), 2)
    if residual:
        biggest = max(hours, key=lambda status: hours[status])
        hours[biggest] = round(hours[biggest] + residual, 2)
    return hours
