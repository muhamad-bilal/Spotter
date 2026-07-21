"""Positioning route stops on the polyline.

This is the only genuinely new logic in phase 3 -- the engine and services are
already proven -- and a subtle error here puts a fuel pin in the wrong place,
which reads as broken to anyone looking at the map.

The fixtures run along a meridian (constant longitude) on purpose: moving one
degree of latitude is a known, constant distance, so expected coordinates can be
derived analytically instead of copied from the implementation's own output.
"""



import pytest

from api.stop_locator import PolylineLocator, haversine_miles

# One degree of latitude is ~69.09 statute miles. Written out rather than derived
# from the module's own EARTH_RADIUS_MILES: deriving it would mean a wrong radius
# (kilometres, say) moved the code and its test together and nothing would fail.
MILES_PER_DEGREE_LAT = 69.0932

# 11 vertices from 30N to 40N at -90E: 10 degrees, ~690.9 miles.
MERIDIAN = [(30.0 + step, -90.0) for step in range(11)]
MERIDIAN_MILES = 10 * MILES_PER_DEGREE_LAT


def assert_close(actual, expected, tolerance_miles=0.5):
    """Compare two coordinates by the real distance between them."""
    off_by = haversine_miles(actual, expected)
    assert off_by <= tolerance_miles, (
        f"located at {actual}, expected {expected} -- {off_by:.2f} mi away"
    )


# --- the distance measure itself -------------------------------------------


def test_haversine_matches_a_known_degree_of_latitude():
    """Pins the unit: one degree of latitude is ~69.09 MILES, not ~111 (km)."""
    assert haversine_miles((30.0, -90.0), (31.0, -90.0)) == pytest.approx(
        MILES_PER_DEGREE_LAT, rel=1e-4
    )


def test_haversine_matches_a_known_city_pair():
    """Chicago to Indianapolis is about 165 miles as the crow flies."""
    measured = haversine_miles((41.8755616, -87.6244212), (39.7683331, -86.1583502))
    assert measured == pytest.approx(165, abs=5), f"got {measured:.1f} mi"


def test_haversine_is_zero_for_the_same_point():
    assert haversine_miles((41.87, -87.62), (41.87, -87.62)) == 0.0


# --- accumulated length -----------------------------------------------------


def test_polyline_length_is_the_sum_of_its_segments():
    # rel=1e-4 because MILES_PER_DEGREE_LAT above is a rounded, human-checkable
    # literal. Still tight enough to catch a unit error -- kilometres would be 60% out.
    assert PolylineLocator(MERIDIAN).length_miles == pytest.approx(MERIDIAN_MILES, rel=1e-4)


# --- coordinate accuracy ----------------------------------------------------


@pytest.mark.parametrize(
    "fraction, expected_lat",
    [
        (0.0, 30.0),
        (0.25, 32.5),
        (0.5, 35.0),
        (0.75, 37.5),
        (1.0, 40.0),
        (0.1234, 31.234),  # deliberately not a vertex
    ],
)
def test_positions_land_where_the_geometry_says(fraction, expected_lat):
    located = PolylineLocator(MERIDIAN).at_fraction(fraction)
    assert_close(located, (expected_lat, -90.0))


def test_interior_stop_at_a_non_round_fraction():
    """A fuel stop at 1000 mi of an 1850-mi trip -- the real-world case.

    54.05% of the way along, which falls between vertices and is not a round
    number, so an off-by-one in the vertex walk would show up here.
    """
    located = PolylineLocator(MERIDIAN).at_odometer(1000, 1850)
    expected_lat = 30.0 + 10.0 * (1000 / 1850)
    assert_close(located, (expected_lat, -90.0))
    assert 35.4 < located[0] < 35.5, "sanity: should be just past the midpoint"


def test_second_fuel_stop_of_a_long_trip():
    located = PolylineLocator(MERIDIAN).at_odometer(2000, 2600)
    assert_close(located, (30.0 + 10.0 * (2000 / 2600), -90.0))


def test_stops_advance_monotonically_along_the_route():
    locator = PolylineLocator(MERIDIAN)
    latitudes = [locator.at_odometer(mile, 1850)[0] for mile in (0, 250, 1000, 1400, 1850)]
    assert latitudes == sorted(latitudes), "a later stop must never be positioned earlier"


# --- distance basis ---------------------------------------------------------


def test_polyline_length_reconciles_with_the_route_distance():
    """The geometry the provider returns should describe the distance it reported.

    If these diverge badly, either the geometry is not the route or the unit
    conversion is wrong -- both of which would misplace every interpolated stop.
    """
    locator = PolylineLocator(MERIDIAN)
    engine_total_miles = MERIDIAN_MILES
    drift = abs(locator.length_miles - engine_total_miles) / engine_total_miles
    assert drift < 0.02, f"polyline length drifts {drift:.1%} from the route distance"


def test_positions_use_the_engines_total_not_the_polylines_own_length():
    """The odometer basis must be the engine's mileage, not a recomputed one.

    Real provider geometry is simplified and measures a few percent short of the
    reported road distance. If the locator divided by its own accumulated length,
    every pin would creep forward. Here the polyline is deliberately half the
    length of the route it represents: a stop at 50% of the ROUTE must still land
    at 50% of the POLYLINE.
    """
    half_length_geometry = [(30.0 + step * 0.5, -90.0) for step in range(11)]
    locator = PolylineLocator(half_length_geometry)
    assert locator.length_miles == pytest.approx(MERIDIAN_MILES / 2, rel=1e-4)

    located = locator.at_odometer(925, 1850)  # half way through the route
    assert_close(located, (32.5, -90.0))  # half way along this polyline


# --- degenerate geometry ----------------------------------------------------


def test_single_point_geometry_does_not_crash():
    locator = PolylineLocator([(41.87, -87.62)])
    assert locator.length_miles == 0.0
    assert locator.at_odometer(500, 1850) == (41.87, -87.62)


def test_empty_geometry_returns_no_position():
    locator = PolylineLocator([])
    assert locator.length_miles == 0.0
    assert locator.at_odometer(500, 1850) is None


def test_zero_total_miles_does_not_divide_by_zero():
    assert_close(PolylineLocator(MERIDIAN).at_odometer(0, 0), (30.0, -90.0))


def test_repeated_points_do_not_divide_by_zero():
    locator = PolylineLocator([(30.0, -90.0), (30.0, -90.0), (31.0, -90.0)])
    assert_close(locator.at_odometer(MILES_PER_DEGREE_LAT / 2, MILES_PER_DEGREE_LAT),
                 (30.5, -90.0))


def test_odometer_beyond_the_route_clamps_to_the_end():
    assert_close(PolylineLocator(MERIDIAN).at_odometer(9999, 1850), (40.0, -90.0))


def test_negative_odometer_clamps_to_the_start():
    assert_close(PolylineLocator(MERIDIAN).at_odometer(-50, 1850), (30.0, -90.0))
