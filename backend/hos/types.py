"""Data shapes passed between the engine and the log-day builder.

Plain frozen dataclasses -- no Django, no serialization concerns. The API layer in
a later phase maps these onto DRF serializers.
"""

from dataclasses import dataclass, field
from datetime import date as Date, datetime
from typing import Literal

# The four rows of an ELD log grid, top to bottom.
Status = Literal["off_duty", "sleeper", "driving", "on_duty"]

# What a segment represents on the map. Driving segments carry no stop kind.
StopKind = Literal[
    "start", "pickup", "dropoff", "fuel", "break_30", "rest_10", "restart_34",
    "drive",  # a driving segment -- not a stop
    "off",    # plain off-duty time, e.g. after the trip ends
]


@dataclass(frozen=True)
class Leg:
    """One routed hop. `distance_miles` comes from the routing provider (Geoapify)."""

    distance_miles: float
    end_action: Literal["pickup", "dropoff"] | None = None
    start_label: str = ""
    end_label: str = ""


@dataclass(frozen=True)
class Segment:
    """One entry on the flat timeline -- the engine's single source of truth."""

    status: Status
    start: datetime
    end: datetime
    kind: StopKind
    remark: str = ""

    @property
    def minutes(self) -> int:
        return round((self.end - self.start).total_seconds() / 60)


@dataclass(frozen=True)
class DaySegment:
    """One drawn line on a single day's grid, in minutes from that day's midnight."""

    status: Status
    start_minute: int
    end_minute: int
    kind: StopKind
    remark: str = ""


@dataclass(frozen=True)
class LogDay:
    """One log sheet. `totals` maps each status to its minutes and must sum to 1440."""

    date: Date
    totals: dict[Status, int]
    total_miles: float
    segments: list[DaySegment] = field(default_factory=list)


@dataclass(frozen=True)
class TripPlan:
    """Everything the API needs from the engine."""

    timeline: list[Segment]
    log_days: list[LogDay]
    total_miles: float
    total_drive_minutes: int
    cycle_minutes_remaining: int
