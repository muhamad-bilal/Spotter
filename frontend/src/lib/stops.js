/**
 * One source of truth for how a stop kind is presented.
 *
 * The map markers and the legend both read from here, so a pin can never end up
 * a different colour from its legend entry. The seven keys are exactly the
 * `stop.kind` values the API documents.
 */

export const STOP_META = {
  start: {
    label: 'Start',
    glyph: 'S',
    description: 'Where the driver begins',
  },
  pickup: {
    label: 'Pickup',
    glyph: 'P',
    description: '1 hour on duty, loading',
  },
  dropoff: {
    label: 'Dropoff',
    glyph: 'D',
    description: '1 hour on duty, unloading',
  },
  fuel: {
    label: 'Fuel',
    glyph: 'F',
    description: '30 min on duty, every 1,000 miles',
  },
  break_30: {
    label: '30-min break',
    glyph: '30',
    description: 'Required after 8 hours driving',
  },
  rest_10: {
    label: '10-hour rest',
    glyph: '10',
    description: 'Resets the 11-hour and 14-hour limits',
  },
  restart_34: {
    label: '34-hour restart',
    glyph: '34',
    description: 'Resets the 70-hour cycle',
  },
}

export const STOP_ORDER = [
  'start',
  'pickup',
  'dropoff',
  'fuel',
  'break_30',
  'rest_10',
  'restart_34',
]

const FALLBACK = { label: 'Stop', glyph: '•', description: '' }

export function stopMeta(kind) {
  return STOP_META[kind] ?? FALLBACK
}

export function stopColor(kind) {
  return STOP_META[kind] ? `var(--stop-${kind})` : 'var(--text-muted)'
}

/** The kinds actually present in a trip, in a stable presentation order. */
export function kindsPresent(stops) {
  const seen = new Set(stops.map((stop) => stop.kind))
  const known = STOP_ORDER.filter((kind) => seen.has(kind))
  const unknown = [...seen].filter((kind) => !STOP_META[kind]).sort()
  return [...known, ...unknown]
}
