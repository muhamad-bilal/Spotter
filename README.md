# ELD Trip Planner

A driver enters their **current location, pickup, dropoff, and hours already used** in the
70-hour / 8-day cycle. The app returns a **routed trip** with every compliant stop marked — fuel,
30-minute breaks, 10-hour rests — and a set of **drawn ELD daily log sheets**, one per calendar
day, that can be downloaded as a filled-out PDF.

The hard part is the Hours-of-Service simulation: turning a route into a legally compliant
sequence of duty statuses (11-hour driving limit, 14-hour window, 30-minute break, 70/8 cycle),
then slicing that sequence across midnight into individual log sheets.

- **Live demo:** _<add your Vercel URL>_
- **Repository:** _<add your GitHub URL>_

## Screenshots

_<app screenshot: form + route map + summary>_

_<log sheet screenshot: the 24-hour duty-status grid>_

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Django + Django REST Framework |
| Frontend | React + Vite |
| Routing | Geoapify (heavy-goods-vehicle / truck profile) |
| Geocoding | Nominatim |
| Map | OpenStreetMap tiles via react-leaflet |
| PDF | reportlab |
| Hosting | Render (backend) · Vercel (frontend) |

The HOS engine (`backend/hos/`) and the geocoding/routing services (`backend/services/`) are
pure Python with **no Django dependency**, so the domain logic is testable and reusable on its
own; Django is the HTTP + persistence shell around it.

## How it works

The form POSTs the four inputs to `POST /api/trips/`. Django geocodes the three addresses,
routes them, runs the HOS simulation to insert compliant stops and rests, cuts the timeline into
per-day sheets, and returns the whole `{ trip, route, logs }` payload. The frontend draws the
map, the trip summary, and the log sheets from that one response.

## Assumptions

The brief fixes the HOS limits but leaves several things open. Every value lives in one place —
[`backend/hos/constants.py`](backend/hos/constants.py) — and is repeated here.

| Assumption | Value | Why |
|---|---|---|
| Distance → drive time | **fixed 55 mph**, not the routing provider's `duration` | The same distance must always produce the same log; a live traffic-aware duration would make a reviewer's run disagree with the recorded demo. The provider's duration is shown for information but the HOS math never uses it. |
| Fuel-stop duration | **30 min, on-duty (not driving)** | Being ≥30 min of non-driving time it also satisfies the 30-minute break, so the engine never stacks a redundant break after fueling. |
| Fuel-stop placement | every **1000 miles**, skipped when no trip miles remain | Avoids a fuel stop at the dropoff door (so exactly 2000 mi yields 1 stop, not 2). |
| Pickup / dropoff | **1 hour on-duty each** | Fixed by the brief. |
| 10-h reset / 34-h restart | logged as **sleeper berth** | Legal, and how an over-the-road driver actually logs an overnight; exercises all four grid rows. |
| 30-minute break | logged as **off duty** | |
| Trip start | **06:00 local**; day 1 opens off-duty 00:00–06:00, no pre-trip hour | Deterministic — tests need no time mocking. |
| Internal time unit | **whole minutes** | Float hours drift, which would make "every day's totals sum to exactly 24:00" flaky. |

## Scope boundary

The **cycle counter is a single-trip model**, seeded from `current_cycle_used` and accumulated
over the simulated trip — **not a rolling 8-day history**. The input is one scalar, so there is
no day-by-day history to roll; a true rolling 70/8 window would need per-day records the brief
doesn't provide. This is stated on-screen where it matters (the recap's historical columns show
"N/A — single-trip simulation").

Two routing providers are supported behind one interface — **Geoapify is the default**;
OpenRouteService is used if only its key is present. Swapping is an environment change, not a
code change.

## Running locally

```bash
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements.txt   # Linux/macOS: .venv/bin/pip

# backend (terminal 1)
cd backend && python manage.py migrate
              python manage.py runserver 8000            # http://localhost:8000

# frontend (terminal 2)
cd frontend && npm install && npm run dev                # http://localhost:5173
```

**Environment variables** — copy `backend/.env.example` to `backend/.env` (gitignored):

| Variable | Needed for |
|---|---|
| `GEOAPIFY_API_KEY` | routing — free key from [geoapify.com](https://www.geoapify.com/) |
| `NOMINATIM_USER_AGENT` | geocoding — a descriptive agent (Nominatim's policy requires it) |
| `DEBUG` | set `true` for local development; unset in production |

Production deployment (Render + Vercel) is documented in **[DEPLOY.md](DEPLOY.md)**.

## Testing

```bash
cd backend && pytest          # default suite; makes no network calls
```

The HOS engine is built test-first against the **seven graded invariants** — each day's four
duty totals sum to exactly 24:00, driving never exceeds 11 h between resets, no driving after the
14-hour window, a 30-minute break before 8 h cumulative driving, the 70-hour cycle never exceeded
without a 34-hour restart, fuel count = ⌊miles / 1000⌋, and pickup/dropoff each add 1 h on-duty.

Two things make those tests worth trusting: they **reconstruct the HOS counters independently**
from the emitted timeline rather than reading the engine's own, and the suite was
**mutation-tested** — deliberate bugs injected to confirm the tests actually catch them, which
surfaced (and fixed) real gaps. Engineering detail is in **[NOTES.md](NOTES.md)**.

Live tests that hit the real APIs are excluded by default; run them with a key:

```bash
cd backend && GEOAPIFY_API_KEY=your-key pytest -m live -v
```
