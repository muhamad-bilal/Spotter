/**
 * Client-side validation, mirroring the server rules exactly.
 *
 * These are the same three checks `TripRequestSerializer` applies: no blank
 * fields, cycle hours within 0-70, and a pickup that differs from the dropoff.
 * Catching them here saves a round trip; the server still enforces all of them,
 * and its message wins if the two ever disagree.
 */

export const CYCLE_LIMIT_HOURS = 70

export const EMPTY_TRIP = {
  current_location: '',
  pickup_location: '',
  dropoff_location: '',
  current_cycle_used: '',
}

export const FIELD_LABELS = {
  current_location: 'Current location',
  pickup_location: 'Pickup location',
  dropoff_location: 'Dropoff location',
  current_cycle_used: 'Cycle hours used',
}

const normalise = (value) => value.trim().toLowerCase()

export function validateTrip(values) {
  const errors = {}

  for (const field of ['current_location', 'pickup_location', 'dropoff_location']) {
    if (!values[field].trim()) {
      errors[field] = `${FIELD_LABELS[field]} is required.`
    }
  }

  const raw = String(values.current_cycle_used).trim()
  if (!raw) {
    errors.current_cycle_used = 'Enter how many cycle hours have been used (0 if fresh).'
  } else {
    const hours = Number(raw)
    if (!Number.isFinite(hours)) {
      errors.current_cycle_used = 'Cycle hours must be a number.'
    } else if (hours < 0) {
      errors.current_cycle_used = 'Cycle hours used cannot be negative.'
    } else if (hours > CYCLE_LIMIT_HOURS) {
      errors.current_cycle_used =
        `Cycle hours used cannot exceed ${CYCLE_LIMIT_HOURS} — that is the whole ` +
        `8-day limit, leaving no hours to drive.`
    }
  }

  if (
    !errors.pickup_location &&
    !errors.dropoff_location &&
    normalise(values.pickup_location) === normalise(values.dropoff_location)
  ) {
    errors.dropoff_location = 'Pickup and dropoff must be different locations.'
  }

  return errors
}
