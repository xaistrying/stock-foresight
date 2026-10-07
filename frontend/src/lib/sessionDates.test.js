import { describe, expect, it } from 'vitest'
import { approximateTargetDate, intermediateSessionDates, rangeBand } from './sessionDates'

describe('approximateTargetDate', () => {
  it('steps forward 5 weekdays, skipping a weekend in between', () => {
    // Wed 2026-07-29 -> Thu 30, Fri 31, (skip Sat 08-01, Sun 08-02), Mon 08-03,
    // Tue 08-04, Wed 08-05 = 5th weekday.
    expect(approximateTargetDate('2026-07-29')).toBe('2026-08-05')
  })

  it('skips a weekend that falls mid-span starting from a Monday', () => {
    // Mon 2026-08-03 -> Tue, Wed, Thu, Fri (4 weekdays, no weekend crossed
    // yet) -> Mon 2026-08-10 (5th weekday, skips Sat/Sun 08-08/09).
    expect(approximateTargetDate('2026-08-03')).toBe('2026-08-10')
  })
})

describe('intermediateSessionDates', () => {
  it('returns exactly the 4 weekday dates strictly between as_of and the t+5 target', () => {
    const asOf = '2026-07-29'
    const target = approximateTargetDate(asOf)
    const intermediates = intermediateSessionDates(asOf)

    expect(intermediates).toEqual(['2026-07-30', '2026-07-31', '2026-08-03', '2026-08-04'])
    expect(intermediates.every((date) => date > asOf && date < target)).toBe(true)
    // Ascending, matching lightweight-charts' strictly-ascending-time requirement.
    expect(intermediates).toEqual([...intermediates].sort())
  })

  it('never includes a weekend date', () => {
    for (const date of intermediateSessionDates('2026-08-03')) {
      const dayOfWeek = new Date(`${date}T00:00:00Z`).getUTCDay()
      expect(dayOfWeek).not.toBe(0) // Sunday
      expect(dayOfWeek).not.toBe(6) // Saturday
    }
  })
})

describe('rangeBand', () => {
  it('puts the bounds at close x (1 +/- r/100) at the t+5 date', () => {
    const band = rangeBand(11, '2026-07-29', 5)

    expect(band.time).toBe('2026-08-05')
    expect(band.upper).toBeCloseTo(11.55, 10)
    expect(band.lower).toBeCloseTo(10.45, 10)
  })

  it('is symmetric about the last close', () => {
    const band = rangeBand(23.4, '2026-08-03', 3.7)

    expect(band.upper - 23.4).toBeCloseTo(23.4 - band.lower, 10)
  })

  it('returns only the t+5 position, never a path', () => {
    expect(Object.keys(rangeBand(10, '2026-07-29', 2)).sort()).toEqual(['lower', 'time', 'upper'])
  })
})
