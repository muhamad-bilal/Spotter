"""Canned provider payloads, shaped like the real ones."""

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-hgv/geojson"

PLACES = {
    "Chicago, IL": (41.8755616, -87.6244212),
    "Indianapolis, IN": (39.7683331, -86.1583502),
    "Columbus, OH": (39.9622601, -82.9987942),
}


def nominatim_hit(address: str) -> list[dict]:
    lat, lon = PLACES[address]
    return [{"lat": str(lat), "lon": str(lon), "display_name": address}]


NOMINATIM_MISS: list[dict] = []


def ors_route(leg_metres: list[float], leg_seconds: list[float]) -> dict:
    """A GeoJSON directions response with one segment per leg.

    Coordinates are [longitude, latitude] -- the order ORS actually returns, and
    the reverse of what Leaflet needs.
    """
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [-87.6244212, 41.8755616],
                        [-86.1583502, 39.7683331],
                        [-82.9987942, 39.9622601],
                    ],
                },
                "properties": {
                    "segments": [
                        {"distance": metres, "duration": seconds}
                        for metres, seconds in zip(leg_metres, leg_seconds)
                    ],
                    "summary": {
                        "distance": sum(leg_metres),
                        "duration": sum(leg_seconds),
                    },
                },
            }
        ],
    }


# 120 mi and 260 mi, matching the phase-1 SINGLE_DAY fixture.
SINGLE_DAY_METRES = [120 * 1609.344, 260 * 1609.344]
SINGLE_DAY_SECONDS = [2.5 * 3600, 5.0 * 3600]


GEOAPIFY_URL = "https://api.geoapify.com/v1/routing"


def geoapify_route(leg_metres: list[float], leg_seconds: list[float]) -> dict:
    """A Geoapify routing response.

    Two shape differences from ORS that the wrapper has to absorb: per-leg
    figures live under `properties.legs` with `time` rather than `duration`, and
    the geometry is a MultiLineString carrying one line per leg instead of a
    single LineString. Coordinates are still [longitude, latitude].
    """
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "mode": "truck",
                    "units": "metric",
                    "distance": sum(leg_metres),
                    "distance_units": "meters",
                    "time": sum(leg_seconds),
                    "legs": [
                        {"distance": metres, "time": seconds}
                        for metres, seconds in zip(leg_metres, leg_seconds)
                    ],
                },
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [
                        [[-87.6244212, 41.8755616], [-86.1583502, 39.7683331]],
                        [[-86.1583502, 39.7683331], [-82.9987942, 39.9622601]],
                    ],
                },
            }
        ],
    }
