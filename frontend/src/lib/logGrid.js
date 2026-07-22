/**
 * Geometry for the FMCSA daily log grid, kept free of React so it can be
 * checked directly.
 *
 * The whole sheet is drawn in one fixed SVG coordinate space and scaled by the
 * viewBox, so every number here is a constant rather than something measured
 * from the DOM. Minutes-from-midnight map straight onto x, which is exactly why
 * the API stores segments that way.
 */

export const MINUTES_PER_DAY = 1440

// Layout, in SVG user units.
// LABEL_W has to clear the longest caption, "On Duty (Not Driving)", with room
// for the row number to its left -- at 132 it was clipping against the sheet edge.
export const LABEL_W = 160 // row captions on the left
export const LABEL_PAD_LEFT = 16 // row numbers sit here
export const TOTALS_W = 74 // summed hours on the right
export const GRID_X = LABEL_W
export const GRID_W = 794 // the plotting area itself is unchanged
export const WIDTH = GRID_X + GRID_W + TOTALS_W // 1028

export const GRID_TOP = 54 // below the hour labels
export const ROW_H = 38
export const ROW_COUNT = 4
export const GRID_H = ROW_H * ROW_COUNT
export const GRID_BOTTOM = GRID_TOP + GRID_H

export const REMARKS_H = 116
export const HEIGHT = GRID_BOTTOM + REMARKS_H

// Remark labels slant up to the right (classic log look) but must never rise
// into the duty rows. Same approach as the PDF renderer: anchor each label deep
// enough that even the highest, right-hand end of the rising text stays below
// the grid baseline. Width is estimated from the character count -- a slightly
// generous per-character factor keeps the clearance conservative.
export const REMARK_ANGLE = 50 // degrees, up to the right
export const REMARK_MAX_CHARS = 20
const REMARK_FONT_SIZE = 10 // must match .sheet__remark font-size
const REMARK_CHAR_W = 0.58 // avg Helvetica advance as a fraction of font size
const REMARK_CAP_RATIO = 0.717 // cap height fraction
const REMARK_TOP_GAP = 9 // clearance kept below the baseline

export function truncateRemark(text) {
  const trimmed = String(text).trim()
  return trimmed.length <= REMARK_MAX_CHARS
    ? trimmed
    : `${trimmed.slice(0, REMARK_MAX_CHARS - 3).trimEnd()}...`
}

export function remarkAnchorDepth(text) {
  const width = truncateRemark(text).length * REMARK_FONT_SIZE * REMARK_CHAR_W
  const angle = (REMARK_ANGLE * Math.PI) / 180
  return (
    width * Math.sin(angle) +
    REMARK_FONT_SIZE * REMARK_CAP_RATIO * Math.cos(angle) +
    REMARK_TOP_GAP
  )
}

/** Top to bottom, exactly the order printed on a real log. */
export const ROWS = [
  { status: 'off_duty', label: 'Off Duty', short: '1' },
  { status: 'sleeper', label: 'Sleeper Berth', short: '2' },
  { status: 'driving', label: 'Driving', short: '3' },
  { status: 'on_duty', label: 'On Duty (Not Driving)', short: '4' },
]

const ROW_INDEX = Object.fromEntries(ROWS.map((row, index) => [row.status, index]))

const isFiniteNumber = (value) => typeof value === 'number' && Number.isFinite(value)

/** Minutes from midnight -> x. Clamped, so bad data cannot draw off the sheet. */
export function minuteToX(minute) {
  const clamped = Math.min(MINUTES_PER_DAY, Math.max(0, isFiniteNumber(minute) ? minute : 0))
  return GRID_X + (clamped / MINUTES_PER_DAY) * GRID_W
}

/** The y of a row's centre line -- where the trace is drawn. */
export function rowY(status) {
  const index = ROW_INDEX[status]
  if (index === undefined) return null
  return GRID_TOP + index * ROW_H + ROW_H / 2
}

/** Rows' top edges, for drawing the bands. */
export function rowTop(index) {
  return GRID_TOP + index * ROW_H
}

function isDrawable(segment) {
  return (
    segment &&
    ROW_INDEX[segment.status] !== undefined &&
    isFiniteNumber(segment.start_minute) &&
    isFiniteNumber(segment.end_minute) &&
    segment.end_minute > segment.start_minute
  )
}

// The printed grid resolves to quarter hours. Real duty changes land on exact
// minutes from routed distance (e.g. 11:27), which then float between ticks and
// read as misaligned. Snapping is a RENDERING concern only: the segment data and
// the reported totals are never touched.
export const TICK_MINUTES = 15

/** Nearest quarter-hour, rounding halves up so SVG and PDF agree exactly. */
export function snapMinute(minute) {
  return Math.floor(minute / TICK_MINUTES + 0.5) * TICK_MINUTES
}

/**
 * Snap each segment's drawn span to quarter-hour boundaries.
 *
 * Two guarantees the naive "round each end" approach cannot make:
 *  - Contiguity: a segment's drawn end IS the next segment's drawn start, so the
 *    trace never gains a gap or an overlap. Achieved by carrying the previous
 *    snapped end forward as the next start (the timeline is contiguous, so in the
 *    common case that equals the independently-snapped start anyway).
 *  - Minimum width: a segment shorter than one tick (a real 20-minute stop that
 *    would otherwise round to zero width) is widened to a full tick so it stays
 *    visible. That push carries forward, keeping everything aligned to ticks.
 */
function snapSegments(segments) {
  const usable = (Array.isArray(segments) ? segments : [])
    .filter(isDrawable)
    .slice()
    .sort((a, b) => a.start_minute - b.start_minute)

  let cursor = null
  return usable.map((segment) => {
    let start = cursor === null ? snapMinute(segment.start_minute) : cursor
    let end = snapMinute(segment.end_minute)
    if (end < start + TICK_MINUTES) end = start + TICK_MINUTES
    if (end > MINUTES_PER_DAY) end = MINUTES_PER_DAY
    if (start > MINUTES_PER_DAY - TICK_MINUTES) start = MINUTES_PER_DAY - TICK_MINUTES
    cursor = end
    return { segment, snapStart: start, snapEnd: end }
  })
}

/**
 * The drawn trace: one horizontal line per segment, plus the vertical
 * connectors at each status change that make it read as one continuous pen
 * stroke rather than a row of disconnected dashes. Drawn positions are snapped
 * to quarter-hour ticks; `startMinute`/`endMinute` keep the true values.
 */
export function buildTrace(segments) {
  const snapped = snapSegments(segments)

  const lines = snapped.map(({ segment, snapStart, snapEnd }) => ({
    status: segment.status,
    x1: minuteToX(snapStart),
    x2: minuteToX(snapEnd),
    y: rowY(segment.status),
    startMinute: segment.start_minute,
    endMinute: segment.end_minute,
  }))

  const connectors = []
  for (let i = 0; i < snapped.length - 1; i += 1) {
    const from = snapped[i].segment
    const to = snapped[i + 1]
    if (from.status === to.segment.status) continue // no change, nothing to connect
    connectors.push({
      // The shared snapped boundary -- a quarter-hour tick by construction.
      x: minuteToX(to.snapStart),
      y1: rowY(from.status),
      y2: rowY(to.segment.status),
    })
  }

  return { lines, connectors }
}

/**
 * Where the location labels hang under the grid.
 *
 * One per status change that carries a remark, anchored at the same snapped
 * boundary as the connector so the stem lines up with the trace.
 */
export function buildRemarks(segments) {
  return snapSegments(segments)
    .filter(
      ({ segment }) =>
        typeof segment.remark === 'string' && segment.remark.trim(),
    )
    .map(({ segment, snapStart }) => ({
      x: minuteToX(snapStart),
      minute: segment.start_minute,
      text: segment.remark.trim(),
    }))
}

/** The 24 hour ticks, labelled the way a paper log is. */
export function hourTicks() {
  return Array.from({ length: 25 }, (_, hour) => ({
    hour,
    x: minuteToX(hour * 60),
    label: hour === 0 || hour === 24 ? 'Midnight' : hour === 12 ? 'Noon' : String(hour % 12),
    isMajor: hour % 6 === 0,
  }))
}

/** The 15-minute subdivisions inside each hour, excluding the hour lines. */
export function quarterTicks() {
  const ticks = []
  for (let hour = 0; hour < 24; hour += 1) {
    for (const quarter of [15, 30, 45]) {
      ticks.push({
        x: minuteToX(hour * 60 + quarter),
        // The half-hour mark is drawn taller, as on the printed form.
        height: quarter === 30 ? ROW_H * 0.42 : ROW_H * 0.24,
      })
    }
  }
  return ticks
}

/** Hours to the two decimals the totals column prints. */
export function formatHours(hours) {
  return (isFiniteNumber(hours) ? hours : 0).toFixed(2)
}

/**
 * The four totals, straight from the payload.
 *
 * Deliberately not recomputed from the segments: the API already guarantees the
 * four values sum to exactly 24.00, and deriving them a second way here would
 * be a second source of truth free to drift from the one the logs were built
 * on.
 */
export function totalsForDisplay(totals) {
  return ROWS.map(({ status, label }) => ({
    status,
    label,
    hours: totals?.[status] ?? 0,
    text: formatHours(totals?.[status] ?? 0),
  }))
}

export function totalOfDisplayed(totals) {
  return totalsForDisplay(totals).reduce((sum, row) => sum + Number(row.text), 0)
}
