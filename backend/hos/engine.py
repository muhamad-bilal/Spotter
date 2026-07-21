"""The HOS simulation.

A clock-based walk over the route legs. Four counters are tracked; before every
driving chunk the engine asks what the binding constraint is and drives only that
far, then inserts whatever stop the rules demand. The output is a flat timeline of
segments -- the single source of truth everything downstream renders.

All time is handled in whole minutes. Float hours would accumulate drift and make
"each day's totals sum to exactly 24:00" flaky; minutes stay exact and are what the
log-sheet grid wants anyway.

Note on the 70-hour cycle: the reference pseudocode checks it only at leg ends,
which lets the cycle sail past 70 mid-leg and be noticed hours later. Here the
remaining cycle time is instead one of the terms that sizes every driving chunk, so
the limit binds the moment it is reached.
"""

from datetime import datetime, time, timedelta

from .constants import (
    BREAK_AFTER_DRIVING_MIN,
    BREAK_LENGTH_MIN,
    BREAK_STATUS,
    CYCLE_LIMIT_MIN,
    DAY_START_HOUR,
    DRIVING_WINDOW_MIN,
    DROPOFF_MIN,
    FUEL_EVERY_MILES,
    FUEL_STOP_MIN,
    MAX_DRIVE_PER_WINDOW_MIN,
    PICKUP_MIN,
    REQUIRED_RESET_OFF_MIN,
    REST_STATUS,
    RESTART_MIN,
    miles_to_minutes,
    minutes_to_miles,
)
from .types import Leg, Segment, StopKind

# Distances are floats; anything under this is "arrived".
EPSILON_MILES = 1e-6

ACTION_MINUTES = {"pickup": PICKUP_MIN, "dropoff": DROPOFF_MIN}


class _Sim:
    """Mutable simulation state. Kept private -- `simulate` is the public surface."""

    def __init__(self, start_at: datetime, cycle_used_minutes: int):
        self.clock = start_at
        self.segments: list[Segment] = []

        self.drive_in_window = 0      # minutes driven since the last 10h reset
        self.drive_since_break = 0    # minutes driven since the last >=30min break
        self.cycle_used = cycle_used_minutes
        self.window_start: datetime | None = None  # when the 14h window opened
        self.odometer = 0.0

    # --- emitting ---------------------------------------------------------

    def emit(self, status: str, minutes: int, kind: StopKind, remark: str = "") -> None:
        end = self.clock + timedelta(minutes=minutes)
        self.segments.append(Segment(status, self.clock, end, kind, remark))
        self.clock = end

    # --- derived counters -------------------------------------------------

    @property
    def window_elapsed(self) -> int:
        if self.window_start is None:
            return 0
        return round((self.clock - self.window_start).total_seconds() / 60)

    def open_window(self) -> None:
        """The 14h window opens on the first on-duty or driving time after a reset."""
        if self.window_start is None:
            self.window_start = self.clock

    # --- the three inserted stops ----------------------------------------

    def take_10h_reset(self) -> None:
        self.emit(REST_STATUS, REQUIRED_RESET_OFF_MIN, "rest_10", "10-hour rest")
        self.drive_in_window = 0
        self.drive_since_break = 0
        self.window_start = None

    def take_30m_break(self) -> None:
        self.emit(BREAK_STATUS, BREAK_LENGTH_MIN, "break_30", "30-minute break")
        self.drive_since_break = 0

    def take_34h_restart(self) -> None:
        self.emit(REST_STATUS, RESTART_MIN, "restart_34", "34-hour restart")
        self.cycle_used = 0
        self.drive_in_window = 0
        self.drive_since_break = 0
        self.window_start = None

    def reserve_cycle(self, minutes: int) -> None:
        """Restart the cycle if the coming on-duty work would push it past 70h."""
        if self.cycle_used + minutes > CYCLE_LIMIT_MIN:
            self.take_34h_restart()

    def on_duty_task(self, minutes: int, kind: StopKind, remark: str) -> None:
        """Pickup, dropoff or fueling: on duty, not driving."""
        self.reserve_cycle(minutes)
        self.open_window()
        self.emit("on_duty", minutes, kind, remark)
        self.cycle_used += minutes
        # >=30 consecutive non-driving minutes also satisfy the 30-minute break.
        if minutes >= BREAK_LENGTH_MIN:
            self.drive_since_break = 0


def simulate(
    legs: list[Leg],
    current_cycle_used_hours: float,
    start_at: datetime | None = None,
) -> list[Segment]:
    """Walk the legs and return the flat duty-status timeline.

    `start_at` is the moment the driver goes on duty. The timeline always begins at
    that day's midnight (off-duty) and ends at a midnight, so the day split below
    yields whole 24-hour sheets.
    """
    if start_at is None:
        start_at = datetime.combine(datetime.now().date(), time(DAY_START_HOUR))

    sim = _Sim(start_at, round(current_cycle_used_hours * 60))

    # Day 1 opens off-duty from midnight until the driver goes on duty.
    day_start = datetime.combine(start_at.date(), time.min)
    sim.clock = day_start
    opening = round((start_at - day_start).total_seconds() / 60)
    if opening > 0:
        sim.emit("off_duty", opening, "start", legs[0].start_label)

    for index, leg in enumerate(legs):
        miles_after_this_leg = sum(later.distance_miles for later in legs[index + 1:])
        miles_left = leg.distance_miles

        while miles_left > EPSILON_MILES:
            to_11 = MAX_DRIVE_PER_WINDOW_MIN - sim.drive_in_window
            to_14 = DRIVING_WINDOW_MIN - sim.window_elapsed
            to_break = BREAK_AFTER_DRIVING_MIN - sim.drive_since_break
            to_cycle = CYCLE_LIMIT_MIN - sim.cycle_used

            # 1. Out of cycle hours -- only a 34h restart unblocks the trip.
            if to_cycle <= 0:
                sim.take_34h_restart()
                continue

            # 2. Out of driving hours or out of window -- 10h reset.
            if to_11 <= 0 or to_14 <= 0:
                sim.take_10h_reset()
                continue

            # 3. Eight hours of driving since the last break.
            if to_break <= 0:
                sim.take_30m_break()
                continue

            # 4. Drive to whichever limit binds first.
            sim.open_window()
            miles_to_fuel = FUEL_EVERY_MILES - (sim.odometer % FUEL_EVERY_MILES)
            minutes_for_leg = miles_to_minutes(miles_left)
            minutes_to_fuel = miles_to_minutes(miles_to_fuel)

            chunk = min(to_11, to_14, to_break, to_cycle, minutes_for_leg, minutes_to_fuel)
            drive_minutes = max(1, round(chunk))

            # Consume the exact distance when the leg or the fuel boundary is what
            # binds, so the odometer lands precisely on leg ends and 1000-mi marks.
            if chunk == minutes_for_leg:
                miles_driven = miles_left
            elif chunk == minutes_to_fuel:
                miles_driven = miles_to_fuel
            else:
                miles_driven = min(minutes_to_miles(drive_minutes), miles_left)

            sim.emit("driving", drive_minutes, "drive")
            sim.drive_in_window += drive_minutes
            sim.drive_since_break += drive_minutes
            sim.cycle_used += drive_minutes
            sim.odometer += miles_driven
            miles_left -= miles_driven

            # 5. Landed on a 1000-mile mark? Fuel -- unless the trip ends here.
            trip_miles_left = miles_left + miles_after_this_leg
            if trip_miles_left > EPSILON_MILES and _on_fuel_mark(sim.odometer):
                sim.on_duty_task(
                    FUEL_STOP_MIN, "fuel", f"Fuel stop at {sim.odometer:.0f} mi"
                )

        # The leg ended at the pickup or the dropoff: one hour on duty.
        if leg.end_action:
            sim.on_duty_task(
                ACTION_MINUTES[leg.end_action],
                leg.end_action,
                f"{leg.end_label} - {leg.end_action}",
            )

    # Close the final day off-duty so every sheet is a whole 24 hours.
    end_of_day = datetime.combine(sim.clock.date() + timedelta(days=1), time.min)
    remaining = round((end_of_day - sim.clock).total_seconds() / 60)
    if remaining > 0:
        sim.emit("off_duty", remaining, "off", legs[-1].end_label)

    return sim.segments


def _on_fuel_mark(odometer: float) -> bool:
    if odometer <= 0:
        return False
    into_interval = odometer % FUEL_EVERY_MILES
    return into_interval < EPSILON_MILES or FUEL_EVERY_MILES - into_interval < EPSILON_MILES


def final_cycle_minutes(timeline: list[Segment], starting_cycle_used_hours: float) -> int:
    """On-duty minutes left on the clock at the end of the trip."""
    used = round(starting_cycle_used_hours * 60)
    for seg in timeline:
        if seg.status in ("driving", "on_duty"):
            used += seg.minutes
        elif seg.kind == "restart_34":
            used = 0
    return used
