"""OpenRouteService wrapper. No test here touches the network."""

import json

import pytest
import requests
import responses
from service_fixtures import (
    ORS_URL,
    SINGLE_DAY_METRES,
    SINGLE_DAY_SECONDS,
    ors_route,
)

from services import OpenRouteServiceRouter, RoutingError

WAYPOINTS = [(41.8755616, -87.6244212), (39.7683331, -86.1583502), (39.9622601, -82.9987942)]


@pytest.fixture
def router():
    return OpenRouteServiceRouter(api_key="test-key")


@responses.activate
def test_three_waypoints_give_two_legs_in_miles(router):
    responses.post(ORS_URL, json=ors_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS))
    result = router.route(WAYPOINTS)
    assert result.leg_distances_miles == [120.0, 260.0]
    assert result.total_distance_miles == 380.0


@responses.activate
def test_geometry_is_flipped_to_lat_lng(router):
    """ORS returns GeoJSON [lng, lat]; Leaflet needs (lat, lng)."""
    responses.post(ORS_URL, json=ors_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS))
    result = router.route(WAYPOINTS)
    assert result.geometry[0] == (41.8755616, -87.6244212)
    for lat, lng in result.geometry:
        assert -90 <= lat <= 90 and -180 <= lng <= 180
        assert lat > 0 and lng < 0, "US coordinates: positive lat, negative lng"


@responses.activate
def test_request_uses_the_truck_profile_and_lng_lat_order(router):
    responses.post(ORS_URL, json=ors_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS))
    router.route(WAYPOINTS)
    call = responses.calls[0].request
    assert "driving-hgv" in call.url, "must use the HGV profile, not the car profile"
    assert call.headers["Authorization"] == "test-key"
    sent = json.loads(call.body)["coordinates"]
    assert sent[0] == [-87.6244212, 41.8755616], "ORS takes [lng, lat]"


@responses.activate
def test_provider_duration_is_captured_for_display(router):
    responses.post(ORS_URL, json=ors_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS))
    result = router.route(WAYPOINTS)
    assert result.provider_duration_seconds == 7.5 * 3600


def test_missing_api_key_raises_before_any_request():
    with pytest.raises(RoutingError, match="ORS_API_KEY"):
        OpenRouteServiceRouter(api_key="").route(WAYPOINTS)


def test_fewer_than_two_waypoints_raises(router):
    with pytest.raises(RoutingError):
        router.route([(41.87, -87.62)])


@responses.activate
@pytest.mark.parametrize(
    "status, expected",
    [
        (401, "key was rejected"),
        (403, "key was rejected"),
        (429, "rate limiting"),
        (500, "HTTP 500"),
    ],
)
def test_http_errors_become_readable_routing_errors(router, status, expected):
    responses.post(ORS_URL, status=status, json={})
    with pytest.raises(RoutingError, match=expected):
        router.route(WAYPOINTS)


@responses.activate
def test_provider_error_message_is_surfaced(router):
    responses.post(
        ORS_URL,
        status=404,
        json={"error": {"code": 2010, "message": "Could not find routable point"}},
    )
    with pytest.raises(RoutingError, match="Could not find routable point"):
        router.route(WAYPOINTS)


@responses.activate
def test_unreachable_provider_raises_routing_error(router):
    responses.post(ORS_URL, body=requests.ConnectionError("boom"))
    with pytest.raises(RoutingError, match="Could not reach"):
        router.route(WAYPOINTS)


@responses.activate
def test_timeout_raises_routing_error(router):
    responses.post(ORS_URL, body=requests.Timeout("slow"))
    with pytest.raises(RoutingError, match="Could not reach"):
        router.route(WAYPOINTS)


@responses.activate
def test_no_route_found_raises(router):
    responses.post(ORS_URL, json={"type": "FeatureCollection", "features": []})
    with pytest.raises(RoutingError, match="No route"):
        router.route(WAYPOINTS)


@responses.activate
def test_wrong_leg_count_raises(router):
    """Three waypoints must come back as two segments; anything else is a bug."""
    responses.post(ORS_URL, json=ors_route([100.0], [100.0]))
    with pytest.raises(RoutingError, match="expected 2"):
        router.route(WAYPOINTS)


@responses.activate
def test_missing_geometry_raises(router):
    payload = ors_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS)
    payload["features"][0]["geometry"]["coordinates"] = []
    responses.post(ORS_URL, json=payload)
    with pytest.raises(RoutingError, match="no geometry"):
        router.route(WAYPOINTS)


@responses.activate
def test_unreadable_segment_raises(router):
    payload = ors_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS)
    del payload["features"][0]["properties"]["segments"][0]["distance"]
    responses.post(ORS_URL, json=payload)
    with pytest.raises(RoutingError, match="unreadable"):
        router.route(WAYPOINTS)
