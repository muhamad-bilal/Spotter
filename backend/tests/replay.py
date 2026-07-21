"""Independent HOS verifier.

This deliberately does NOT import or inspect the engine's counters. It walks the
emitted timeline and reconstructs `drive_in_window`, `window_elapsed`,
`drive_since_break` and `cycle_used` from the segments alone, applying the FMCSA
rules from scratch. If the engine's internal bookkeeping is wrong, this disagrees
with it -- which is the whole point. An engine that checked its own counters would
be grading its own homework.
"""

from dataclasses import dataclass, field

from hos.types import Segment

# Hardcoded on purpose -- see the note in test_invariants.py. This verifier must
# not share a source of truth with the engine it is checking.
MAX_DRIVE_PER_WINDOW_MIN = 11 * 60
DRIVING_WINDOW_MIN = 14 * 60
BREAK_AFTER_DRIVING_MIN = 8 * 60
BREAK_LENGTH_MIN = 30
REQUIRED_RESET_OFF_MIN = 10 * 60
CYCLE_LIMIT_MIN = 70 * 60
RESTART_MIN = 34 * 60

OFF_STATUSES = ("off_duty", "sleeper")


@dataclass
class ReplayResult:
    violations: list[str] = field(default_factory=list)
    max_drive_in_window: int = 0
    max_window_elapsed_at_drive_start: int = 0
    max_drive_since_break: int = 0
    max_cycle_used: int = 0
    restarts: int = 0
    resets: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations


def replay(timeline: list[Segment], starting_cycle_used_hours: float) -> ReplayResult:
    """Re-derive every HOS counter from the timeline and report any rule breach."""
    result = ReplayResult()

    drive_in_window = 0
    drive_since_break = 0
    cycle_used = round(starting_cycle_used_hours * 60)
    result.max_cycle_used = cycle_used

    window_start = None  # datetime the current 14h window opened, or None
    off_run = 0          # consecutive off_duty/sleeper minutes
    nondriving_run = 0   # consecutive non-driving minutes (on_duty counts)

    for seg in timeline:
        minutes = seg.minutes

        if seg.status == "driving":
            # The window opens at the first on-duty/driving after a reset.
            if window_start is None:
                window_start = seg.start
            elapsed_at_start = round((seg.start - window_start).total_seconds() / 60)

            if elapsed_at_start > DRIVING_WINDOW_MIN:
                result.violations.append(
                    f"driving started at {seg.start} with {elapsed_at_start} min of "
                    f"window elapsed (limit {DRIVING_WINDOW_MIN})"
                )
            result.max_window_elapsed_at_drive_start = max(
                result.max_window_elapsed_at_drive_start, elapsed_at_start
            )

            drive_in_window += minutes
            drive_since_break += minutes
            cycle_used += minutes
            off_run = 0
            nondriving_run = 0

            if drive_in_window > MAX_DRIVE_PER_WINDOW_MIN:
                result.violations.append(
                    f"drive_in_window reached {drive_in_window} min by {seg.end} "
                    f"(limit {MAX_DRIVE_PER_WINDOW_MIN})"
                )
            if drive_since_break > BREAK_AFTER_DRIVING_MIN:
                result.violations.append(
                    f"drove {drive_since_break} min without a {BREAK_LENGTH_MIN}-min "
                    f"break by {seg.end} (limit {BREAK_AFTER_DRIVING_MIN})"
                )
            if cycle_used > CYCLE_LIMIT_MIN:
                result.violations.append(
                    f"cycle_used reached {cycle_used} min by {seg.end} "
                    f"(limit {CYCLE_LIMIT_MIN})"
                )

            result.max_drive_in_window = max(result.max_drive_in_window, drive_in_window)
            result.max_drive_since_break = max(result.max_drive_since_break, drive_since_break)
            result.max_cycle_used = max(result.max_cycle_used, cycle_used)
            continue

        # --- non-driving ---
        if seg.status == "on_duty":
            if window_start is None:
                window_start = seg.start
            cycle_used += minutes
            off_run = 0
            if cycle_used > CYCLE_LIMIT_MIN:
                result.violations.append(
                    f"cycle_used reached {cycle_used} min by {seg.end} "
                    f"(limit {CYCLE_LIMIT_MIN})"
                )
            result.max_cycle_used = max(result.max_cycle_used, cycle_used)
        else:
            off_run += minutes

        # Any >=30 min of consecutive non-driving time satisfies the break rule,
        # including an on-duty fuel stop or pickup.
        nondriving_run += minutes
        if nondriving_run >= BREAK_LENGTH_MIN:
            drive_since_break = 0

        # >=10h off/sleeper resets the driving limit and the window.
        if off_run >= REQUIRED_RESET_OFF_MIN:
            if drive_in_window > 0 or window_start is not None:
                result.resets += 1
            drive_in_window = 0
            drive_since_break = 0
            window_start = None

        # >=34h off/sleeper additionally resets the 70h cycle.
        if off_run >= RESTART_MIN:
            result.restarts += 1
            cycle_used = 0

    return result


def assert_contiguous(timeline: list[Segment]) -> None:
    """Every segment must start exactly where the previous one ended."""
    for prev, nxt in zip(timeline, timeline[1:]):
        assert prev.end == nxt.start, f"gap/overlap between {prev} and {nxt}"
