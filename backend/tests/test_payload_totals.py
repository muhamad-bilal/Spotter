"""Converting a day's four totals from exact minutes to displayed hours.

The engine guarantees the four sum to 1440 minutes. Rounding each independently to
two decimal places does NOT guarantee they still sum to 24.00 hours, and that sum
is the first thing anyone checks on a log sheet.
"""

import pytest

from api.payload import _totals_in_hours

STATUSES = ("off_duty", "sleeper", "driving", "on_duty")


def minutes(off_duty, sleeper, driving, on_duty):
    return dict(zip(STATUSES, (off_duty, sleeper, driving, on_duty)))


@pytest.mark.parametrize(
    "day_minutes",
    [
        minutes(360, 360, 660, 60),        # a clean day
        minutes(1, 1, 1, 1437),            # naive rounding gives 24.01
        minutes(7, 13, 697, 723),          # thirds of a minute everywhere
        minutes(1, 0, 719, 720),
        minutes(0, 0, 0, 1440),            # everything in one bucket
        minutes(359, 361, 359, 361),
        minutes(1439, 1, 0, 0),
        minutes(5, 5, 5, 1425),
    ],
)
def test_totals_always_sum_to_exactly_24(day_minutes):
    assert sum(day_minutes.values()) == 1440, "fixture must be a whole day"
    hours = _totals_in_hours(day_minutes)
    assert round(sum(hours.values()), 2) == 24.00, (
        f"{day_minutes} -> {hours}, summing to {sum(hours.values())}"
    )


def test_naive_rounding_really_would_drift():
    """Proves the correction is load-bearing, not decoration.

    Without it, this input rounds to 0.02 + 0.02 + 0.02 + 23.95 = 24.01.
    """
    day_minutes = minutes(1, 1, 1, 1437)
    naive = sum(round(m / 60, 2) for m in day_minutes.values())
    assert round(naive, 2) == 24.01, "expected this fixture to drift when rounded naively"
    assert round(sum(_totals_in_hours(day_minutes).values()), 2) == 24.00


def test_the_correction_lands_on_the_largest_bucket():
    """A hundredth of an hour must be absorbed where it cannot be noticed."""
    hours = _totals_in_hours(minutes(1, 1, 1, 1437))
    assert hours["on_duty"] == 23.94, hours
    assert hours["off_duty"] == hours["sleeper"] == hours["driving"] == 0.02


def test_totals_stay_close_to_the_true_value():
    """The correction may shift a bucket by a hundredth, never more."""
    for day_minutes in (minutes(1, 1, 1, 1437), minutes(7, 13, 697, 723)):
        hours = _totals_in_hours(day_minutes)
        for status, mins in day_minutes.items():
            assert abs(hours[status] - mins / 60) <= 0.02, (
                f"{status}: {hours[status]} vs true {mins / 60:.4f}"
            )


def test_keys_are_preserved():
    assert set(_totals_in_hours(minutes(360, 360, 660, 60))) == set(STATUSES)
