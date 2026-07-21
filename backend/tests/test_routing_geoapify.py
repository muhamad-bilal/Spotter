"""Geoapify wrapper. No test here touches the network."""

import pytest
import requests
import responses
from service_fixtures import (
    GEOAPIFY_URL,
    SINGLE_DAY_METRES,
    SINGLE_DAY_SECONDS,
    geoapify_route,
)

from services import GeoapifyRouter, RoutingError

WAYPOINTS = [
    (41.8755616, -87.6244212),
    (39.7683331, -86.1583502),
    (39.9622601, -82.9987942),
]


@pytest.fixture
def router():
    return GeoapifyRouter(api_key="test-key")


def query(call):
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(call.request.url).query)


@responses.activate
def test_three_waypoints_give_two_legs_in_miles(router):
    responses.get(GEOAPIFY_URL, json=geoapify_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS))
    result = router.route(WAYPOINTS)
    assert result.leg_distances_miles == [120.0, 260.0]
    assert result.total_distance_miles == 380.0


@responses.activate
def test_multilinestring_is_flattened_in_leg_order(router):
    """Geoapify returns one line per leg; the map needs a single continuous path."""
    responses.get(GEOAPIFY_URL, json=geoapify_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS))
    geometry = router.route(WAYPOINTS).geometry
    assert len(geometry) == 4
    assert geometry[0] == (41.8755616, -87.6244212)
    assert geometry[-1] == (39.9622601, -82.9987942)


@responses.activate
def test_a_linestring_geometry_is_also_accepted(router):
    payload = geoapify_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS)
    payload["features"][0]["geometry"] = {
        "type": "LineString",
        "coordinates": [[-87.6244212, 41.8755616], [-82.9987942, 39.9622601]],
    }
    responses.get(GEOAPIFY_URL, json=payload)
    geometry = router.route(WAYPOINTS).geometry
    assert geometry == [(41.8755616, -87.6244212), (39.9622601, -82.9987942)]


@responses.activate
def test_request_uses_truck_mode_and_lat_lng_order(router):
    responses.get(GEOAPIFY_URL, json=geoapify_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS))
    router.route(WAYPOINTS)
    sent = query(responses.calls[0])
    assert sent["mode"] == ["truck"], "must ask for the truck profile, not a car"
    assert sent["apiKey"] == ["test-key"]
    # Geoapify takes lat,lon -- the opposite of ORS's [lng, lat].
    assert sent["waypoints"][0].startswith("41.8755616,-87.6244212")
    assert sent["waypoints"][0].count("|") == 2


@responses.activate
def test_provider_duration_is_captured_for_display(router):
    responses.get(GEOAPIFY_URL, json=geoapify_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS))
    assert router.route(WAYPOINTS).provider_duration_seconds == 7.5 * 3600


def test_missing_api_key_raises_before_any_request():
    with pytest.raises(RoutingError, match="GEOAPIFY_API_KEY"):
        GeoapifyRouter(api_key="").route(WAYPOINTS)


def test_fewer_than_two_waypoints_raises(router):
    with pytest.raises(RoutingError):
        router.route([(41.87, -87.62)])


# --- truck mode falling back to driving ------------------------------------


@responses.activate
def test_truck_mode_falls_back_to_drive_on_a_rejected_mode(router):
    """Free plans do not always allow the truck profile."""
    responses.get(
        GEOAPIFY_URL,
        status=400,
        json={"statusCode": 400, "message": "mode is not supported on your plan"},
    )
    responses.get(GEOAPIFY_URL, json=geoapify_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS))

    result = router.route(WAYPOINTS)
    assert result.leg_distances_miles == [120.0, 260.0]
    assert router.mode_used == "drive", "the caller must be able to see it fell back"
    assert result.provider_name == "Geoapify drive", (
        "the summary must show car routing was used, not claim a truck route"
    )
    assert query(responses.calls[0])["mode"] == ["truck"]
    assert query(responses.calls[1])["mode"] == ["drive"]


@responses.activate
def test_a_rejected_key_does_not_trigger_a_retry(router):
    """Retrying a bad key would burn a second call and confuse the message."""
    responses.get(GEOAPIFY_URL, status=401, json={"message": "Invalid apiKey"})
    with pytest.raises(RoutingError, match="key was rejected"):
        router.route(WAYPOINTS)
    assert len(responses.calls) == 1


@responses.activate
def test_a_drive_mode_router_does_not_retry(router):
    responses.get(GEOAPIFY_URL, status=400, json={"message": "nope"})
    with pytest.raises(RoutingError):
        GeoapifyRouter(api_key="test-key", mode="drive").route(WAYPOINTS)
    assert len(responses.calls) == 1


# --- failures --------------------------------------------------------------


@responses.activate
@pytest.mark.parametrize(
    "status, expected",
    [(401, "key was rejected"), (403, "key was rejected"), (429, "rate limiting"), (500, "HTTP 500")],
)
def test_http_errors_become_readable_routing_errors(router, status, expected):
    responses.get(GEOAPIFY_URL, status=status, json={})
    with pytest.raises(RoutingError, match=expected):
        router.route(WAYPOINTS)


@responses.activate
def test_provider_message_is_surfaced(router):
    responses.get(
        GEOAPIFY_URL, status=500, json={"message": "No path found between waypoints"}
    )
    with pytest.raises(RoutingError, match="No path found"):
        router.route(WAYPOINTS)


@responses.activate
def test_unreachable_provider_raises_routing_error(router):
    responses.get(GEOAPIFY_URL, body=requests.ConnectionError("boom"))
    with pytest.raises(RoutingError, match="Could not reach"):
        router.route(WAYPOINTS)


@responses.activate
def test_timeout_raises_routing_error(router):
    responses.get(GEOAPIFY_URL, body=requests.Timeout("slow"))
    with pytest.raises(RoutingError, match="Could not reach"):
        router.route(WAYPOINTS)


@responses.activate
def test_no_route_found_raises(router):
    responses.get(GEOAPIFY_URL, json={"type": "FeatureCollection", "features": []})
    with pytest.raises(RoutingError, match="No route"):
        router.route(WAYPOINTS)


@responses.activate
def test_wrong_leg_count_raises(router):
    responses.get(GEOAPIFY_URL, json=geoapify_route([100.0], [100.0]))
    with pytest.raises(RoutingError, match="expected 2"):
        router.route(WAYPOINTS)


@responses.activate
def test_missing_geometry_raises(router):
    payload = geoapify_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS)
    payload["features"][0]["geometry"] = {}
    responses.get(GEOAPIFY_URL, json=payload)
    with pytest.raises(RoutingError, match="no geometry"):
        router.route(WAYPOINTS)


@responses.activate
def test_unreadable_leg_raises(router):
    payload = geoapify_route(SINGLE_DAY_METRES, SINGLE_DAY_SECONDS)
    del payload["features"][0]["properties"]["legs"][0]["distance"]
    responses.get(GEOAPIFY_URL, json=payload)
    with pytest.raises(RoutingError, match="unreadable"):
        router.route(WAYPOINTS)


@responses.activate
def test_malformed_json_raises(router):
    responses.get(GEOAPIFY_URL, body="not json", status=200)
    with pytest.raises(RoutingError, match="malformed"):
        router.route(WAYPOINTS)
