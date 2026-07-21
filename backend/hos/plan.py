"""One call from trip inputs to everything the API needs."""

from datetime import datetime

from .constants import CYCLE_LIMIT_MIN
from .engine import final_cycle_minutes, simulate
from .logdays import build_log_days
from .types import Leg, TripPlan


def plan_trip(
    legs: list[Leg],
    current_cycle_used_hours: float,
    start_at: datetime | None = None,
) -> TripPlan:
    timeline = simulate(legs, current_cycle_used_hours, start_at)
    return TripPlan(
        timeline=timeline,
        log_days=build_log_days(timeline),
        total_miles=sum(leg.distance_miles for leg in legs),
        total_drive_minutes=sum(s.minutes for s in timeline if s.status == "driving"),
        cycle_minutes_remaining=max(
            0, CYCLE_LIMIT_MIN - final_cycle_minutes(timeline, current_cycle_used_hours)
        ),
    )
