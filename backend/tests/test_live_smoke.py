"""OPTIONAL live smoke tests -- these hit the real Nominatim and routing APIs.

Excluded from the default suite (see `addopts` in pytest.ini). Run deliberately:

    pytest -m live -v

Each provider skips cleanly when its key is absent, so having only a Geoapify
key runs the Geoapify tests and skips the OpenRouteService ones.

Nothing here asserts exact distances -- real road networks change -- only that
the pipeline resolves end to end into the shape the engine already consumes.
"""

import os

import pytest

from hos import Leg, plan_trip
from services import GeoapifyRouter, OpenRouteServiceRouter, plan_route
from services import env as env_module

pytestmark = pytest.mark.live

CHICAGO_TO_COLUMBUS = ("Chicago, IL", "Indianapolis, IN", "Columbus, OH")


def key(name):
    """Read through the .env loader, so a key in backend/.env counts."""
    return env_module.get(name) or os.environ.get(name, "")


def check_routed_trip(routed):
    assert len(routed.legs) == 2
    assert all(isinstance(leg, Leg) for leg in routed.legs)
    assert routed.legs[0].end_action == "pickup"
    assert routed.legs[1].end_action == "dropoff"

    # Chicago -> Indianapolis -> Columbus is roughly 350-550 road miles.
    assert 300 < routed.total_distance_miles < 600, (
        f"got {routed.total_distance_miles:.0f} mi, which looks wrong for this trip"
    )
    assert len(routed.geometry) > 10, "expected a real polyline"
    assert all(30 < lat < 45 and -90 < lng < -80 for lat, lng in routed.geometry)

    # And the whole point: the logs still run off distance / 55 mph.
    plan = plan_trip(routed.legs, current_cycle_used_hours=10)
    assert plan.log_days
    for day in plan.log_days:
        assert sum(day.totals.values()) == 1440
    driving = sum(s.minutes for s in plan.timeline if s.status == "driving")
    assert driving == pytest.approx(routed.total_distance_miles / 55 * 60, abs=5)


# --- Geoapify ---------------------------------------------------------------


@pytest.fixture(scope="module")
def geoapify_routed():
    if not key("GEOAPIFY_API_KEY"):
        pytest.skip("GEOAPIFY_API_KEY is not set; skipping the live Geoapify test")
    router = GeoapifyRouter()
    routed = plan_route(*CHICAGO_TO_COLUMBUS, router=router)
    return routed, router


def test_live_geoapify_route_feeds_the_engine(geoapify_routed):
    routed, _ = geoapify_routed
    check_routed_trip(routed)


def test_live_geoapify_reports_which_mode_it_used(geoapify_routed):
    """Truck if the plan allows it, driving if it fell back -- never silent."""
    _, router = geoapify_routed
    assert router.mode_used in ("truck", "drive")


# --- OpenRouteService -------------------------------------------------------


@pytest.fixture(scope="module")
def ors_routed():
    if not key("ORS_API_KEY"):
        pytest.skip("ORS_API_KEY is not set; skipping the live OpenRouteService test")
    return plan_route(*CHICAGO_TO_COLUMBUS, router=OpenRouteServiceRouter())


def test_live_ors_route_feeds_the_engine(ors_routed):
    check_routed_trip(ors_routed)
