"""Three addresses in, the engine's `list[Leg]` out.

This is the only place that knows both the providers and the engine. Phase 3's
view calls `plan_route`, hands `routed.legs` straight to `plan_trip`, and keeps
`geometry` and `provider_duration_seconds` for the map and the summary panel.

`Leg` is imported from the engine unchanged -- routing adapts to the engine, not
the other way round.
"""

from dataclasses import dataclass

from hos.types import Leg

from .geocoding import NominatimGeocoder, Place
from .routing import GeoapifyRouter, OpenRouteServiceRouter, default_router


@dataclass(frozen=True)
class RoutedTrip:
    legs: list[Leg]
    places: dict[str, Place]  # "current" | "pickup" | "dropoff"
    geometry: list[tuple[float, float]]
    provider_duration_seconds: float
    """The routing provider's estimate, for display only -- never fed to the engine."""

    provider_name: str
    """Which provider and profile produced this route, e.g. "Geoapify truck"."""

    @property
    def total_distance_miles(self) -> float:
        return sum(leg.distance_miles for leg in self.legs)


def plan_route(
    current_location: str,
    pickup_location: str,
    dropoff_location: str,
    geocoder: NominatimGeocoder | None = None,
    router: OpenRouteServiceRouter | GeoapifyRouter | None = None,
) -> RoutedTrip:
    """Geocode the three inputs, route between them, and build the engine's legs.

    Raises AddressNotFound / GeocodingError / RoutingError, which the API layer
    turns into 400s.
    """
    geocoder = geocoder or NominatimGeocoder()
    router = router or default_router()

    places = {
        "current": geocoder.geocode(current_location, "current location"),
        "pickup": geocoder.geocode(pickup_location, "pickup location"),
        "dropoff": geocoder.geocode(dropoff_location, "dropoff location"),
    }

    result = router.route([(p.latitude, p.longitude) for p in places.values()])
    to_pickup, to_dropoff = result.leg_distances_miles

    return RoutedTrip(
        legs=[
            Leg(to_pickup, "pickup", current_location, pickup_location),
            Leg(to_dropoff, "dropoff", pickup_location, dropoff_location),
        ],
        places=places,
        geometry=result.geometry,
        provider_duration_seconds=result.provider_duration_seconds,
        provider_name=result.provider_name,
    )
