import { logsPdfUrl } from '../../api/client.js'
import { ROWS } from '../../lib/logGrid.js'
import LogSheet from './LogSheet.jsx'
import './LogSheet.css'

/**
 * One sheet per calendar day, stacked. A multi-day trip must visibly produce
 * several sheets -- that is explicitly what the brief asks for.
 */
export default function LogSheetList({ logs, tripId }) {
  const days = Array.isArray(logs) ? logs : []

  return (
    <section className="card" aria-labelledby="logs-heading">
      <div className="card__header">
        <h2 className="card__title" id="logs-heading">
          Daily log sheets
        </h2>
        <div className="logs__actions">
          <span className="card__hint">
            {days.length} {days.length === 1 ? 'day' : 'days'}
          </span>
          {tripId != null && days.length > 0 && (
            // A plain link, not a fetch-and-blob: the browser streams the file
            // straight to disk and the filename comes from Content-Disposition.
            <a
              className="button button--quiet"
              href={logsPdfUrl(tripId)}
              download={`drivers-daily-log-trip-${tripId}.pdf`}
            >
              <span aria-hidden="true">↓</span> Download PDF
            </a>
          )}
        </div>
      </div>

      <div className="card__body sheets">
        {days.length === 0 ? (
          <p className="sheet__empty">No log days were produced for this trip.</p>
        ) : (
          <>
            <ul className="duty-key">
              {ROWS.map((row) => (
                <li className="duty-key__item" key={row.status}>
                  <span
                    className="duty-key__swatch"
                    style={{ background: `var(--duty-${row.status.replace('_', '-')})` }}
                    aria-hidden="true"
                  />
                  {row.label}
                </li>
              ))}
            </ul>

            {days.map((day, index) => (
              <LogSheet key={day.date ?? index} day={day} index={index} count={days.length} />
            ))}
          </>
        )}
      </div>
    </section>
  )
}
