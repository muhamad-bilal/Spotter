"""Give every route stop a position on the map.

The engine emits stops on a clock, not a map -- it knows a fuel stop happened after
1000 miles, not where that is. Only the three geocoded addresses have real
coordinates. This walks the routing provider's polyline and places each remaining
stop at the fraction of the route its odometer reading corresponds to.

Distances are measured along the polyline itself rather than trusting it to be
evenly spaced, and the odometer is converted to a fraction of the total so a
simplified geometry (fewer vertices than the real road) still places stops
proportionally.
"""

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_MILES = 3958.7613


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lat, lng) points, in miles."""
    lat1, lng1 = radians(a[0]), radians(a[1])
    lat2, lng2 = radians(b[0]), radians(b[1])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * asin(sqrt(min(1.0, h)))


class PolylineLocator:
    """Maps a distance along a route onto a coordinate."""

    def __init__(self, geometry: list[tuple[float, float]]):
        self.geometry = list(geometry)
        self.cumulative = [0.0]
        for previous, current in zip(self.geometry, self.geometry[1:]):
            self.cumulative.append(self.cumulative[-1] + haversine_miles(previous, current))

    @property
    def length_miles(self) -> float:
        return self.cumulative[-1] if self.cumulative else 0.0

    def at_fraction(self, fraction: float) -> tuple[float, float] | None:
        """Coordinate at `fraction` (0..1) of the way along the polyline."""
        if not self.geometry:
            return None
        if len(self.geometry) == 1 or self.length_miles == 0:
            return self.geometry[0]

        target = max(0.0, min(1.0, fraction)) * self.length_miles
        for index, reached in enumerate(self.cumulative):
            if reached >= target:
                if index == 0:
                    return self.geometry[0]
                # Interpolate between the vertex before the target and this one.
                span = reached - self.cumulative[index - 1]
                within = (target - self.cumulative[index - 1]) / span if span else 0.0
                start, end = self.geometry[index - 1], self.geometry[index]
                return (
                    start[0] + (end[0] - start[0]) * within,
                    start[1] + (end[1] - start[1]) * within,
                )
        return self.geometry[-1]

    def at_odometer(self, miles: float, total_miles: float) -> tuple[float, float] | None:
        """Coordinate after `miles` driven out of `total_miles`."""
        if total_miles <= 0:
            return self.at_fraction(0.0)
        return self.at_fraction(miles / total_miles)
