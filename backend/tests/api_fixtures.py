"""A stand-in for `plan_route`, so API tests never touch the network.

This is the seam the endpoint injects: the view calls whatever planner it is given,
so the tests hand it one of these instead of the real geocode+route pipeline.
"""

from hos.types import Leg
from services.geocoding import Place
from services.route_planner import RoutedTrip

PLACES = {
    "current": Place("Chicago, IL", 41.8755616, -87.6244212),
    "pickup": Place("Indianapolis, IN", 39.7683331, -86.1583502),
    "dropoff": Place("Columbus, OH", 39.9622601, -82.9987942),
}

# A plausible polyline: Chicago -> Indianapolis -> Columbus with a few vertices.
GEOMETRY = [
    (41.8755616, -87.6244212),
    (41.0, -87.0),
    (40.2, -86.5),
    (39.7683331, -86.1583502),
    (39.75, -85.0),
    (39.8, -84.19),
    (39.9622601, -82.9987942),
]

VALID_REQUEST = {
    "current_location": "Chicago, IL",
    "pickup_location": "Indianapolis, IN",
    "dropoff_location": "Columbus, OH",
    "current_cycle_used": 10,
}


def fake_planner(
    to_pickup=120.0,
    to_dropoff=260.0,
    duration_seconds=7.5 * 3600,
    provider_name="Geoapify truck",
):
    """Build a planner callable returning a fixed RoutedTrip."""

    def planner(current_location, pickup_location, dropoff_location):
        return RoutedTrip(
            legs=[
                Leg(to_pickup, "pickup", current_location, pickup_location),
                Leg(to_dropoff, "dropoff", pickup_location, dropoff_location),
            ],
            places=PLACES,
            geometry=GEOMETRY,
            provider_duration_seconds=duration_seconds,
            provider_name=provider_name,
        )

    return planner


def failing_planner(exception):
    def planner(*_args, **_kwargs):
        raise exception

    return planner
