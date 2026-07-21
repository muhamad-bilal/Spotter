"""Failures the API layer turns into 400s in phase 3.

Every one carries a message safe to show a driver in the form -- no stack traces,
no provider internals.
"""


class TripPlanningError(Exception):
    """Base for anything that stops a trip being planned."""


class GeocodingError(TripPlanningError):
    """The geocoding provider failed or was unreachable."""


class AddressNotFound(GeocodingError):
    """An address could not be resolved. `field` names which input was bad."""

    def __init__(self, address: str, field: str = ""):
        self.address = address
        self.field = field
        where = f" for {field}" if field else ""
        super().__init__(f"Could not locate the address{where}: {address!r}")


class RoutingError(TripPlanningError):
    """The routing provider failed, was unreachable, or found no route."""
