"""Third-party service wrappers. Pure Python -- imports nothing from Django."""

from .exceptions import (
    AddressNotFound,
    GeocodingError,
    RoutingError,
    TripPlanningError,
)
from .geocoding import NominatimGeocoder, Place
from .route_planner import RoutedTrip, plan_route
from .routing import (
    GeoapifyRouter,
    OpenRouteServiceRouter,
    RouteResult,
    default_router,
)

__all__ = [
    "AddressNotFound",
    "GeocodingError",
    "RoutingError",
    "TripPlanningError",
    "NominatimGeocoder",
    "Place",
    "OpenRouteServiceRouter",
    "GeoapifyRouter",
    "default_router",
    "RouteResult",
    "RoutedTrip",
    "plan_route",
]
