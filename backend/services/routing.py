"""Coordinates -> route, on a truck profile.

Two providers behind one interface, `route(waypoints) -> RouteResult`: Geoapify
(the default) and OpenRouteService (used when only its key is present). A shared
contract test runs against both. `default_router()` picks by which key is set.

One request carries all three waypoints, so a trip costs a single call and comes
back with one continuous geometry plus one segment per leg -- which is exactly the
shape the HOS engine wants.

Two provider quirks handled here so nothing downstream has to know about them:
GeoJSON coordinates arrive as [longitude, latitude] and are flipped to
(latitude, longitude) for Leaflet; distances arrive in metres and leave in miles.
"""

import os
import re
from dataclasses import dataclass

import requests

from . import env
from .exceptions import RoutingError

ORS_URL = "https://api.openrouteservice.org/v2/directions/{profile}/geojson"
PROFILE = "driving-hgv"  # truck profile: respects weight/height restrictions
METRES_PER_MILE = 1609.344
REQUEST_TIMEOUT_SECONDS = 20


@dataclass(frozen=True)
class RouteResult:
    leg_distances_miles: list[float]
    geometry: list[tuple[float, float]]  # (lat, lng), ready for Leaflet
    provider_duration_seconds: float
    """The provider's own estimate. Captured for DISPLAY ONLY.

    It must never reach the HOS engine: drive time is always distance / 55 mph so
    the same trip always produces the same log. A test asserts this holds.
    """

    provider_name: str
    """Who actually produced this route, and on which profile.

    Reported by the router rather than assumed by the caller -- otherwise the
    summary can claim one provider while another did the work. Geoapify folds
    its mode in here ("Geoapify truck" vs "Geoapify drive"), so a fallback to
    car routing is visible on screen instead of silent.
    """

    @property
    def total_distance_miles(self) -> float:
        return sum(self.leg_distances_miles)


class OpenRouteServiceRouter:
    def __init__(self, api_key: str | None = None):
        # Read at construction, not import, so tests and deploys can set it late.
        self._api_key = api_key if api_key is not None else os.environ.get("ORS_API_KEY", "")

    def route(self, waypoints: list[tuple[float, float]]) -> RouteResult:
        """Route through waypoints given as (lat, lng). Returns one leg per gap."""
        if len(waypoints) < 2:
            raise RoutingError("A route needs at least two points.")
        if not self._api_key:
            raise RoutingError(
                "No OpenRouteService API key configured. Set the ORS_API_KEY "
                "environment variable."
            )

        payload = self._post(waypoints)
        return self._parse(payload, expected_legs=len(waypoints) - 1)

    def _post(self, waypoints: list[tuple[float, float]]) -> dict:
        try:
            response = requests.post(
                ORS_URL.format(profile=PROFILE),
                # ORS takes [lng, lat] -- the reverse of how we carry coordinates.
                json={"coordinates": [[lng, lat] for lat, lng in waypoints]},
                headers={
                    "Authorization": self._api_key,
                    "Content-Type": "application/json",
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise RoutingError(
                "Could not reach the routing service. Please try again."
            ) from exc

        if response.status_code != 200:
            raise RoutingError(_describe_failure(response))
        try:
            return response.json()
        except ValueError as exc:
            raise RoutingError("Routing service returned malformed JSON.") from exc

    def _parse(self, payload: dict, expected_legs: int) -> RouteResult:
        features = payload.get("features") or []
        if not features:
            raise RoutingError("No route could be found between those locations.")

        feature = features[0]
        segments = feature.get("properties", {}).get("segments") or []
        if len(segments) != expected_legs:
            raise RoutingError(
                f"Routing service returned {len(segments)} legs, expected {expected_legs}."
            )

        coordinates = feature.get("geometry", {}).get("coordinates") or []
        if not coordinates:
            raise RoutingError("Routing service returned a route with no geometry.")

        try:
            distances = [seg["distance"] / METRES_PER_MILE for seg in segments]
            duration = sum(seg["duration"] for seg in segments)
            geometry = [(float(lat), float(lng)) for lng, lat in coordinates]
        except (KeyError, TypeError, ValueError) as exc:
            raise RoutingError("Routing service returned an unreadable route.") from exc

        return RouteResult(
            leg_distances_miles=[round(d, 2) for d in distances],
            geometry=geometry,
            provider_duration_seconds=duration,
            provider_name=f"OpenRouteService {PROFILE}",
        )


def _describe_failure(response: requests.Response) -> str:
    if response.status_code in (401, 403):
        return "The OpenRouteService API key was rejected. Check ORS_API_KEY."
    if response.status_code == 429:
        return "The routing service is rate limiting us. Please try again shortly."
    # ORS puts a human-readable reason in the body for routing failures.
    try:
        message = response.json().get("error", {})
        message = message.get("message") if isinstance(message, dict) else message
    except ValueError:
        message = None
    if message:
        return f"Could not route this trip: {message}"
    return f"Routing service returned HTTP {response.status_code}."


# --------------------------------------------------------------------------
# Geoapify
# --------------------------------------------------------------------------

GEOAPIFY_URL = "https://api.geoapify.com/v1/routing"
GEOAPIFY_TRUCK_MODE = "truck"
GEOAPIFY_FALLBACK_MODE = "drive"
# Geoapify's synchronous routing rejects trips longer than this. The raw
# rejection talks about metres and an "asynchronous batch API call", which means
# nothing to a driver, so we translate it into miles.
GEOAPIFY_MAX_METRES = 10_000_000


class GeoapifyRouter:
    """The same contract as OpenRouteServiceRouter, against Geoapify.

    Both expose `route(waypoints) -> RouteResult`, so `plan_route` cannot tell
    them apart and nothing downstream changes. A shared contract test asserts
    that both really do behave identically.

    Geoapify differs from ORS in three ways, all absorbed here: waypoints go in
    the query string as `lat,lon|lat,lon`, per-leg figures live under
    `properties.legs`, and the geometry comes back as a MultiLineString with one
    line per leg rather than a single LineString.
    """

    def __init__(self, api_key: str | None = None, mode: str = GEOAPIFY_TRUCK_MODE):
        self._api_key = api_key if api_key is not None else env.get("GEOAPIFY_API_KEY")
        self._mode = mode
        self._last_status: int | None = None
        # A distance-limit rejection is the same in any mode, so it must not
        # trigger the truck -> drive retry.
        self._last_over_limit: bool = False
        # Records which mode actually produced the route: free plans do not
        # always allow the truck profile, and the caller deserves to know which
        # one it got rather than silently receiving car routing.
        self.mode_used: str | None = None

    def route(self, waypoints: list[tuple[float, float]]) -> RouteResult:
        if len(waypoints) < 2:
            raise RoutingError("A route needs at least two points.")
        if not self._api_key:
            raise RoutingError(
                "No Geoapify API key configured. Set the GEOAPIFY_API_KEY "
                "environment variable."
            )

        payload, self.mode_used = self._get_with_fallback(waypoints)
        return self._parse(
            payload, expected_legs=len(waypoints) - 1, mode=self.mode_used
        )

    def _get_with_fallback(self, waypoints):
        """Try the truck profile, then fall back to driving if it is rejected.

        Only a 400 triggers the retry -- that is what an unsupported mode looks
        like on a free plan. A rejected key (401/403) or a rate limit must
        surface as itself, not be retried into a confusing second failure.
        """
        try:
            return self._get(waypoints, self._mode), self._mode
        except RoutingError:
            already_driving = self._mode == GEOAPIFY_FALLBACK_MODE
            mode_was_rejected = self._last_status == 400
            if already_driving or not mode_was_rejected or self._last_over_limit:
                raise
        return self._get(waypoints, GEOAPIFY_FALLBACK_MODE), GEOAPIFY_FALLBACK_MODE

    def _get(self, waypoints: list[tuple[float, float]], mode: str) -> dict:
        self._last_status = None
        self._last_over_limit = False
        try:
            response = requests.get(
                GEOAPIFY_URL,
                params={
                    # Geoapify takes lat,lon -- the same order we carry.
                    "waypoints": "|".join(f"{lat},{lng}" for lat, lng in waypoints),
                    "mode": mode,
                    "units": "metric",
                    "apiKey": self._api_key,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise RoutingError(
                "Could not reach the routing service. Please try again."
            ) from exc

        self._last_status = response.status_code
        if response.status_code != 200:
            over_limit = _geoapify_over_limit_message(response)
            self._last_over_limit = over_limit is not None
            raise RoutingError(over_limit or _describe_geoapify_failure(response))
        try:
            return response.json()
        except ValueError as exc:
            raise RoutingError("Routing service returned malformed JSON.") from exc

    def _parse(self, payload: dict, expected_legs: int, mode: str) -> RouteResult:
        features = payload.get("features") or []
        if not features:
            raise RoutingError("No route could be found between those locations.")

        feature = features[0]
        legs = feature.get("properties", {}).get("legs") or []
        if len(legs) != expected_legs:
            raise RoutingError(
                f"Routing service returned {len(legs)} legs, expected {expected_legs}."
            )

        geometry = _flatten_geoapify_geometry(feature.get("geometry") or {})
        if not geometry:
            raise RoutingError("Routing service returned a route with no geometry.")

        try:
            distances = [leg["distance"] / METRES_PER_MILE for leg in legs]
            duration = sum(leg["time"] for leg in legs)
        except (KeyError, TypeError, ValueError) as exc:
            raise RoutingError("Routing service returned an unreadable route.") from exc

        return RouteResult(
            leg_distances_miles=[round(d, 2) for d in distances],
            geometry=geometry,
            provider_duration_seconds=duration,
            provider_name=f"Geoapify {mode}",
        )


def _flatten_geoapify_geometry(geometry: dict) -> list[tuple[float, float]]:
    """MultiLineString (one line per leg) or LineString -> one (lat, lng) list."""
    coordinates = geometry.get("coordinates") or []
    kind = geometry.get("type")

    if kind == "LineString":
        lines = [coordinates]
    elif kind == "MultiLineString":
        lines = coordinates
    else:
        return []

    points: list[tuple[float, float]] = []
    for line in lines:
        for point in line:
            try:
                lng, lat = point[0], point[1]
                points.append((float(lat), float(lng)))
            except (IndexError, TypeError, ValueError) as exc:
                raise RoutingError("Routing service returned an unreadable route.") from exc
    return points


def _geoapify_over_limit_message(response: requests.Response) -> str | None:
    """Translate Geoapify's over-distance rejection into a message about miles.

    Returns None if this failure is something else. The raw rejection reads like
    "...N meters... greater than 10000000 meters limit... asynchronous batch API
    call", none of which is meaningful to a driver.
    """
    try:
        body = response.json()
        raw = str(body.get("message") or body.get("error") or "")
    except ValueError:
        raw = ""

    metres = [int(n) for n in re.findall(r"\d{6,}", raw)]
    lowered = raw.lower()
    over_limit = any(n >= GEOAPIFY_MAX_METRES for n in metres)
    talks_async = "async" in lowered or "batch" in lowered
    if not (over_limit or talks_async):
        return None

    limit_miles = round(GEOAPIFY_MAX_METRES / METRES_PER_MILE / 100) * 100  # ~6,200
    attempted = max((n for n in metres if n >= GEOAPIFY_MAX_METRES), default=None)
    if attempted is not None:
        miles = attempted / METRES_PER_MILE
        return (
            f"This trip is too long to route (about {miles:,.0f} miles). The routing "
            f"service supports trips up to roughly {limit_miles:,.0f} miles. "
            f"Try a shorter route."
        )
    return (
        f"This trip is too long to route. The routing service supports trips up to "
        f"roughly {limit_miles:,.0f} miles. Try a shorter route."
    )


def _describe_geoapify_failure(response: requests.Response) -> str:
    if response.status_code in (401, 403):
        return "The Geoapify API key was rejected. Check GEOAPIFY_API_KEY."
    if response.status_code == 429:
        return "The routing service is rate limiting us. Please try again shortly."
    try:
        body = response.json()
        message = body.get("message") or body.get("error")
    except ValueError:
        message = None
    if message:
        return f"Could not route this trip: {message}"
    return f"Routing service returned HTTP {response.status_code}."


def default_router():
    """The routing provider to use when a caller does not name one.

    Selected by which key is configured, so deployment is a matter of setting an
    environment variable rather than editing code.
    """
    if env.get("GEOAPIFY_API_KEY"):
        return GeoapifyRouter()
    return OpenRouteServiceRouter()
