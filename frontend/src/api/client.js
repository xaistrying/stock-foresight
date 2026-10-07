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
  constructor(message, { status, body, timedOut = false } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
    // True when a time limit the caller set (an AbortSignal.timeout) ended the request: the
    // server may well still be working, so this is not the same as "could not reach the server".
    this.timedOut = timedOut
  }
}

// fetch rejects with the signal's reason when it aborts: a TimeoutError for AbortSignal.timeout,
// an AbortError for a manual abort(). Only the first is a time limit.
function isTimeout(cause, signal) {
  return cause?.name === 'TimeoutError' || signal?.reason?.name === 'TimeoutError'
}

async function request(path, options = {}) {
  let response
  let text
  // The body is read inside the same guard: a time limit can strike after the headers arrived.
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { Accept: 'application/json', ...options.headers },
      ...options,
    })
    text = await response.text()
  } catch (cause) {
    if (isTimeout(cause, options.signal)) {
      throw new ApiError('The request timed out.', { timedOut: true })
    }
    throw new ApiError('Network error — could not reach the server.')
  }

  let body = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }

  if (!response.ok) {
    // Some endpoints (e.g. /range's refusing statuses, /load's rate_limited)
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

export function post(path, body, { signal } = {}) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    ...(signal ? { signal } : {}),
  })
}
