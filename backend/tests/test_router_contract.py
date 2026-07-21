"""One contract, two providers.

`plan_route` cannot tell the routers apart, so anything it relies on must hold
for both. Rather than duplicating the geometry-flip assertion in each provider's
own test file, every case here runs against both -- which means a third provider
added later inherits the whole suite by appending one entry to ROUTERS.
"""

import pytest
import responses
from service_fixtures import (
    GEOAPIFY_URL,
    ORS_URL,
    SINGLE_DAY_METRES,
    SINGLE_DAY_SECONDS,
    geoapify_route,
    ors_route,
)

from services import GeoapifyRouter, OpenRouteServiceRouter, RoutingError

WAYPOINTS = [
    (41.8755616, -87.6244212),
    (39.7683331, -86.1583502),
    (39.9622601, -82.9987942),
]


def register_ors(metres=None, seconds=None, **kwargs):
    responses.post(
        ORS_URL,
        json=ors_route(metres or SINGLE_DAY_METRES, seconds or SINGLE_DAY_SECONDS),
        **kwargs,
    )


def register_geoapify(metres=None, seconds=None, **kwargs):
    responses.get(
        GEOAPIFY_URL,
        json=geoapify_route(metres or SINGLE_DAY_METRES, seconds or SINGLE_DAY_SECONDS),
        **kwargs,
    )


ROUTERS = [
    pytest.param(
        lambda: OpenRouteServiceRouter(api_key="k"),
        register_ors,
        "OpenRouteService driving-hgv",
        id="ors",
    ),
    pytest.param(
        lambda: GeoapifyRouter(api_key="k"),
        register_geoapify,
        "Geoapify truck",
        id="geoapify",
    ),
]


@pytest.mark.parametrize("build, register, provider_name", ROUTERS)
@responses.activate
def test_geometry_comes_back_as_lat_lng(build, register, provider_name):
    """Both providers speak GeoJSON [lng, lat]; both must return (lat, lng).

    Getting this backwards puts the route in the Indian Ocean, so it is asserted
    per provider and by absolute position, not just by shape.
    """
    register()
    geometry = build().route(WAYPOINTS).geometry

    assert geometry[0] == (41.8755616, -87.6244212)
    for lat, lng in geometry:
        assert -90 <= lat <= 90 and -180 <= lng <= 180
        assert lat > 0 and lng < 0, "US coordinates: positive lat, negative lng"


@pytest.mark.parametrize("build, register, provider_name", ROUTERS)
@responses.activate
def test_distances_are_miles_one_per_leg(build, register, provider_name):
    register()
    result = build().route(WAYPOINTS)
    assert result.leg_distances_miles == [120.0, 260.0]
    assert result.total_distance_miles == 380.0


@pytest.mark.parametrize("build, register, provider_name", ROUTERS)
@responses.activate
def test_provider_duration_is_seconds(build, register, provider_name):
    register()
    assert build().route(WAYPOINTS).provider_duration_seconds == 7.5 * 3600


@pytest.mark.parametrize("build, register, provider_name", ROUTERS)
@responses.activate
def test_each_router_names_itself(build, register, provider_name):
    """The name travels with the result, so the caller never has to guess.

    Before this, the summary printed a hardcoded provider string and happily
    credited OpenRouteService for routes Geoapify had produced.
    """
    register()
    assert build().route(WAYPOINTS).provider_name == provider_name


@pytest.mark.parametrize("build, register, provider_name", ROUTERS)
@responses.activate
def test_leg_count_must_match_the_waypoints(build, register, provider_name):
    register(metres=[100.0], seconds=[100.0])
    with pytest.raises(RoutingError, match="expected 2"):
        build().route(WAYPOINTS)


@pytest.mark.parametrize("build, register, provider_name", ROUTERS)
def test_too_few_waypoints_is_rejected(build, register, provider_name):
    with pytest.raises(RoutingError, match="at least two"):
        build().route([(41.87, -87.62)])


@pytest.mark.parametrize("build, register, provider_name", ROUTERS)
@responses.activate
def test_result_feeds_the_engine_unchanged(build, register, provider_name):
    """Whatever the provider, the output must drop straight into the engine."""
    from hos import Leg, plan_trip

    register()
    result = build().route(WAYPOINTS)
    legs = [
        Leg(result.leg_distances_miles[0], "pickup"),
        Leg(result.leg_distances_miles[1], "dropoff"),
    ]
    plan = plan_trip(legs, current_cycle_used_hours=10)

    driving = sum(s.minutes for s in plan.timeline if s.status == "driving")
    assert driving == pytest.approx(380 / 55 * 60, abs=2), (
        "drive time must follow 55 mph regardless of which provider routed it"
    )
