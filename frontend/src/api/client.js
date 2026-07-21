/**
 * The one call the app makes.
 *
 * The backend already returns a user-safe `error` string on every 400, so this
 * surfaces that verbatim rather than inventing its own wording. The only message
 * written here is for the case the backend never answered at all, which it
 * cannot tell us about itself.
 */

const BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
).replace(/\/+$/, '')

export class ApiError extends Error {
  constructor(message, { status = null, details = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

export async function postTrip(inputs) {
  let response
  try {
    response = await fetch(`${BASE_URL}/api/trips/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_location: inputs.current_location.trim(),
        pickup_location: inputs.pickup_location.trim(),
        dropoff_location: inputs.dropoff_location.trim(),
        current_cycle_used: Number(inputs.current_cycle_used),
      }),
    })
  } catch (cause) {
    throw new ApiError(
      `Could not reach the server at ${BASE_URL}. Is the backend running?`,
      { cause },
    )
  }

  const body = await response.json().catch(() => null)

  if (!response.ok) {
    throw new ApiError(body?.error ?? `The server returned HTTP ${response.status}.`, {
      status: response.status,
      details: body?.details ?? null,
    })
  }

  return body
}

export { BASE_URL }
