"""The seam: three addresses -> the engine's `list[Leg]` -> the phase-1 engine.

Nothing here touches the network, and nothing here changes the engine.
"""

import pytest
import responses
from fixtures import START_AT
from service_fixtures import (
    NOMINATIM_MISS,
    NOMINATIM_URL,
    ORS_URL,
    SINGLE_DAY_METRES,
    SINGLE_DAY_SECONDS,
    nominatim_hit,
    ors_route,
)

from hos import Leg, plan_trip
from services import AddressNotFound, NominatimGeocoder, OpenRouteServiceRouter, plan_route
from services import geocoding as geocoding_module

ADDRESSES = ("Chicago, IL", "Indianapolis, IN", "Columbus, OH")


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    monkeypatch.setattr(geocoding_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(geocoding_module, "_last_request_at", 0.0)


@pytest.fixture
def services():
    return {
        "geocoder": NominatimGeocoder(cache={}, user_agent="eld-trip-planner/test"),
        "router": OpenRouteServiceRouter(api_key="test-key"),
    }


def mock_a_happy_trip(leg_metres=None, leg_seconds=None):
    for address in ADDRESSES:
        responses.get(NOMINATIM_URL, json=nominatim_hit(address))
    responses.post(
        ORS_URL,
        json=ors_route(leg_metres or SINGLE_DAY_METRES, leg_seconds or SINGLE_DAY_SECONDS),
    )


@responses.activate
def test_builds_the_legs_the_engine_already_takes(services):
    mock_a_happy_trip()
    routed = plan_route(*ADDRESSES, **services)

    assert routed.legs == [
        Leg(120.0, "pickup", "Chicago, IL", "Indianapolis, IN"),
        Leg(260.0, "dropoff", "Indianapolis, IN", "Columbus, OH"),
    ]
    assert all(isinstance(leg, Leg) for leg in routed.legs)
    assert routed.total_distance_miles == 380.0


@responses.activate
def test_routed_legs_drive_the_existing_engine(services):
    mock_a_happy_trip()
    routed = plan_route(*ADDRESSES, **services)

    plan = plan_trip(routed.legs, current_cycle_used_hours=10, start_at=START_AT)
    assert len(plan.log_days) == 1
    assert sum(plan.log_days[0].totals.values()) == 1440


@responses.activate
def test_ors_duration_never_reaches_the_hos_math(services):
    """The guard on our stated assumption.

    ORS is told the trip takes 40 hours. Drive time must still come out as
    380 mi / 55 mph, and the log must be identical to the one built from the
    same distances with a sane duration. If anyone ever wires
    `provider_duration_seconds` into the engine, this fails.
    """
    mock_a_happy_trip(leg_seconds=[20 * 3600, 20 * 3600])
    routed = plan_route(*ADDRESSES, **services)
    assert routed.provider_duration_seconds == 40 * 3600, "the absurd duration was captured"

    plan = plan_trip(routed.legs, 10, START_AT)
    driving = sum(s.minutes for s in plan.timeline if s.status == "driving")
    assert driving == pytest.approx(380 / 55 * 60, abs=2), (
        f"drive time was {driving} min; it must follow 55 mph, not the provider"
    )

    from_hardcoded = plan_trip([Leg(120.0, "pickup"), Leg(260.0, "dropoff")], 10, START_AT)
    assert [s.minutes for s in plan.timeline] == [s.minutes for s in from_hardcoded.timeline]


@responses.activate
def test_geometry_comes_back_ready_for_leaflet(services):
    mock_a_happy_trip()
    routed = plan_route(*ADDRESSES, **services)
    assert routed.geometry[0] == (41.8755616, -87.6244212)


@responses.activate
def test_places_are_resolved_for_the_map_markers(services):
    mock_a_happy_trip()
    routed = plan_route(*ADDRESSES, **services)
    assert set(routed.places) == {"current", "pickup", "dropoff"}
    assert routed.places["pickup"].latitude == 39.7683331


@responses.activate
def test_a_bad_address_raises_before_any_routing_call(services):
    responses.get(NOMINATIM_URL, json=nominatim_hit("Chicago, IL"))
    responses.get(NOMINATIM_URL, json=NOMINATIM_MISS)

    with pytest.raises(AddressNotFound, match="pickup location"):
        plan_route("Chicago, IL", "asdfqwerzxcv", "Columbus, OH", **services)

    assert not [c for c in responses.calls if "openrouteservice" in c.request.url], (
        "should not pay for a routing call when an address is already unresolvable"
    )
