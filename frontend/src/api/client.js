// Shared fetch wrapper for the backend API (FastAPI, see
// openspec/config.yaml). Base URL is configurable via
// VITE_API_BASE_URL so the dashboard can point at a non-default backend
// without a code change.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

/**
 * Error raised for any backend response the caller didn't already handle
 * via a typed status field (e.g. a network-level failure, or a non-2xx
 * response with no parseable `status`). Callers that need to distinguish
 * a `status`-classified failure (rate_limited/invalid_symbol/no_data/
 * near_gap/etc.) from this generic case should catch this type separately
 * — see design.md Decision 4 and tasks.md 6.5/7.6.
 */
export class ApiError extends Error {
  constructor(message, { status, body } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: 'application/json', ...options.headers },
      ...options,
    })
  } catch (cause) {
    throw new ApiError('Network error — could not reach the server.', { cause })
  }

  let body = null
  const text = await response.text()
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }

  if (!response.ok) {
    // Some endpoints (e.g. /prediction's near_gap, /load's rate_limited)
    // encode a meaningful outcome in the body of a non-2xx response, or in
    // a 2xx body's `status` field. Callers are responsible for checking
    // `error.body` for a `status`/`detail` field before falling back to
    // this generic message.
    throw new ApiError(body?.detail ?? `Request failed with status ${response.status}`, {
      status: response.status,
      body,
    })
  }

  return body
}

export function get(path) {
  return request(path)
}

export function post(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}
