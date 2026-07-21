import './Placeholder.css'

/**
 * A reserved slot for a section that lands in a later phase.
 *
 * Deliberately a labelled, composed empty state rather than a blank gap: the
 * layout should read as finished-with-a-slot, not as something that failed to
 * load. Each one names what will occupy it.
 */
export default function Placeholder({ title, phase, description, lines = 3 }) {
  return (
    <section className="card" aria-labelledby={`${phase}-heading`}>
      <div className="card__header">
        <h2 className="card__title" id={`${phase}-heading`}>
          {title}
        </h2>
        <span className="tag">Next up</span>
      </div>
      <div className="card__body placeholder__body">
        <div className="placeholder__art" aria-hidden="true">
          {Array.from({ length: lines }, (_, index) => (
            <span key={index} className="placeholder__bar" />
          ))}
        </div>
        <p className="placeholder__text">{description}</p>
      </div>
    </section>
  )
}
