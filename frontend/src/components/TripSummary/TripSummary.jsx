import { CYCLE_LIMIT_HOURS } from '../../lib/validation.js'
import './TripSummary.css'

const hours = (value) => `${Number(value).toFixed(2)}`
const miles = (value) => Number(value).toLocaleString('en-US', { maximumFractionDigits: 1 })

export default function TripSummary({ trip }) {
  const cycleUsed = CYCLE_LIMIT_HOURS - trip.cycle_hours_remaining
  const cyclePercent = Math.min(100, Math.max(0, (cycleUsed / CYCLE_LIMIT_HOURS) * 100))

  return (
    <section className="card" aria-labelledby="summary-heading">
      <div className="card__header">
        <h2 className="card__title" id="summary-heading">
          Trip summary
        </h2>
        <span className="card__hint">Trip #{trip.id}</span>
      </div>

      <div className="card__body summary__body">
        <div className="stats">
          <div className="stat">
            <p className="eyebrow">Total distance</p>
            <p className="stat__value tnum">
              {miles(trip.total_distance_miles)}
              <span className="stat__unit">mi</span>
            </p>
          </div>

          <div className="stat">
            <p className="eyebrow">Log sheets</p>
            <p className="stat__value tnum">
              {trip.total_days}
              <span className="stat__unit">{trip.total_days === 1 ? 'day' : 'days'}</span>
            </p>
          </div>

          <div className="stat">
            <p className="eyebrow">Cycle remaining</p>
            <p className="stat__value tnum">
              {hours(trip.cycle_hours_remaining)}
              <span className="stat__unit">hrs</span>
            </p>
            <div
              className="meter"
              role="img"
              aria-label={`${hours(cycleUsed)} of ${CYCLE_LIMIT_HOURS} cycle hours used`}
            >
              <div className="meter__fill" style={{ width: `${cyclePercent}%` }} />
            </div>
            <p className="stat__foot tnum">
              {hours(cycleUsed)} of {CYCLE_LIMIT_HOURS} used
            </p>
          </div>
        </div>

        {/* Two durations that must never be mistaken for one another: the HOS
            figure is what every log sheet is built from, the provider ETA is
            informational. Each carries the basis string the API supplies. */}
        <div className="durations">
          <div className="duration duration--primary">
            <div className="duration__head">
              <p className="eyebrow">Drive time — HOS</p>
              <span className="tag tag--accent">Logs use this</span>
            </div>
            <p className="duration__value tnum">
              {hours(trip.total_drive_hours)}
              <span className="stat__unit">hrs</span>
            </p>
            <p className="duration__basis">{trip.drive_hours_basis}</p>
          </div>

          <div className="duration">
            <div className="duration__head">
              <p className="eyebrow">Provider ETA</p>
              <span className="tag">Display only</span>
            </div>
            <p className="duration__value duration__value--muted tnum">
              {hours(trip.provider_eta_hours)}
              <span className="stat__unit">hrs</span>
            </p>
            <p className="duration__basis">{trip.provider_eta_source}</p>
          </div>
        </div>

        <ResolvedLocations resolved={trip.resolved_locations} />
      </div>
    </section>
  )
}

const RESOLVED_ORDER = [
  ['current', 'Current'],
  ['pickup', 'Pickup'],
  ['dropoff', 'Dropoff'],
]

/* What the geocoder actually matched each typed address to. A bare "LA" or "NY"
   resolves unpredictably, so showing the resolved name lets the driver catch a
   wrong match before trusting the route. */
function ResolvedLocations({ resolved }) {
  if (!resolved || RESOLVED_ORDER.every(([key]) => !resolved[key])) return null

  return (
    <div className="resolved">
      <p className="eyebrow">Resolved locations</p>
      <dl className="resolved__list">
        {RESOLVED_ORDER.map(([key, label]) =>
          resolved[key] ? (
            <div className="resolved__row" key={key}>
              <dt>{label}</dt>
              <dd title={resolved[key]}>{resolved[key]}</dd>
            </div>
          ) : null,
        )}
      </dl>
    </div>
  )
}
