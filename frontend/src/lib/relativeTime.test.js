import { describe, expect, it } from 'vitest'
import { formatLastLoadedAt } from './relativeTime'

const NOW = new Date('2026-08-12T12:00:00Z').getTime()

describe('formatLastLoadedAt', () => {
  it('returns null for a null timestamp (never loaded)', () => {
    expect(formatLastLoadedAt(null, NOW)).toBeNull()
  })

  it('returns null for an undefined timestamp', () => {
    expect(formatLastLoadedAt(undefined, NOW)).toBeNull()
  })

  it('renders "just now" for a timestamp under a minute old', () => {
    const isoTimestamp = new Date(NOW - 30 * 1000).toISOString()
    expect(formatLastLoadedAt(isoTimestamp, NOW)).toBe('Loaded just now')
  })

  it('renders whole minutes for a timestamp under an hour old', () => {
    const isoTimestamp = new Date(NOW - 5 * 60 * 1000).toISOString()
    expect(formatLastLoadedAt(isoTimestamp, NOW)).toBe('Loaded 5m ago')
  })

  it('renders whole hours for a timestamp under a day old', () => {
    const isoTimestamp = new Date(NOW - 3 * 60 * 60 * 1000).toISOString()
    expect(formatLastLoadedAt(isoTimestamp, NOW)).toBe('Loaded 3h ago')
  })

  it('renders whole days for a multi-day-old timestamp', () => {
    const isoTimestamp = new Date(NOW - 14 * 24 * 60 * 60 * 1000).toISOString()
    expect(formatLastLoadedAt(isoTimestamp, NOW)).toBe('Loaded 14d ago')
  })

  it('renders 1 day for exactly one day old', () => {
    const isoTimestamp = new Date(NOW - 24 * 60 * 60 * 1000).toISOString()
    expect(formatLastLoadedAt(isoTimestamp, NOW)).toBe('Loaded 1d ago')
  })

  it('treats a future timestamp as just now rather than going negative', () => {
    const isoTimestamp = new Date(NOW + 5000).toISOString()
    expect(formatLastLoadedAt(isoTimestamp, NOW)).toBe('Loaded just now')
  })
})
