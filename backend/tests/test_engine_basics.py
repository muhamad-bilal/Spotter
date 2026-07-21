"""Structural checks on the timeline and the day split, independent of HOS rules."""

import pytest
from fixtures import ALL_CASES, MULTI_DAY, SINGLE_DAY, START_AT
from replay import assert_contiguous, replay

from hos import Leg, build_log_days, plan_trip, simulate
from hos.constants import BREAK_STATUS, MINUTES_PER_DAY, REST_STATUS


@pytest.fixture(params=ALL_CASES, ids=lambda c: c.name)
def case(request):
    return request.param


def test_timeline_is_contiguous(case):
    assert_contiguous(simulate(case.legs, case.cycle_used_hours, START_AT))


def test_timeline_starts_at_midnight_and_ends_at_midnight(case):
    timeline = simulate(case.legs, case.cycle_used_hours, START_AT)
    first, last = timeline[0], timeline[-1]
    assert (first.start.hour, first.start.minute) == (0, 0)
    assert (last.end.hour, last.end.minute) == (0, 0)
    assert first.status == "off_duty", "the trip opens off-duty before going on duty"


def test_day_split_preserves_total_duration(case):
    timeline = simulate(case.legs, case.cycle_used_hours, START_AT)
    days = build_log_days(timeline)
    timeline_minutes = sum(s.minutes for s in timeline)
    assert timeline_minutes == len(days) * MINUTES_PER_DAY

    per_status = {"off_duty": 0, "sleeper": 0, "driving": 0, "on_duty": 0}
    for seg in timeline:
        per_status[seg.status] += seg.minutes
    summed = {"off_duty": 0, "sleeper": 0, "driving": 0, "on_duty": 0}
    for day in days:
        for status, minutes in day.totals.items():
            summed[status] += minutes
    assert summed == per_status, "splitting on midnight changed the status totals"


def test_single_day_trip_yields_one_sheet():
    days = build_log_days(simulate(SINGLE_DAY.legs, SINGLE_DAY.cycle_used_hours, START_AT))
    assert len(days) == 1


def test_multi_day_trip_yields_several_sheets():
    days = build_log_days(simulate(MULTI_DAY.legs, MULTI_DAY.cycle_used_hours, START_AT))
    assert len(days) > 1
    dates = [d.date for d in days]
    assert dates == sorted(dates), "log days must be in date order"
    for prev, nxt in zip(dates, dates[1:]):
        assert (nxt - prev).days == 1, "log days must be consecutive, no gaps"


def test_short_trip_inserts_no_rest_or_break():
    """380 mi fits inside one window -- do not invent a rest that isn't needed."""
    timeline = simulate(SINGLE_DAY.legs, SINGLE_DAY.cycle_used_hours, START_AT)
    kinds = {s.kind for s in timeline}
    assert "rest_10" not in kinds
    assert "break_30" not in kinds
    assert "fuel" not in kinds


def test_total_driving_matches_distance_at_assumed_speed(case):
    """Driving time must reflect distance / 55 mph, within whole-minute rounding.

    55 is written out rather than imported: it is the project's stated assumption,
    so changing it should break a test instead of quietly rewriting every log.
    """
    timeline = simulate(case.legs, case.cycle_used_hours, START_AT)
    driving = sum(s.minutes for s in timeline if s.status == "driving")
    expected = case.total_miles / 55.0 * 60
    assert abs(driving - expected) <= len(timeline), (
        f"drove {driving} min for {case.total_miles} mi, expected ~{expected:.1f}"
    )


def test_no_redundant_30_minute_breaks(case):
    """hos-rules.md: any >=30-min non-driving period -- including an on-duty fuel
    stop or pickup -- already satisfies the 30-minute break. So every break the
    engine does insert must be one the driver actually needed: 8h of driving must
    have accumulated since the last qualifying stop.

    Checking only the immediately preceding segment is not enough -- an engine that
    ignores the fuel stop inserts its redundant break several driving hours later.
    """
    timeline = simulate(case.legs, case.cycle_used_hours, START_AT)
    driving_since_qualifying = 0
    nondriving_run = 0

    for seg in timeline:
        if seg.status == "driving":
            driving_since_qualifying += seg.minutes
            nondriving_run = 0
            continue

        if seg.kind == "break_30":
            assert driving_since_qualifying >= 8 * 60, (
                f"redundant break at {seg.start}: only "
                f"{driving_since_qualifying} min of driving since the last "
                f">=30-min stop, so no break was required"
            )

        nondriving_run += seg.minutes
        if nondriving_run >= 30:
            driving_since_qualifying = 0


def test_rest_and_break_use_the_assumed_statuses(case):
    timeline = simulate(case.legs, case.cycle_used_hours, START_AT)
    for seg in timeline:
        if seg.kind in ("rest_10", "restart_34"):
            assert seg.status == REST_STATUS
        elif seg.kind == "break_30":
            assert seg.status == BREAK_STATUS


def test_14h_window_binds_before_the_11h_driving_cap():
    """With one pickup and one dropoff, non-driving time inside a window tops out at
    3h, so 11h of driving always binds first and the 14h window rule is never
    exercised. This synthetic multi-stop trip burns the window with on-duty work
    instead, forcing a rest while under the driving cap -- which is the only way to
    prove the window rule does any work.
    """
    legs = [
        Leg(100, "pickup" if i % 2 == 0 else "dropoff", f"Stop {i}", f"Stop {i + 1}")
        for i in range(6)
    ]
    timeline = simulate(legs, 0, START_AT)

    result = replay(timeline, 0)
    assert result.ok, result.violations

    # Find the first 10h rest and confirm the driving done before it is under 11h,
    # i.e. the window -- not the driving cap -- is what stopped the driver.
    driven = 0
    for seg in timeline:
        if seg.status == "driving":
            driven += seg.minutes
        elif seg.kind == "rest_10":
            assert driven < 11 * 60, (
                f"rest was forced by the 11h driving cap ({driven} min), not the window"
            )
            break
    else:
        raise AssertionError("expected a 10-hour rest to be inserted")


def test_plan_trip_reports_consistent_totals(case):
    plan = plan_trip(case.legs, case.cycle_used_hours, START_AT)
    assert plan.total_miles == pytest.approx(case.total_miles)
    assert plan.log_days == build_log_days(plan.timeline)
    assert plan.total_drive_minutes == sum(
        s.minutes for s in plan.timeline if s.status == "driving"
    )
    assert plan.cycle_minutes_remaining >= 0
