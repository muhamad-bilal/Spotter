/**
 * Renders the real component and inspects the SVG it produces.
 *
 * The point is to check the drawing, not just the arithmetic: a segment has to
 * land at the right x on the right row, and the totals printed on the sheet have
 * to be the ones in the payload. Asserting on the markup is what catches a
 * component that computes correctly and then draws somewhere else.
 */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import LogSheet from './LogSheet.jsx'
import LogSheetList from './LogSheetList.jsx'

// Written out rather than imported from logGrid: if the test read the layout
// from the module it is checking, a change to either would move both together
// and the assertion would prove nothing.
const GRID_X = 160
const GRID_W = 794
const xForMinute = (minute) => GRID_X + (minute / 1440) * GRID_W
const minuteForX = (x) => ((x - GRID_X) / GRID_W) * 1440
const isOnTick = (minute) => Math.abs(minute - Math.round(minute / 15) * 15) < 1e-6

const DAY_ONE = {
  date: '2026-07-21',
  total_miles: 605,
  totals: { off_duty: 6.0, sleeper: 6.0, driving: 11.0, on_duty: 1.0 },
  segments: [
    { status: 'off_duty', start_minute: 0, end_minute: 360, remark: 'Chicago, IL' },
    { status: 'driving', start_minute: 360, end_minute: 687, remark: '' },
    { status: 'on_duty', start_minute: 687, end_minute: 747, remark: 'Indianapolis, IN - pickup' },
    { status: 'driving', start_minute: 747, end_minute: 1080, remark: '' },
    { status: 'sleeper', start_minute: 1080, end_minute: 1440, remark: '10-hour rest' },
  ],
}

const DAY_TWO = {
  date: '2026-07-22',
  total_miles: 0,
  totals: { off_duty: 24.0, sleeper: 0.0, driving: 0.0, on_duty: 0.0 },
  segments: [{ status: 'off_duty', start_minute: 0, end_minute: 1440, remark: 'Columbus, OH' }],
}

const render = (element) => renderToStaticMarkup(element)

/** Every <line> carrying a data-status, i.e. the drawn duty-status trace. */
function segmentLines(markup) {
  return [...markup.matchAll(/<line[^>]*data-status="([^"]+)"[^>]*>/g)].map((match) => {
    const tag = match[0]
    const attr = (name) => {
      const found = tag.match(new RegExp(`${name}="([^"]+)"`))
      return found ? found[1] : null
    }
    return {
      status: match[1],
      start: Number(attr('data-start')),
      end: Number(attr('data-end')),
      x1: Number(attr('x1')),
      x2: Number(attr('x2')),
      y1: Number(attr('y1')),
      y2: Number(attr('y2')),
    }
  })
}

function totalTexts(markup) {
  return [...markup.matchAll(/<text[^>]*data-status="([^"]+)"[^>]*>([^<]*)<\/text>/g)].map(
    (match) => ({ status: match[1], text: match[2] }),
  )
}

describe('LogSheet', () => {
  const markup = render(<LogSheet day={DAY_ONE} index={0} count={2} />)

  it('draws one line per segment', () => {
    expect(segmentLines(markup)).toHaveLength(DAY_ONE.segments.length)
  })

  it('places a driving segment at the expected x-range on the driving row', () => {
    const [driving] = segmentLines(markup).filter((line) => line.status === 'driving')

    // The data attributes carry the TRUE minutes...
    expect(driving.start).toBe(360)
    expect(driving.end).toBe(687)
    // ...but the DRAWN x is snapped to the quarter-hour tick: 687 (11:27) -> 690.
    expect(driving.x1).toBeCloseTo(xForMinute(360), 6)
    expect(driving.x2).toBeCloseTo(xForMinute(690), 6)
    // 06:00 is a quarter of the way across the 24-hour grid.
    expect(driving.x1 - GRID_X).toBeCloseTo(GRID_W * 0.25, 6)
    // Horizontal: a duty-status line never slopes.
    expect(driving.y1).toBe(driving.y2)
  })

  it('snaps every drawn boundary to a quarter-hour tick', () => {
    for (const line of segmentLines(markup)) {
      expect(isOnTick(minuteForX(line.x1))).toBe(true)
      expect(isOnTick(minuteForX(line.x2))).toBe(true)
    }
  })

  it('draws every connector on a quarter-hour tick', () => {
    const connectorXs = [...markup.matchAll(/class="sheet__connector"[^>]*x1="([\d.]+)"/g)].map(
      (m) => Number(m[1]),
    )
    expect(connectorXs).toHaveLength(4)
    for (const x of connectorXs) {
      expect(isOnTick(minuteForX(x))).toBe(true)
    }
  })

  it('keeps the trace contiguous after snapping (no gaps or overlaps)', () => {
    // Each drawn segment ends exactly where the next begins.
    const lines = segmentLines(markup).sort((a, b) => a.start - b.start)
    for (let i = 0; i < lines.length - 1; i += 1) {
      expect(lines[i].x2).toBeCloseTo(lines[i + 1].x1, 6)
    }
  })

  it('puts each status on its own row, ordered off/sleeper/driving/on-duty', () => {
    const rowY = {}
    for (const line of segmentLines(markup)) rowY[line.status] = line.y1

    expect(rowY.off_duty).toBeLessThan(rowY.sleeper)
    expect(rowY.sleeper).toBeLessThan(rowY.driving)
    expect(rowY.driving).toBeLessThan(rowY.on_duty)
    // The two driving segments share one row.
    const driving = segmentLines(markup).filter((l) => l.status === 'driving')
    expect(driving[0].y1).toBe(driving[1].y1)
  })

  it('joins the trace with a vertical connector at every status change', () => {
    const connectors = [...markup.matchAll(/class="sheet__connector"[^>]*>/g)]
    // Four changes across five segments.
    expect(connectors).toHaveLength(4)
  })

  it('prints the totals from the payload, unmodified', () => {
    expect(totalTexts(markup)).toEqual([
      { status: 'off_duty', text: '6.00' },
      { status: 'sleeper', text: '6.00' },
      { status: 'driving', text: '11.00' },
      { status: 'on_duty', text: '1.00' },
    ])
  })

  it('totals on the sheet sum to exactly 24.00', () => {
    const sum = totalTexts(markup).reduce((total, row) => total + Number(row.text), 0)
    expect(sum).toBeCloseTo(24.0, 10)
    expect(markup).toContain('>24.00<')
  })

  it('shows the date and the miles driven', () => {
    expect(markup).toContain('605')
    expect(markup).toMatch(/Jul 21, 2026/)
  })

  it('drops a remark at each labelled status change', () => {
    expect(markup).toContain('Chicago, IL')
    // 'Indianapolis, IN - pickup' is over the 20-char cap, so it renders
    // truncated -- assert the prefix rather than the full string.
    expect(markup).toContain('Indianapolis')
    expect(markup).toContain('10-hour rest')
  })

  it('never lets a remark label rise into the grid', () => {
    // The label slants up to the right; its highest point is the far end of the
    // baseline plus the glyph cap height. Reconstructed here from the same angle
    // and font metrics the component uses, then asserted below the grid baseline.
    const ANGLE = (50 * Math.PI) / 180
    const FONT = 10
    const CHAR_W = 0.58
    const CAP = 0.717
    const GRID_BOTTOM_Y = 54 + 4 * 38 // SVG GRID_TOP(54) + 4 rows * ROW_H(38) = 206

    const labels = [...markup.matchAll(/class="sheet__remark"[^>]*y="([\d.]+)"[^>]*>([^<]+)</g)]
    expect(labels.length).toBeGreaterThan(0)

    for (const [, anchorYStr, text] of labels) {
      const anchorY = Number(anchorYStr) // lowest point (left end of the baseline)
      const width = text.length * FONT * CHAR_W
      const topY = anchorY - width * Math.sin(ANGLE) - FONT * CAP * Math.cos(ANGLE)
      expect(topY).toBeGreaterThan(GRID_BOTTOM_Y)
    }
  })

  it('labels all four rows, and midnight once', () => {
    for (const label of ['Off Duty', 'Sleeper Berth', 'Driving', 'On Duty (Not Driving)']) {
      expect(markup).toContain(label)
    }
    // Only the opening midnight is labelled -- the closing one collided with the
    // totals-column caption, and a 24-hour grid ending at midnight is obvious.
    expect(markup.match(/Midnight/g)).toHaveLength(1)
    expect(markup).toContain('Noon')
  })

  it('keeps every row caption inside the label gutter', () => {
    // "On Duty (Not Driving)" is the longest and was clipping at the sheet edge.
    // Anchored at the gutter's right edge, so its left end must clear the row
    // numbers rather than run off the sheet.
    const anchors = [...markup.matchAll(/class="sheet__row-label" x="([\d.]+)"/g)].map((m) =>
      Number(m[1]),
    )
    expect(anchors).toHaveLength(4)
    for (const x of anchors) {
      expect(x).toBeLessThan(GRID_X)
      expect(x).toBeGreaterThan(120) // room for ~21 characters at 11px
    }
  })
})

describe('degenerate days', () => {
  it('renders a day that is entirely one status', () => {
    const markup = render(<LogSheet day={DAY_TWO} index={1} count={2} />)
    const lines = segmentLines(markup)

    expect(lines).toHaveLength(1)
    expect(lines[0].x1).toBeCloseTo(GRID_X, 6)
    expect(lines[0].x2).toBeCloseTo(GRID_X + GRID_W, 6)
    expect(markup).not.toContain('sheet__connector')

    const sum = totalTexts(markup).reduce((total, row) => total + Number(row.text), 0)
    expect(sum).toBeCloseTo(24.0, 10)
  })

  it('survives an empty segment list', () => {
    const day = { ...DAY_TWO, segments: [] }
    const markup = render(<LogSheet day={day} index={0} count={1} />)
    expect(segmentLines(markup)).toHaveLength(0)
    expect(markup).toContain('Off Duty') // the grid is still drawn
  })

  it('survives malformed segments without drawing them', () => {
    const day = {
      ...DAY_TWO,
      segments: [
        { status: 'nonsense', start_minute: 0, end_minute: 60 },
        { status: 'driving', start_minute: null, end_minute: 60 },
        { status: 'driving', start_minute: 120, end_minute: 180, remark: 'kept' },
      ],
    }
    const markup = render(<LogSheet day={day} index={0} count={1} />)
    expect(segmentLines(markup)).toHaveLength(1)
    expect(markup).toContain('kept')
  })

  it('survives missing totals', () => {
    const day = { date: '2026-07-21', total_miles: 0, segments: [] }
    const markup = render(<LogSheet day={day} index={0} count={1} />)
    expect(totalTexts(markup).map((row) => row.text)).toEqual(['0.00', '0.00', '0.00', '0.00'])
  })

  it('keeps a sub-tick stop visible at a minimum one-tick width', () => {
    // A real 10-minute on-duty stop would round to zero width and vanish; it
    // must be widened to a full quarter-hour instead.
    const day = {
      date: '2026-07-21',
      total_miles: 0,
      totals: { off_duty: 23.83, sleeper: 0, driving: 0, on_duty: 0.17 },
      segments: [
        { status: 'off_duty', start_minute: 0, end_minute: 100, remark: 'A' },
        { status: 'on_duty', start_minute: 100, end_minute: 110, remark: '' },
        { status: 'off_duty', start_minute: 110, end_minute: 1440, remark: 'B' },
      ],
    }
    const markup = render(<LogSheet day={day} index={0} count={1} />)
    const [onDuty] = segmentLines(markup).filter((line) => line.status === 'on_duty')
    const widthMinutes = minuteForX(onDuty.x2) - minuteForX(onDuty.x1)
    expect(widthMinutes).toBeGreaterThanOrEqual(15 - 1e-6)
  })
})

describe('LogSheetList', () => {
  it('renders one sheet per day for a multi-day trip', () => {
    const markup = render(<LogSheetList logs={[DAY_ONE, DAY_TWO]} />)
    expect(markup.match(/class="sheet"/g)).toHaveLength(2)
    expect(markup).toContain('Day 1 of 2')
    expect(markup).toContain('Day 2 of 2')
    expect(markup).toContain('2 days')
  })

  it('renders a single sheet for a one-day trip', () => {
    const markup = render(<LogSheetList logs={[DAY_ONE]} />)
    expect(markup.match(/class="sheet"/g)).toHaveLength(1)
    expect(markup).toContain('1 day')
  })

  it('every sheet in a multi-day trip totals 24.00', () => {
    for (const day of [DAY_ONE, DAY_TWO]) {
      const sum = totalTexts(render(<LogSheet day={day} index={0} count={2} />)).reduce(
        (total, row) => total + Number(row.text),
        0,
      )
      expect(sum).toBeCloseTo(24.0, 10)
    }
  })

  it('handles no logs at all', () => {
    expect(render(<LogSheetList logs={[]} />)).toContain('No log days')
    expect(render(<LogSheetList logs={undefined} />)).toContain('No log days')
  })

  it('offers a PDF download pointing at the trip', () => {
    const markup = render(<LogSheetList logs={[DAY_ONE, DAY_TWO]} tripId={42} />)
    expect(markup).toContain('/api/trips/42/logs.pdf')
    expect(markup).toContain('Download PDF')
    expect(markup).toContain('download="drivers-daily-log-trip-42.pdf"')
  })

  it('offers no download when there is nothing to print', () => {
    expect(render(<LogSheetList logs={[]} tripId={42} />)).not.toContain('Download PDF')
    expect(render(<LogSheetList logs={[DAY_ONE]} />)).not.toContain('Download PDF')
  })
})
