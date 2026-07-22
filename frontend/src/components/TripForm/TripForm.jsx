import { useState } from 'react'

import {
  CYCLE_LIMIT_HOURS,
  EMPTY_TRIP,
  FIELD_LABELS,
  validateTrip,
} from '../../lib/validation.js'
import './TripForm.css'

const TEXT_FIELDS = [
  {
    name: 'current_location',
    placeholder: 'Los Angeles, CA',
    hint: 'Where the driver is now. Use City, State — e.g. Los Angeles, CA.',
  },
  {
    name: 'pickup_location',
    placeholder: 'Phoenix, AZ',
    hint: 'Where the load is collected. Use City, State.',
  },
  {
    name: 'dropoff_location',
    placeholder: 'Dallas, TX',
    hint: 'Where the load is delivered. Use City, State.',
  },
]

export default function TripForm({ onSubmit, isLoading, serverError }) {
  const [values, setValues] = useState(EMPTY_TRIP)
  const [errors, setErrors] = useState({})
  const [submitted, setSubmitted] = useState(false)

  const update = (name) => (event) => {
    const next = { ...values, [name]: event.target.value }
    setValues(next)
    // Re-validate only once the driver has tried to submit, so the form does not
    // shout at them while they are still typing the first field.
    if (submitted) setErrors(validateTrip(next))
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    setSubmitted(true)
    const found = validateTrip(values)
    setErrors(found)
    if (Object.keys(found).length === 0) onSubmit(values)
  }

  const describedBy = (name) =>
    [errors[name] ? `${name}-error` : null, `${name}-hint`].filter(Boolean).join(' ')

  return (
    <form className="card trip-form" onSubmit={handleSubmit} noValidate>
      <div className="card__header">
        <h2 className="card__title">Plan a trip</h2>
        <span className="card__hint">70&nbsp;hr / 8&nbsp;day</span>
      </div>

      <div className="card__body trip-form__body">
        {TEXT_FIELDS.map(({ name, placeholder, hint }) => (
          <div className="field" key={name}>
            <label className="field__label" htmlFor={name}>
              {FIELD_LABELS[name]}
            </label>
            <input
              id={name}
              name={name}
              className="field__input"
              type="text"
              autoComplete="off"
              placeholder={placeholder}
              value={values[name]}
              onChange={update(name)}
              disabled={isLoading}
              aria-invalid={Boolean(errors[name])}
              aria-describedby={describedBy(name)}
            />
            {errors[name] ? (
              <p className="field__error" id={`${name}-error`}>
                {errors[name]}
              </p>
            ) : (
              <p className="field__hint" id={`${name}-hint`}>
                {hint}
              </p>
            )}
          </div>
        ))}

        <div className="field">
          <label className="field__label" htmlFor="current_cycle_used">
            {FIELD_LABELS.current_cycle_used}
            <span className="field__unit">hours</span>
          </label>
          <input
            id="current_cycle_used"
            name="current_cycle_used"
            className="field__input tnum"
            type="number"
            inputMode="decimal"
            min="0"
            max={CYCLE_LIMIT_HOURS}
            step="0.5"
            placeholder="0"
            value={values.current_cycle_used}
            onChange={update('current_cycle_used')}
            disabled={isLoading}
            aria-invalid={Boolean(errors.current_cycle_used)}
            aria-describedby={describedBy('current_cycle_used')}
          />
          {errors.current_cycle_used ? (
            <p className="field__error" id="current_cycle_used-error">
              {errors.current_cycle_used}
            </p>
          ) : (
            <p className="field__hint" id="current_cycle_used-hint">
              Already used in the current 8-day cycle (0–{CYCLE_LIMIT_HOURS})
            </p>
          )}
        </div>

        {serverError && (
          <div className="alert" role="alert">
            <span className="alert__mark" aria-hidden="true" />
            <div>
              <p className="alert__title">Could not plan this trip</p>
              <p className="alert__message">{serverError}</p>
            </div>
          </div>
        )}

        <button className="button" type="submit" disabled={isLoading}>
          {isLoading ? (
            <>
              <span className="spinner" aria-hidden="true" />
              Planning trip…
            </>
          ) : (
            'Plan trip'
          )}
        </button>
      </div>
    </form>
  )
}
