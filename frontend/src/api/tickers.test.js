import { describe, expect, it } from 'vitest'
import { describeLoadStatus } from '../hooks/useLoadTicker'

// Smoke test for the test harness itself (Vitest + jsdom), and a first
// real check on the load-status messaging (tasks.md 6.5) — each status
// must map to its own distinct, non-null message except "ok".
describe('describeLoadStatus', () => {
  it('returns null for a successful load', () => {
    expect(describeLoadStatus('ok', 'VNM')).toBeNull()
  })

  it('returns a distinct, retry-suggesting message for rate_limited', () => {
    expect(describeLoadStatus('rate_limited', 'VNM')).toMatch(/try again/i)
  })

  it('names the symbol for invalid_symbol', () => {
    expect(describeLoadStatus('invalid_symbol', 'NOTREAL')).toContain('NOTREAL')
  })

  it('returns a non-retry-suggesting message for no_data', () => {
    expect(describeLoadStatus('no_data', 'ABC')).toMatch(/unlikely to help/i)
  })

  it('gives each status a distinct message', () => {
    const messages = ['rate_limited', 'invalid_symbol', 'no_data'].map((status) =>
      describeLoadStatus(status, 'ABC'),
    )
    expect(new Set(messages).size).toBe(messages.length)
  })
})
