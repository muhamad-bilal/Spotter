"""POST /api/trips/ against a mocked routing pipeline.

No test here makes a network call: the view's planner is replaced with a fake, so
the endpoint is exercised end to end without an ORS key existing at all.
"""

import pytest
from api import views
from api.models import DutySegment, LogDay, RouteStop, Trip
from api.stop_locator import haversine_miles
from api_fixtures import VALID_REQUEST, fake_planner, failing_planner

from services import AddressNotFound, GeocodingError, RoutingError

pytestmark = pytest.mark.django_db

ENDPOINT = "/api/trips/"
STOP_KINDS = {"start", "pickup", "dropoff", "fuel", "break_30", "rest_10", "restart_34"}
DUTY_STATUSES = {"off_duty", "sleeper", "driving", "on_duty"}


@pytest.fixture(autouse=True)
def mocked_planner(monkeypatch):
    """Default every test to the happy-path fake; individual tests override it."""
    monkeypatch.setattr(views, "plan_route", fake_planner())


def post(client, **overrides):
    return client.post(
        ENDPOINT, {**VALID_REQUEST, **overrides}, content_type="application/json"
    )


# --- happy path -------------------------------------------------------------


def test_returns_201_with_the_contract_shape(client):
    response = post(client)
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"trip", "route", "logs"}
    assert set(body["route"]) == {"geometry", "stops"}


def test_trip_summary_fields(client):
    body = post(client).json()
    trip = body["trip"]
    assert trip["id"] > 0
    assert trip["total_distance_miles"] == 380.0
    assert trip["total_days"] == len(body["logs"])
    assert trip["cycle_hours_remaining"] > 0


def test_both_durations_are_present_and_distinct(client):
    """The HOS number drives the logs; the provider number is display only."""
    trip = post(client).json()["trip"]
    assert trip["total_drive_hours"] == pytest.approx(380 / 55, abs=0.05)
    assert trip["provider_eta_hours"] == 7.5
    assert trip["total_drive_hours"] != trip["provider_eta_hours"]
    assert "55 mph" in trip["drive_hours_basis"]
    assert trip["provider_eta_source"] == "Geoapify truck"


@pytest.mark.parametrize(
    "provider_name",
    ["Geoapify truck", "Geoapify drive", "OpenRouteService driving-hgv"],
)
def test_summary_names_the_router_that_actually_answered(
    client, monkeypatch, provider_name
):
    """The card must not claim one provider while another did the work.

    This used to be a hardcoded constant, so a Geoapify route was labelled
    OpenRouteService on screen.
    """
    monkeypatch.setattr(views, "plan_route", fake_planner(provider_name=provider_name))
    assert post(client).json()["trip"]["provider_eta_source"] == provider_name


def test_the_provider_name_survives_a_refetch(client, monkeypatch):
    """A stored trip keeps naming the provider that served it, not today's."""
    monkeypatch.setattr(views, "plan_route", fake_planner(provider_name="Geoapify drive"))
    created = post(client).json()

    monkeypatch.setattr(views, "plan_route", fake_planner(provider_name="Geoapify truck"))
    fetched = client.get(f"{ENDPOINT}{created['trip']['id']}/").json()

    assert fetched["trip"]["provider_eta_source"] == "Geoapify drive"


def test_a_geoapify_fallback_to_car_routing_is_visible(client, monkeypatch):
    """Falling back from truck to drive changes the route; say so on screen."""
    monkeypatch.setattr(views, "plan_route", fake_planner(provider_name="Geoapify drive"))
    source = post(client).json()["trip"]["provider_eta_source"]
    assert "drive" in source and "truck" not in source


def test_provider_eta_never_changes_the_logs(client, monkeypatch):
    """An absurd provider ETA must not move a single minute of the log."""
    baseline = post(client).json()["logs"]
    monkeypatch.setattr(views, "plan_route", fake_planner(duration_seconds=40 * 3600))
    inflated = post(client).json()
    assert inflated["trip"]["provider_eta_hours"] == 40.0
    assert inflated["logs"] == baseline


def test_logs_are_whole_days_in_the_documented_enum(client):
    for day in post(client).json()["logs"]:
        assert set(day["totals"]) == DUTY_STATUSES
        for segment in day["segments"]:
            assert segment["status"] in DUTY_STATUSES
            assert 0 <= segment["start_minute"] < segment["end_minute"] <= 1440


@pytest.mark.parametrize("legs", [(120.0, 260.0), (300.0, 1550.0), (200.0, 1400.0)])
def test_the_four_totals_sum_to_exactly_24(client, monkeypatch, legs):
    """The invariant a reviewer checks by adding up the column by hand.

    Exact, not approximate: the payload reports hours to two decimals, and
    rounding four independently-rounded numbers can land on 23.99.
    """
    monkeypatch.setattr(views, "plan_route", fake_planner(*legs))
    for day in post(client).json()["logs"]:
        assert round(sum(day["totals"].values()), 2) == 24.00, (
            f"{day['date']} totals sum to {sum(day['totals'].values())}: {day['totals']}"
        )


def test_stops_are_typed_positioned_and_ordered(client):
    stops = post(client).json()["route"]["stops"]
    kinds = [stop["kind"] for stop in stops]
    assert kinds[0] == "start"
    assert "pickup" in kinds and "dropoff" in kinds
    assert set(kinds) <= STOP_KINDS, f"undocumented stop kind in {kinds}"

    for stop in stops:
        assert stop["lat"] is not None and stop["lng"] is not None
        assert 25 < stop["lat"] < 50 and -125 < stop["lng"] < -65
        assert stop["arrive_at"] <= stop["depart_at"]


def test_resolved_locations_are_surfaced(client):
    """The geocoder's matched names come back so a wrong 'LA'/'NY' is visible."""
    trip = post(client).json()["trip"]
    resolved = trip["resolved_locations"]
    assert set(resolved) == {"current", "pickup", "dropoff"}
    assert resolved["pickup"] == "Indianapolis, IN"
    assert resolved["dropoff"] == "Columbus, OH"


def test_geocoded_stops_use_their_real_coordinates(client):
    """Pickup and dropoff must sit on the geocoded address, not an interpolation."""
    stops = {s["kind"]: s for s in post(client).json()["route"]["stops"]}
    assert stops["pickup"]["lat"] == pytest.approx(39.7683331)
    assert stops["dropoff"]["lat"] == pytest.approx(39.9622601)


def test_geometry_is_returned_for_the_map(client):
    geometry = post(client).json()["route"]["geometry"]
    assert len(geometry) > 1
    assert all(len(point) == 2 for point in geometry)


def test_interpolated_stops_advance_along_the_route(client, monkeypatch):
    """Fuel and rest pins must move down the route, not pile up on the origin.

    Only pickup and dropoff get real geocoded coordinates; everything else is
    positioned from the odometer. If that odometer failed to advance, every
    interpolated stop would sit on the start point and the map would look broken
    while every other assertion here still passed.
    """
    monkeypatch.setattr(views, "plan_route", fake_planner(300.0, 1550.0))
    stops = post(client).json()["route"]["stops"]

    origin = (stops[0]["lat"], stops[0]["lng"])
    interpolated = [s for s in stops if s["kind"] in {"fuel", "rest_10", "break_30"}]
    assert interpolated, "expected a long trip to insert fuel/rest stops"

    for stop in interpolated:
        assert haversine_miles(origin, (stop["lat"], stop["lng"])) > 25, (
            f"{stop['kind']} at {stop['arrive_at']} is sitting on the trip origin"
        )

    # Only the interpolated stops are compared. Pickup and dropoff are placed on
    # their real geocoded coordinates, which is a different (and authoritative)
    # basis -- mixing the two only lines up when the geometry's proportions match
    # the leg distances exactly, which is true of real routing data but not of a
    # hand-sketched fixture polyline.
    distances = [haversine_miles(origin, (s["lat"], s["lng"])) for s in interpolated]
    assert distances == sorted(distances), (
        f"interpolated stops are not ordered along the route: "
        f"{list(zip([s['kind'] for s in interpolated], distances))}"
    )


def test_the_fuel_stop_lands_near_its_thousand_mile_mark(client, monkeypatch):
    """1000 mi into an 1850-mi trip is ~54% of the way along the polyline."""
    monkeypatch.setattr(views, "plan_route", fake_planner(300.0, 1550.0))
    body = post(client).json()
    geometry = [tuple(point) for point in body["route"]["geometry"]]
    fuel = next(s for s in body["route"]["stops"] if s["kind"] == "fuel")

    route_length = sum(
        haversine_miles(a, b) for a, b in zip(geometry, geometry[1:])
    )
    reached = 0.0
    for a, b in zip(geometry, geometry[1:]):
        if haversine_miles(a, (fuel["lat"], fuel["lng"])) + haversine_miles(
            (fuel["lat"], fuel["lng"]), b
        ) <= haversine_miles(a, b) + 1.0:
            reached += haversine_miles(a, (fuel["lat"], fuel["lng"]))
            break
        reached += haversine_miles(a, b)

    assert reached / route_length == pytest.approx(1000 / 1850, abs=0.05), (
        f"fuel stop sits {reached / route_length:.0%} along the route, expected ~54%"
    )


def test_a_long_trip_produces_several_log_sheets(client, monkeypatch):
    monkeypatch.setattr(views, "plan_route", fake_planner(300.0, 1550.0))
    body = post(client).json()
    assert len(body["logs"]) > 1
    assert body["trip"]["total_days"] == len(body["logs"])
    assert any(s["kind"] == "fuel" for s in body["route"]["stops"])
    assert any(s["kind"] == "rest_10" for s in body["route"]["stops"])


# --- persistence ------------------------------------------------------------


def test_the_trip_is_persisted_with_its_children(client):
    body = post(client).json()
    trip = Trip.objects.get(pk=body["trip"]["id"])
    assert trip.pickup_location == "Indianapolis, IN"
    assert RouteStop.objects.filter(trip=trip).count() == len(body["route"]["stops"])
    assert LogDay.objects.filter(trip=trip).count() == len(body["logs"])
    assert DutySegment.objects.filter(log_day__trip=trip).exists()


def test_the_saved_trip_can_be_fetched_again(client):
    created = post(client).json()
    fetched = client.get(f"{ENDPOINT}{created['trip']['id']}/")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_a_rejected_request_saves_nothing(client, monkeypatch):
    monkeypatch.setattr(
        views, "plan_route", failing_planner(AddressNotFound("nowhere", "pickup location"))
    )
    assert post(client).status_code == 400
    assert Trip.objects.count() == 0


# --- validation 400s --------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["current_location", "pickup_location", "dropoff_location"]
)
@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_fields_are_rejected(client, field, blank):
    response = post(client, **{field: blank})
    assert response.status_code == 400
    assert response.json()["error"]


@pytest.mark.parametrize("cycle", [-1, -0.5, 70.1, 71, 500])
def test_cycle_hours_out_of_range_are_rejected(client, cycle):
    response = post(client, current_cycle_used=cycle)
    assert response.status_code == 400
    assert response.json()["error"]


@pytest.mark.parametrize("cycle", [0, 35, 70])
def test_cycle_hours_at_the_boundaries_are_accepted(client, cycle):
    assert post(client, current_cycle_used=cycle).status_code == 201


def test_same_pickup_and_dropoff_is_rejected(client):
    response = post(client, pickup_location="Columbus, OH", dropoff_location="Columbus, OH")
    assert response.status_code == 400
    assert "different" in response.json()["error"].lower()


def test_same_pickup_and_dropoff_ignores_case_and_padding(client):
    response = post(client, pickup_location="Columbus, OH", dropoff_location="  columbus, oh  ")
    assert response.status_code == 400


def test_missing_fields_are_rejected(client):
    response = client.post(ENDPOINT, {}, content_type="application/json")
    assert response.status_code == 400


def test_non_numeric_cycle_is_rejected(client):
    assert post(client, current_cycle_used="not a number").status_code == 400


# --- service failures become 400s, never 500s -------------------------------


@pytest.mark.parametrize(
    "exception, expected_text",
    [
        (AddressNotFound("asdfqwer", "pickup location"), "pickup location"),
        (GeocodingError("Could not reach the geocoding service. Please try again."),
         "Could not reach"),
        (RoutingError("No route could be found between those locations."), "No route"),
        (RoutingError("The OpenRouteService API key was rejected. Check ORS_API_KEY."),
         "key was rejected"),
    ],
)
def test_service_failures_return_400_with_the_safe_message(
    client, monkeypatch, exception, expected_text
):
    monkeypatch.setattr(views, "plan_route", failing_planner(exception))
    response = post(client)
    assert response.status_code == 400
    assert expected_text in response.json()["error"]


def test_service_failure_never_leaks_a_traceback(client, monkeypatch):
    monkeypatch.setattr(
        views, "plan_route", failing_planner(RoutingError("Could not reach the routing service."))
    )
    body = post(client).json()
    assert "Traceback" not in str(body)
    assert set(body) == {"error"}


def test_missing_ors_key_surfaces_as_a_400_not_a_crash(client, monkeypatch):
    """ORS being unconfigured is a user-visible message, not a server error."""
    monkeypatch.setattr(
        views,
        "plan_route",
        failing_planner(RoutingError("No OpenRouteService API key configured. Set the "
                                     "ORS_API_KEY environment variable.")),
    )
    response = post(client)
    assert response.status_code == 400
    assert "ORS_API_KEY" in response.json()["error"]


# --- CORS -------------------------------------------------------------------


def test_cors_allows_the_vite_dev_origin(client):
    response = client.post(
        ENDPOINT,
        VALID_REQUEST,
        content_type="application/json",
        HTTP_ORIGIN="http://localhost:5173",
    )
    assert response["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_cors_preflight_passes(client):
    response = client.options(
        ENDPOINT,
        HTTP_ORIGIN="http://localhost:5173",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
    )
    assert response.status_code == 200
    assert response["Access-Control-Allow-Origin"] == "http://localhost:5173"


def test_cors_rejects_an_unknown_origin(client):
    response = client.post(
        ENDPOINT,
        VALID_REQUEST,
        content_type="application/json",
        HTTP_ORIGIN="https://evil.example.com",
    )
    assert not response.has_header("Access-Control-Allow-Origin")


# --- method handling --------------------------------------------------------


def test_get_on_the_collection_is_not_allowed(client):
    assert client.get(ENDPOINT).status_code == 405


def test_unknown_trip_id_returns_404(client):
    assert client.get(f"{ENDPOINT}999999/").status_code == 404
