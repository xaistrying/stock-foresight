import { describe, expect, it } from 'vitest'
import { buildRailRows, reasonLabels, REASON_TAGS } from './railRows'

const entry = (ticker, overrides = {}) => ({
  ticker,
  loaded: true,
  last_loaded_at: '2026-10-01T00:00:00Z',
  eligibility: { eligible: true, reasons: [], as_of: '2026-10-06', age_sessions: 0 },
  ...overrides,
})
const symbols = (rows) => rows.map((row) => row.ticker)

describe('buildRailRows', () => {
  it('lists loaded catalog entries only, as {ticker, loadedAt, eligibility}', () => {
    const rows = buildRailRows({ catalog: [entry('TCB'), entry('VIB', { loaded: false })] })

    expect(rows).toEqual([
      { ticker: 'TCB', loadedAt: '2026-10-01T00:00:00Z', eligibility: entry('TCB').eligibility },
    ])
  })

  it('adds searched-in symbols the catalog does not list, with their client load time and no eligibility', () => {
    const rows = buildRailRows({
      catalog: [entry('TCB')],
      searched: [{ ticker: 'FPT', loadedAt: '2026-10-07T01:00:00.000Z' }],
    })

    expect(rows.find((row) => row.ticker === 'FPT')).toEqual({
      ticker: 'FPT',
      loadedAt: '2026-10-07T01:00:00.000Z',
      eligibility: null,
    })
  })

  it('keeps the catalog row when a searched-in symbol is now in the catalog', () => {
    const rows = buildRailRows({
      catalog: [entry('TCB')],
      searched: [{ ticker: 'TCB', loadedAt: '2026-10-07T01:00:00.000Z' }],
    })

    expect(rows).toHaveLength(1)
    expect(rows[0].loadedAt).toBe('2026-10-01T00:00:00Z')
  })

  it('treats an entry without eligibility (an older backend) as unknown', () => {
    const { eligibility, ...withoutEligibility } = entry('TCB')
    void eligibility

    expect(buildRailRows({ catalog: [withoutEligibility] })[0].eligibility).toBeNull()
  })

  it('sorts by symbol, A to Z, by default and whatever the catalog order', () => {
    const catalog = [entry('VIB'), entry('ACB'), entry('TCB')]

    expect(symbols(buildRailRows({ catalog }))).toEqual(['ACB', 'TCB', 'VIB'])
  })

  it('sorts by last load, newest first, no load time last, ties by symbol', () => {
    const catalog = [
      entry('AAA', { last_loaded_at: '2026-09-01T00:00:00Z' }),
      entry('BBB', { last_loaded_at: '2026-10-05T00:00:00Z' }),
      entry('CCC', { last_loaded_at: null }),
      entry('DDD', { last_loaded_at: '2026-10-05T00:00:00Z' }),
      entry('EEE', { last_loaded_at: 'not a date' }),
    ]

    expect(symbols(buildRailRows({ catalog, sort: 'loaded' }))).toEqual(['BBB', 'DDD', 'AAA', 'CCC', 'EEE'])
  })

  it('places a searched-in symbol by its client load time', () => {
    const rows = buildRailRows({
      catalog: [entry('AAA', { last_loaded_at: '2026-10-05T00:00:00Z' })],
      searched: [{ ticker: 'ZZZ', loadedAt: '2026-10-07T00:00:00Z' }],
      sort: 'loaded',
    })

    expect(symbols(rows)).toEqual(['ZZZ', 'AAA'])
  })

  it('filters by symbol, as a case-insensitive substring, ignoring surrounding spaces', () => {
    const catalog = [entry('CBB'), entry('ACB'), entry('VIB')]

    expect(symbols(buildRailRows({ catalog, query: ' cb ' }))).toEqual(['ACB', 'CBB'])
    expect(symbols(buildRailRows({ catalog, query: '' }))).toEqual(['ACB', 'CBB', 'VIB'])
  })

  it('does not change its inputs', () => {
    const catalog = [entry('VIB'), entry('ACB')]
    const frozen = JSON.stringify(catalog)

    buildRailRows({ catalog, sort: 'loaded', query: 'a' })

    expect(JSON.stringify(catalog)).toBe(frozen)
  })
})

describe('reasonLabels', () => {
  it('names the six reasons in the server order, in short text', () => {
    expect(REASON_TAGS).toEqual({
      delisted: 'Delisted',
      insufficient_history: 'Short history',
      stale: 'Stale',
      near_gap: 'Data gaps',
      hard_quality_flag: 'Quality flag',
      indicators_missing: 'No indicators',
    })
  })

  it('returns every reason of an ineligible ticker, in the order given', () => {
    expect(reasonLabels({ eligible: false, reasons: ['delisted', 'stale'] })).toEqual(['Delisted', 'Stale'])
  })

  it('returns nothing for an eligible ticker, an unknown one or an older backend', () => {
    expect(reasonLabels({ eligible: true, reasons: [] })).toEqual([])
    expect(reasonLabels(null)).toEqual([])
    expect(reasonLabels(undefined)).toEqual([])
  })

  it('passes an unrecognised reason through rather than hiding it', () => {
    expect(reasonLabels({ eligible: false, reasons: ['something_new'] })).toEqual(['something_new'])
  })
})
