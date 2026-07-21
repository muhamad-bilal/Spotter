"""Address -> coordinates, via Nominatim.

Swapping providers means writing another class with the same `geocode` signature
and pointing `route_planner` at it. Nothing else in the codebase knows the
provider exists.

Two things Nominatim's usage policy requires and that are easy to get wrong:
a descriptive User-Agent (requests without one are blocked), and at most one
request per second. Both are handled here rather than left to callers.
"""

import os
import threading
import time
from dataclasses import dataclass

import requests

from .exceptions import AddressNotFound, GeocodingError

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
MIN_SECONDS_BETWEEN_REQUESTS = 1.0
DEFAULT_USER_AGENT = "eld-trip-planner/1.0"
REQUEST_TIMEOUT_SECONDS = 10

# Shared across instances on purpose: the throttle and cache must hold for the
# whole process, and the API layer builds a fresh service per request. Tests pass
# their own cache so they do not leak results into each other.
_SHARED_CACHE: dict[str, "Place"] = {}
_throttle_lock = threading.Lock()
_last_request_at = 0.0


@dataclass(frozen=True)
class Place:
    label: str
    latitude: float
    longitude: float


class NominatimGeocoder:
    def __init__(self, cache: dict | None = None, user_agent: str | None = None):
        self._cache = _SHARED_CACHE if cache is None else cache
        self._user_agent = (
            user_agent or os.environ.get("NOMINATIM_USER_AGENT") or DEFAULT_USER_AGENT
        )

    def geocode(self, address: str, field: str = "") -> Place:
        """Resolve one address. Raises AddressNotFound if there is no match."""
        key = address.strip().lower()
        if not key:
            raise AddressNotFound(address, field)
        if key in self._cache:
            return self._cache[key]

        payload = self._get(address, field)
        if not payload:
            raise AddressNotFound(address, field)

        top = payload[0]
        try:
            place = Place(
                label=top.get("display_name", address),
                latitude=float(top["lat"]),
                longitude=float(top["lon"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GeocodingError(
                f"Geocoding returned an unreadable result for {address!r}"
            ) from exc

        self._cache[key] = place
        return place

    def _get(self, address: str, field: str) -> list[dict]:
        _wait_for_rate_limit()
        try:
            response = requests.get(
                NOMINATIM_URL,
                params={"q": address, "format": "json", "limit": 1},
                headers={"User-Agent": self._user_agent},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise GeocodingError(
                "Could not reach the geocoding service. Please try again."
            ) from exc

        if response.status_code != 200:
            raise GeocodingError(
                f"Geocoding service returned HTTP {response.status_code}."
            )
        try:
            return response.json()
        except ValueError as exc:
            raise GeocodingError("Geocoding service returned malformed JSON.") from exc


def _wait_for_rate_limit() -> None:
    """Block until at least a second has passed since the last request."""
    global _last_request_at
    with _throttle_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
        _last_request_at = time.monotonic()
