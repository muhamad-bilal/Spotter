import { kindsPresent, stopMeta } from '../../lib/stops.js'

/**
 * Only the kinds this trip actually contains. A legend listing rests and
 * restarts for a short single-day run would be noise, and worse, would imply
 * the map is missing pins it never had.
 */
export default function MapLegend({ stops }) {
  const kinds = kindsPresent(stops)
  if (kinds.length === 0) return null

  return (
    <ul className="legend">
      {kinds.map((kind) => {
        const { label, glyph, description } = stopMeta(kind)
        return (
          <li className="legend__item" key={kind} title={description}>
            <span className={`pin pin--sm pin--${kind}`} aria-hidden="true">
              <span className="pin__glyph">{glyph}</span>
            </span>
            <span className="legend__label">{label}</span>
          </li>
        )
      })}
    </ul>
  )
}
