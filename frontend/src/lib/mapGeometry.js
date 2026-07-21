/**
 * Geometry preparation, kept free of React and Leaflet so it can be checked
 * directly.
 *
 * The API positions fuel stops, breaks and rests by interpolating along the
 * route polyline, and returns null coordinates if it had no geometry to
 * interpolate along. A trip is still perfectly valid in that case -- the logs do
 * not depend on the map -- so nothing here may throw. Anything unplottable is
 * dropped, and the caller decides what to show when nothing is left.
 */

const isFiniteNumber = (value) => typeof value === 'number' && Number.isFinite(value)

/** A [lat, lng] pair is plottable only if both halves are real numbers in range. */
export function isPlottable(point) {
  if (!Array.isArray(point) || point.length < 2) return false
  const [lat, lng] = point
  return (
    isFiniteNumber(lat) &&
    isFiniteNumber(lng) &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180
  )
}

/** The route line, with any unusable vertex removed. */
export function routeLine(geometry) {
  if (!Array.isArray(geometry)) return []
  return geometry.filter(isPlottable).map(([lat, lng]) => [lat, lng])
}

/** Stops that can actually be placed on the map. */
export function plottableStops(stops) {
  if (!Array.isArray(stops)) return []
  return stops.filter((stop) => stop && isPlottable([stop.lat, stop.lng]))
}

/**
 * Bounds framing the whole trip, or null if there is nothing to frame.
 * A single point yields a degenerate bound; the caller centres on it instead.
 */
export function routeBounds(line, stops) {
  const points = [...line, ...stops.map((stop) => [stop.lat, stop.lng])]
  if (points.length === 0) return null

  let [minLat, minLng] = points[0]
  let [maxLat, maxLng] = points[0]
  for (const [lat, lng] of points) {
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
    if (lng < minLng) minLng = lng
    if (lng > maxLng) maxLng = lng
  }
  return [
    [minLat, minLng],
    [maxLat, maxLng],
  ]
}

export function boundsAreDegenerate(bounds) {
  if (!bounds) return true
  const [[minLat, minLng], [maxLat, maxLng]] = bounds
  return minLat === maxLat && minLng === maxLng
}

export function boundsCenter(bounds) {
  if (!bounds) return null
  const [[minLat, minLng], [maxLat, maxLng]] = bounds
  return [(minLat + maxLat) / 2, (minLng + maxLng) / 2]
}

/** Everything the map needs, derived once. */
export function prepareRoute(route) {
  const line = routeLine(route?.geometry)
  const stops = plottableStops(route?.stops)
  const bounds = routeBounds(line, stops)
  return {
    line,
    stops,
    bounds,
    // A polyline needs two points to be a line at all.
    hasLine: line.length >= 2,
    hasAnything: bounds !== null,
    droppedStops: (route?.stops?.length ?? 0) - stops.length,
  }
}
