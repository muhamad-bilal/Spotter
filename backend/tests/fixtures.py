"""Hardcoded trip fixtures. No routing -- leg distances are fixed so the expected
HOS behaviour is hand-checkable.
"""

from dataclasses import dataclass
from datetime import datetime

from hos.constants import DAY_START_HOUR
from hos.types import Leg

# Fixed start so no test ever depends on the wall clock.
START_AT = datetime(2025, 1, 15, DAY_START_HOUR, 0)


@dataclass(frozen=True)
class TripCase:
    name: str
    legs: list[Leg]
    cycle_used_hours: float

    @property
    def total_miles(self) -> float:
        return sum(leg.distance_miles for leg in self.legs)


def _legs(to_pickup: float, to_dropoff: float) -> list[Leg]:
    return [
        Leg(to_pickup, "pickup", "Chicago, IL", "Indianapolis, IN"),
        Leg(to_dropoff, "dropoff", "Indianapolis, IN", "Columbus, OH"),
    ]


# 380 mi ~ 6.9h driving + 2h of actions. Fits one window and one log day:
# no rest, no 30-min break (driving stays under 8h), no fuel stop.
SINGLE_DAY = TripCase("single_day", _legs(120, 260), cycle_used_hours=10)

# 1850 mi ~ 33.6h driving. Forces several 10h resets and 30-min breaks, exactly
# one fuel stop, and spans multiple log days with rests split across midnight.
MULTI_DAY = TripCase("multi_day", _legs(300, 1550), cycle_used_hours=8)

# Only 4h of the 70h cycle left at the start -> forces a 34h restart mid-trip.
CYCLE_LIMITED = TripCase("cycle_limited", _legs(200, 1400), cycle_used_hours=66)

# Total is exactly 2000 mi, pinning the fuel edge case: the stop that would land
# at the dropoff door with zero miles remaining is skipped by design.
EXACT_MULTIPLE = TripCase("exact_multiple", _legs(500, 1500), cycle_used_hours=5)

# 2600 mi needs two fuel stops. Without a case this long the suite cannot tell a
# 1000-mile fuel interval from a 1500-mile one: every shorter fixture happens to
# yield the same count either way.
FUEL_HEAVY = TripCase("fuel_heavy", _legs(600, 2000), cycle_used_hours=0)

ALL_CASES = [SINGLE_DAY, MULTI_DAY, CYCLE_LIMITED, EXACT_MULTIPLE, FUEL_HEAVY]

# EXACT_MULTIPLE is excluded: it is the one case where the documented
# skip-the-terminal-stop rule makes count != floor(miles / 1000).
FUEL_COUNT_CASES = [SINGLE_DAY, MULTI_DAY, CYCLE_LIMITED, FUEL_HEAVY]
