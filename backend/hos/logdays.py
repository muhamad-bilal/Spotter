"""Cut the flat timeline into one log sheet per calendar day.

Any segment crossing midnight (home-terminal time) is split at the boundary, then
segments are grouped by date. Because the engine's timeline always spans whole
days, each resulting sheet covers 00:00-24:00 and its four totals sum to 1440.
"""

from dataclasses import replace
from datetime import datetime, time, timedelta
from itertools import groupby

from .constants import minutes_to_miles
from .types import DaySegment, LogDay, Segment, Status

STATUSES: tuple[Status, ...] = ("off_duty", "sleeper", "driving", "on_duty")


def build_log_days(timeline: list[Segment]) -> list[LogDay]:
    days = []
    split = _split_on_midnight(timeline)

    for date, group in groupby(split, key=lambda s: s.start.date()):
        segments = list(group)
        midnight = datetime.combine(date, time.min)

        day_segments = [
            DaySegment(
                status=seg.status,
                start_minute=round((seg.start - midnight).total_seconds() / 60),
                end_minute=round((seg.end - midnight).total_seconds() / 60),
                kind=seg.kind,
                remark=seg.remark,
            )
            for seg in segments
        ]

        totals = {status: 0 for status in STATUSES}
        for seg in day_segments:
            totals[seg.status] += seg.end_minute - seg.start_minute

        days.append(
            LogDay(
                date=date,
                totals=totals,
                total_miles=round(minutes_to_miles(totals["driving"]), 1),
                segments=day_segments,
            )
        )

    return days


def _split_on_midnight(timeline: list[Segment]) -> list[Segment]:
    """Cut any segment that crosses midnight into one piece per calendar day."""
    out: list[Segment] = []
    for seg in timeline:
        start = seg.start
        while True:
            boundary = datetime.combine(start.date() + timedelta(days=1), time.min)
            if seg.end > boundary:
                out.append(replace(seg, start=start, end=boundary))
                start = boundary
            else:
                out.append(replace(seg, start=start, end=seg.end))
                break
    return out
