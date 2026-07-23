# Engineering notes

Detail that doesn't belong in the README but is worth keeping — the design decisions and how the
tests were hardened.

## Provider abstraction

`plan_route(current, pickup, dropoff)` geocodes the three addresses, makes **one** routing call
through all three waypoints on a truck profile, and returns the engine's `list[Leg]` unchanged
alongside the geometry and the provider's own duration.

Two routing providers sit behind one interface — `route(waypoints) -> RouteResult`. **Geoapify
is the default**; OpenRouteService is used only when its key is present and Geoapify's is not.

| | Profile | Waypoints | Per-leg figures | Geometry |
|---|---|---|---|---|
| **Geoapify** (default) | `mode=truck`, falls back to `drive` | query string, `lat,lon` | `properties.legs[].time` | MultiLineString, one line per leg |
| **OpenRouteService** (alternative) | `driving-hgv` | POST body, `[lng, lat]` | `properties.segments[].duration` | single LineString |

Every one of those differences is absorbed in `services/routing.py`; nothing downstream knows
which provider answered. Both speak GeoJSON `[longitude, latitude]` and metres, and both return
`(latitude, longitude)` and miles. `tests/test_router_contract.py` runs the same cases against
both, so a third provider would inherit the whole suite by appending one line — that shared
contract is the point of keeping the second provider around.

The Geoapify truck profile is attempted first and falls back to `drive` **only** on a 400 (an
unsupported mode on the free plan); a rejected key or a rate limit surfaces as itself rather than
being retried into a confusing second failure. `router.mode_used` records which profile actually
produced the route, so a fallback is never silent. A distance-limit rejection (Geoapify caps the
synchronous API at ~6,200 mi) is translated into a human message in miles instead of the raw
"metres / asynchronous batch API" wording.

With no key at all, `default_router()` still returns a router, so the failure is the usual
actionable 400 rather than a crash.

## The two durations

They travel together and must never be confused, so each carries its own basis string:

```json
"total_drive_hours": 33.63,
"drive_hours_basis": "distance / 55 mph (assumed)",
"provider_eta_hours": 7.5,
"provider_eta_source": "Geoapify truck"
```

`total_drive_hours` is what every log sheet is built on. `provider_eta_hours` is display only —
**the provider's `duration` never reaches the HOS engine.** A test feeds the planner a route the
provider claims takes 40 hours and asserts the resulting log is byte-identical to one built from
the same distances with a sane duration.

`provider_eta_source` is reported by the router that actually answered, not assumed by the
caller — a summary naming the wrong provider is worse than no label. Geoapify folds its profile
into that name, so a `truck`→`drive` fallback reads as `"Geoapify drive"` on screen. The value is
stored on the trip, so refetching an old trip still names the provider that served it.

## Positioning stops on the map

Only the three geocoded addresses have real coordinates. Fuel stops, breaks and rests happen at
an odometer reading, not a place, so they are positioned by walking the route polyline and
interpolating to the fraction of the trip completed — using the engine's mileage as the basis,
never the polyline's own measured length, which runs a few percent short on simplified geometry.

## Day totals

The engine works in whole minutes summing to exactly 1440. Rounding four of those to two-decimal
hours independently can land on 23.99 or 24.01, so the residual is folded into the largest
bucket. `test_naive_rounding_really_would_drift` proves that correction is load-bearing rather
than decoration.

## Timezone

`USE_TZ = False`, deliberately. An ELD log sheet is defined in a single home-terminal local time
— the midnight its days are cut at is the terminal's, not UTC's. Leaving it on made Django
relabel the engine's naive local datetimes as UTC, which would shift the day boundaries the logs
are built on.

## Two deliberate deviations from the reference pseudocode

**The 70-hour cycle is checked continuously, not at leg ends.** The reference pseudocode tests
the cycle only after a pickup or dropoff, which lets it sail past 70 hours mid-leg and be noticed
hours later — that cannot uphold the invariant it exists for. Here the remaining cycle time is
one of the terms sizing every driving chunk, so the limit binds the moment it is reached.

**Fuel-stop count at exact 1000-mile multiples.** Because a stop with zero miles remaining is
skipped, a trip of exactly 2000 miles yields 1 fuel stop, not `floor(2000/1000) == 2` — no fuel
stop at the destination door. Pinned by `test_exact_multiple_skips_the_terminal_fuel_stop`.

## How the tests were hardened

**They don't read the engine's counters.** `tests/replay.py` walks the emitted timeline and
reconstructs `drive_in_window`, `window_elapsed`, `drive_since_break` and `cycle_used` from
scratch. The regulation numbers are hardcoded there and in the tests rather than imported from
`hos.constants` — otherwise widening the driving cap to 12 h would move the engine and its own
test together and the test would still pass.

**The engine suite was mutation-tested.** Fourteen deliberate bugs were injected (widen the
driving cap, drop the break term, remove the cycle guards, shorten the reset, ignore the 14-hour
window, log rests as driving, change the fuel interval, change the assumed speed, …). Every one
is caught. Three gaps the first draft missed were found this way and fixed:

- no fixture was long enough to tell a 1000-mile fuel interval from a 1500-mile one → a
  2600-mile case was added;
- with one pickup and one dropoff, non-driving time in a window tops out at exactly 3 h, so
  11 h of driving always binds before the 14-hour window and that rule was never exercised → a
  synthetic multi-stop trip now forces it;
- an engine that ignored a fuel stop's contribution to the 30-minute break inserted a redundant
  break several driving hours later, which an adjacency check could not see.

**The service and PDF layers were mutation-tested the same way.** For the services: legs derived
from the provider's duration, forgetting the lng/lat flip, the car profile instead of the truck
one, metres read as kilometres, a cache that never hits, a throttle that never waits, a dropped
User-Agent, an unresolvable address silently returning `0,0`. For the PDF: the reportlab y-flip
omitted (which turns the log upside down), the trace unsnapped from the quarter-hour grid, totals
recomputed and drifting. The PDF tests assert on the **actual drawn coordinates** read back with
pdfminer, not on a helper's return value — an earlier version checked the latter and passed while
the rendering was visibly wrong.

**No default-suite test touches the network:** the whole run passes with `socket.connect` patched
to raise.
