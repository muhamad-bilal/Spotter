# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

# Project: ELD Trip Planner (Full-Stack Assessment)

Project-specific instructions. These refine the general guidelines above for this build.

## Context and sources of truth
- Read `ARCHITECTURE.md` at the project root before starting any step — it holds the system design, data model, API contract, and build order.
- The `eld-trip-planner` skill holds the domain rules (HOS limits, the simulation algorithm, the ELD grid spec). Consult it whenever touching HOS logic, route stops, or log-sheet rendering. Don't re-derive the rules from memory.
- This is a graded take-home. Reviewers test the **hosted** version for accuracy and judge **UI/UX**. Good design partially compensates for output inaccuracies.

## Scope clarifications (these override the generic "Simplicity First" defaults for this project)
- **UI/UX polish is in scope, not speculative.** Map marker styling + legend, the ELD log-sheet visuals, loading and error states, and responsive layout are graded requirements. Do not strip them citing simplicity. Simplicity applies to *internal structure and abstractions*, not to user-facing quality.
- **Input validation is on the test path, not an "impossible scenario."** Reviewers will submit a bad/unresolvable address and a `current_cycle_used` > 70. Validate inputs and return clear `400` messages the form can display.
- Everything else in "Simplicity First" still holds: no premature abstractions, no config knobs nobody asked for, no speculative endpoints.

## Tech constraints
- Backend: Django + Django REST Framework. Frontend: React + Vite.
- Only free, keyless-or-free-tier external services: OpenRouteService (routing), Nominatim (geocoding), OpenStreetMap tiles via react-leaflet. No paid APIs, no billing-required services.
- Keep routing/geocoding behind service classes so a provider swap is a one-file change.
- Deployment: React → Vercel; Django → Render/Railway free tier. Frontend reaches the backend via `VITE_API_BASE_URL`; enable CORS for the Vercel origin.

## Build order (always keep something demoable)
Follow this sequence; don't jump ahead:
1. HOS simulation engine in isolation (pure functions, no Django) — riskiest, build first.
2. Routing + geocoding service wrappers.
3. Django `POST /api/trips/` wiring services + engine into the response payload.
4. React form + trip summary (plain round trip).
5. Route map (polyline + typed markers + legend).
6. ELD log-sheet SVG (the showpiece; iterate against a known-good fixture).
7. Polish, deploy, smoke-test the hosted pair.

## Success criteria for the HOS engine (apply "Goal-Driven Execution" §4 here)
Write these as tests first, then make them pass. Do not proceed to the API until they're green:
- Every day's four duty-status totals sum to exactly 24:00.
- No `driving` segment starts after 14h of window elapsed.
- Driving within a window never exceeds 11h between 10h resets.
- A ≥30-min non-driving break appears before cumulative driving passes 8h.
- Cycle on-duty never exceeds 70h without a 34h restart between.
- Fuel-stop count == floor(total_miles / 1000).
- Pickup and dropoff each add exactly 1h on-duty.

## Assumptions to state explicitly (apply §1)
The brief leaves these open. Pick values, state them in the README and in code comments, and keep them in one constants module:
- Average driving speed used to convert distance → drive time (e.g., 55 mph), or whether you use the routing API's duration instead.
- Fuel-stop duration (e.g., 30 min; note it also satisfies the 30-min break when it lands).
Surface any other assumption you make rather than deciding silently.