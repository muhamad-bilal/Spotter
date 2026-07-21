# ELD Trip Planner

Full-stack Hours-of-Service trip planner: a driver enters current location, pickup, dropoff and
hours already used in their 70-hour/8-day cycle, and gets back a routed trip with compliant
rest/break/fuel stops plus drawn ELD daily log sheets.

**Status: Phase 3 complete.** The HOS engine, the geocoding/routing services and the
`POST /api/trips/` endpoint are built and tested. The React app is still a Vite skeleton — no
map, log-sheet SVG or UI yet.

## Layout

```
backend/
  hos/          the HOS simulation engine — pure Python, imports nothing from Django
  services/     Nominatim + OpenRouteService wrappers — also Django-free
  api/          DRF endpoint, models, serializers, payload assembly
  tests/        engine invariants, service tests, API tests, optional live smoke test
  config/       Django project settings and URLs
frontend/       Vite + React skeleton
```

`hos/` and `services/` deliberately have no Django dependency, so they are testable without a
settings module and reusable from anywhere. A check hard-blocks the `django` import and both
still run.

## Configuration

| Variable | Needed for | Notes |
|---|---|---|
| `GEOAPIFY_API_KEY` | routing | Free key from [geoapify.com](https://www.geoapify.com/). Selected in preference to ORS when both are set. |
| `ORS_API_KEY` | routing | Free key from [openrouteservice.org](https://openrouteservice.org/dev/#/signup). Used when no Geoapify key is present. |
| `NOMINATIM_USER_AGENT` | geocoding | Nominatim's usage policy requires a descriptive agent; requests without one are blocked. Falls back to a sane default. |

Copy `backend/.env.example` to `backend/.env` for local use (gitignored); set real environment
variables on Render/Railway in production. `services/env.py` reads the file without adding a
dependency, and a real environment variable always beats a stale local one, so a deployment
value is never overwritten.

Whichever key is present decides the provider — deployment is an environment change, not a code
change. With neither, `default_router()` still returns a router, so the failure is the usual
actionable 400 rather than a crash.

## Running it

```bash
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt   # Linux/macOS: .venv/bin/pip

cd backend && pytest              # 117 tests; live tests excluded by default
cd backend && python manage.py check
cd frontend && npm install && npm run dev

# optional, hits the real APIs:
cd backend && ORS_API_KEY=your-key pytest -m live -v
```

## Services

`plan_route(current, pickup, dropoff)` geocodes the three addresses, makes **one** routing call
through all three waypoints on a truck profile, and returns the engine's `list[Leg]` unchanged
alongside the geometry and the provider's own duration.

Two routing providers are supported behind one interface — `route(waypoints) -> RouteResult`:

| | Profile | Waypoints | Per-leg figures | Geometry |
|---|---|---|---|---|
| **Geoapify** | `mode=truck`, falls back to `drive` | query string, `lat,lon` | `properties.legs[].time` | MultiLineString, one line per leg |
| **OpenRouteService** | `driving-hgv` | POST body, `[lng, lat]` | `properties.segments[].duration` | single LineString |

Every one of those differences is absorbed in `services/routing.py`; nothing downstream knows
which provider answered. Both speak GeoJSON `[longitude, latitude]` and metres, and both return
`(latitude, longitude)` and miles. `tests/test_router_contract.py` runs the same cases against
both, so a third provider inherits the whole suite by appending one line.

The Geoapify truck profile is attempted first and falls back to `drive` **only** on a 400, which
is what an unsupported mode looks like on a free plan — a rejected key or a rate limit surfaces
as itself rather than being retried into a confusing second failure. `router.mode_used` records
which profile actually produced the route, so a fallback is never silent. Either way the HOS
logs are unaffected: drive time is always distance ÷ 55 mph.

**ORS's `duration` is captured for display only and never reaches the HOS engine** — drive time
is always distance ÷ 55 mph, per the assumption above. `test_ors_duration_never_reaches_the_hos_math`
feeds the planner a route ORS claims takes 40 hours and asserts the resulting log is byte-identical
to one built from the same distances with a sane duration.

Failures raise `AddressNotFound`, `GeocodingError` or `RoutingError`, all carrying messages safe
to show a driver. The API turns these into 400s.

## API

**`POST /api/trips/`** — takes the four inputs, returns `{ trip, route, logs }` and a `201` with
a persisted id. **`GET /api/trips/<id>/`** returns the same payload again, which is what makes
that id worth storing.

Everything that can go wrong is a `400` with a message the form can display — never a `500` and
never a traceback: unresolvable address, geocoder or router unreachable, no route found, a
missing ORS key, a blank field, `current_cycle_used` outside 0–70, or the same pickup and
dropoff. A test asserts the error body contains nothing but `error`.

### The two durations

They travel together and must never be confused, so each carries its own basis string:

```json
"total_drive_hours": 33.63,
"drive_hours_basis": "distance / 55 mph (assumed)",
"provider_eta_hours": 7.5,
"provider_eta_source": "OpenRouteService driving-hgv"
```

`total_drive_hours` keeps the contract's field name and is what every log sheet is built on.
`provider_eta_hours` is carried for display only. A test feeds the endpoint a route the provider
claims takes 40 hours and asserts the returned logs are byte-identical.

`provider_eta_source` is reported by the router that actually answered, not assumed by the
caller — with two providers supported, a summary naming the wrong one is worse than no label.
Geoapify folds its profile into that name, so a `truck`→`drive` fallback reads as
`"Geoapify drive"` on screen rather than passing silently as a truck route. The value is stored
on the trip, so refetching an old trip still names the provider that served it.

### Positioning stops on the map

Only the three geocoded addresses have real coordinates. Fuel stops, breaks and rests happen at
an odometer reading, not a place, so they are positioned by walking the route polyline and
interpolating to the fraction of the trip completed — using the engine's mileage as the basis,
never the polyline's own measured length, which is a few percent short on simplified geometry.

### Day totals

The engine works in whole minutes summing to exactly 1440. Rounding four of those to two-decimal
hours independently can land on 23.99 or 24.01, so the residual is folded into the largest
bucket. `test_naive_rounding_really_would_drift` proves that correction is load-bearing rather
than decoration.

### Timezone

`USE_TZ = False`, deliberately. An ELD log sheet is defined in a single home-terminal local time
— the midnight its days are cut at is the terminal's, not UTC's. Leaving it on made Django
relabel the engine's naive local datetimes as UTC, which would shift the day boundaries the logs
are built on.

## Assumptions

The brief fixes the HOS limits but leaves several things open. Every value below lives in one
place — [`backend/hos/constants.py`](backend/hos/constants.py) — and each is repeated here.

| Assumption | Value | Why |
|---|---|---|
| Distance → drive time | **fixed 55 mph**, not the routing API's `duration` | The same distance must always produce the same log. A live traffic-aware duration would make a reviewer's run disagree with the recorded demo. OpenRouteService's duration will still be shown for information, but the HOS math never depends on it. |
| Fuel-stop duration | **30 min, on-duty (not driving)** | Not fixed by the brief. Being ≥30 min of consecutive non-driving time it *also* satisfies the 30-minute break, so the engine never stacks a redundant break after fueling. |
| Fuel-stop placement | every 1000 odometer-miles, **skipped when no trip miles remain** | Avoids a fuel stop at the dropoff door. See the note below on what this means for the count. |
| 10-h reset / 34-h restart status | **sleeper berth** | Both `off_duty` and `sleeper` are legal. Sleeper is how an over-the-road driver actually logs an overnight, and it exercises all four rows of the log grid. |
| 30-minute break status | **off duty** | |
| Trip start | **06:00 local; day 1 opens off-duty 00:00–06:00. No pre-trip inspection hour.** | Deterministic, so tests need no time mocking. The brief mandates only the 1 h pickup and 1 h dropoff; adding a third on-duty hour would burn the 70-hour cycle faster than the stated rules imply. |
| Timezone | single home-terminal local time, naive datetimes | Makes the midnight split unambiguous. No DST handling. |
| Internal time unit | **whole minutes** | Float hours drift, which would make "every day's totals sum to exactly 24:00" flaky. Minutes stay exact and are what the log grid wants anyway. |
| Cycle model | one counter seeded from `current_cycle_used` | The input is a single scalar, so there is no 8-day history to roll. A true rolling 70/8 window would need per-day history the brief does not provide. |

### Two deliberate deviations

**The 70-hour cycle is checked continuously, not at leg ends.** The reference pseudocode tests
the cycle only after a pickup or dropoff, which lets it sail past 70 hours mid-leg and be
noticed hours later — that cannot satisfy the invariant it is meant to uphold. Here the
remaining cycle time is one of the terms sizing every driving chunk, so the limit binds the
moment it is reached.

**Fuel-stop count at exact 1000-mile multiples.** Because a stop with zero miles remaining is
skipped, a trip of exactly 2000 miles yields 1 fuel stop, not `floor(2000/1000) == 2`. This is
the intended trade: no fuel stop at the destination door. The edge case is pinned by
`test_exact_multiple_skips_the_terminal_fuel_stop` rather than left to chance.

## Testing

The seven graded invariants are in
[`backend/tests/test_invariants.py`](backend/tests/test_invariants.py). Two things make them
worth trusting:

**The tests do not read the engine's counters.**
[`tests/replay.py`](backend/tests/replay.py) walks the emitted timeline and reconstructs
`drive_in_window`, `window_elapsed`, `drive_since_break` and `cycle_used` from scratch. The
regulation numbers are hardcoded there and in the tests rather than imported from
`hos.constants` — otherwise widening the driving cap to 12 h would move the engine and its own
test together and the test would still pass.

**The suite was mutation-tested.** Fourteen deliberate bugs were injected (widen the driving
cap, drop the break term, remove the cycle guards, shorten the reset, ignore the 14-hour
window, log rests as driving, change the fuel interval, change the assumed speed, …). Every one
is caught. Three test gaps that the first draft of the suite missed were found this way and
fixed:

- no fixture was long enough to tell a 1000-mile fuel interval from a 1500-mile one, so a
  2600-mile case was added;
- with one pickup and one dropoff, non-driving time in a window tops out at exactly 3 h, so
  11 h of driving always binds before the 14-hour window and that rule was never exercised — a
  synthetic multi-stop trip now forces it;
- an engine that ignored a fuel stop's contribution to the 30-minute break inserted a redundant
  break several driving hours later, which an adjacency check could not see.

The service layer was mutation-tested the same way — eight injected bugs (legs derived from ORS
duration, forgetting the lng/lat flip, the car profile instead of the truck one, metres read as
kilometres, a cache that never hits, a throttle that never waits, a dropped User-Agent, an
unresolvable address silently returning coordinates `0,0`). All eight are caught.

No test in the default suite touches the network: the whole run passes with `socket.connect`
patched to raise.
