"""The seven graded HOS invariants.

Each test drives the engine through the hardcoded fixtures and checks the emitted
timeline against `replay.py`, which re-derives the HOS counters independently.
"""

import math

import pytest
from fixtures import (
    ALL_CASES,
    CYCLE_LIMITED,
    EXACT_MULTIPLE,
    FUEL_COUNT_CASES,
    START_AT,
)
from replay import replay

from hos import build_log_days, simulate

# These are deliberately hardcoded rather than imported from hos.constants.
# The regulation numbers are facts, not project configuration -- if a test read
# them from the same module the engine reads, widening the driving cap to 12h
# would move the engine and its own test together and the test would still pass.
DRIVE_CAP_MIN = 11 * 60
WINDOW_MIN = 14 * 60
BREAK_TRIGGER_MIN = 8 * 60
CYCLE_CAP_MIN = 70 * 60
RESTART_MIN = 34 * 60
ACTION_MIN = 60
FUEL_INTERVAL_MILES = 1000
MINUTES_PER_DAY = 24 * 60
# The project's stated assumption, pinned here so changing it fails a test rather
# than silently rewriting every log.
AVG_SPEED_MPH = 55.0

STATUSES = ("off_duty", "sleeper", "driving", "on_duty")


def run(case):
    return simulate(case.legs, case.cycle_used_hours, START_AT)


@pytest.fixture(params=ALL_CASES, ids=lambda c: c.name)
def case(request):
    return request.param


# --- 1. Every day's four totals sum to exactly 24:00 ------------------------


def test_day_totals_sum_to_1440(case):
    days = build_log_days(run(case))
    assert days, "expected at least one log day"

    for day in days:
        assert set(day.totals) == set(STATUSES), f"{day.date}: wrong status keys"
        assert all(isinstance(v, int) for v in day.totals.values()), (
            f"{day.date}: totals must be whole minutes, got {day.totals}"
        )
        assert sum(day.totals.values()) == MINUTES_PER_DAY, (
            f"{day.date}: totals sum to {sum(day.totals.values())}, not 1440"
        )


def test_day_segments_tile_the_whole_day(case):
    """The four totals can only be trusted if the segments actually cover 00:00-24:00."""
    for day in build_log_days(run(case)):
        assert day.segments, f"{day.date}: no segments"
        assert day.segments[0].start_minute == 0, f"{day.date}: does not start at midnight"
        assert day.segments[-1].end_minute == MINUTES_PER_DAY, (
            f"{day.date}: does not run to midnight"
        )
        for prev, nxt in zip(day.segments, day.segments[1:]):
            assert prev.end_minute == nxt.start_minute, (
                f"{day.date}: gap or overlap at minute {prev.end_minute}"
            )
        for seg in day.segments:
            assert seg.end_minute > seg.start_minute, f"{day.date}: empty segment {seg}"

        # Totals must agree with the segments they were summed from.
        recomputed = {s: 0 for s in STATUSES}
        for seg in day.segments:
            recomputed[seg.status] += seg.end_minute - seg.start_minute
        assert recomputed == day.totals, f"{day.date}: totals disagree with segments"


# --- 2. No driving segment starts after 14h of window elapsed ---------------


def test_no_driving_starts_after_14h_window(case):
    result = replay(run(case), case.cycle_used_hours)
    assert result.max_window_elapsed_at_drive_start <= WINDOW_MIN, result.violations
    assert not [v for v in result.violations if "window elapsed" in v], result.violations


# --- 3. Driving never exceeds 11h between 10h resets ------------------------


def test_driving_never_exceeds_11h_per_window(case):
    result = replay(run(case), case.cycle_used_hours)
    assert result.max_drive_in_window <= DRIVE_CAP_MIN, result.violations
    assert not [v for v in result.violations if "drive_in_window" in v], result.violations


# --- 4. A >=30-min non-driving break before cumulative driving passes 8h ----


def test_break_before_8h_cumulative_driving(case):
    result = replay(run(case), case.cycle_used_hours)
    assert result.max_drive_since_break <= BREAK_TRIGGER_MIN, result.violations
    assert not [v for v in result.violations if "without a" in v], result.violations


# --- 5. Cycle on-duty never exceeds 70h without a 34h restart between -------


def test_cycle_never_exceeds_70h(case):
    result = replay(run(case), case.cycle_used_hours)
    assert result.max_cycle_used <= CYCLE_CAP_MIN, result.violations
    assert not [v for v in result.violations if "cycle_used" in v], result.violations


def test_high_starting_cycle_forces_a_34h_restart():
    """66h already used cannot cover a 1600-mi trip, so a restart must appear."""
    timeline = run(CYCLE_LIMITED)
    restarts = [s for s in timeline if s.kind == "restart_34"]
    assert restarts, "expected a 34h restart when the cycle is the binding constraint"
    for seg in restarts:
        assert seg.minutes >= RESTART_MIN, f"restart only {seg.minutes} min"
        assert seg.status in ("off_duty", "sleeper")


# --- 6. Fuel-stop count == floor(total_miles / 1000) -----------------------


@pytest.mark.parametrize("case", FUEL_COUNT_CASES, ids=lambda c: c.name)
def test_fuel_stop_count(case):
    fuel = [s for s in run(case) if s.kind == "fuel"]
    assert len(fuel) == math.floor(case.total_miles / FUEL_INTERVAL_MILES)
    for seg in fuel:
        assert seg.status == "on_duty", "fueling is on-duty, not driving"


@pytest.mark.parametrize("case", FUEL_COUNT_CASES, ids=lambda c: c.name)
def test_fuel_stops_land_on_1000_mile_marks(case):
    """Counting stops is not enough -- they must fall at the right odometer marks.
    Miles are re-derived from driving minutes at the stated 55 mph, independently
    of the engine's own odometer.
    """
    odometer = 0.0
    for seg in run(case):
        if seg.status == "driving":
            odometer += seg.minutes / 60 * AVG_SPEED_MPH
        elif seg.kind == "fuel":
            nearest = round(odometer / FUEL_INTERVAL_MILES) * FUEL_INTERVAL_MILES
            assert nearest > 0, f"fuel stop at {odometer:.0f} mi is not on a 1000-mi mark"
            assert abs(odometer - nearest) <= 1.0, (
                f"fuel stop at {odometer:.0f} mi, expected near {nearest} mi"
            )


def test_exact_multiple_skips_the_terminal_fuel_stop():
    """Documented deviation: at exactly 2000 mi the second stop would land at the
    dropoff door with zero miles left, so it is skipped and the count is 1, not 2."""
    fuel = [s for s in run(EXACT_MULTIPLE) if s.kind == "fuel"]
    assert EXACT_MULTIPLE.total_miles % FUEL_INTERVAL_MILES == 0
    assert len(fuel) == 1


# --- 7. Pickup and dropoff each add exactly 1h on-duty ---------------------


def test_pickup_and_dropoff_are_one_hour_on_duty(case):
    timeline = run(case)
    for kind in ("pickup", "dropoff"):
        matching = [s for s in timeline if s.kind == kind]
        assert len(matching) == 1, f"expected exactly one {kind}, got {len(matching)}"
        assert matching[0].status == "on_duty", f"{kind} must be on-duty, not driving"
        assert matching[0].minutes == ACTION_MIN, f"{kind} was {matching[0].minutes} min"
