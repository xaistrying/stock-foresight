import { describe, expect, it } from 'vitest'
import {
  approximateTargetDate,
  intermediateSessionDates,
  logReturnToPercent,
  logReturnToPrice,
} from './logReturn'

describe('logReturnToPercent', () => {
  it('converts a zero log return to 0%', () => {
    expect(logReturnToPercent(0)).toBeCloseTo(0, 10)
  })

  it('converts a positive log return to a positive percentage', () => {
    // ln(1.023) ~= 0.02274 -> back to +2.3%
    expect(logReturnToPercent(Math.log(1.023))).toBeCloseTo(2.3, 5)
  })

  it('converts a negative log return to a negative percentage', () => {
    expect(logReturnToPercent(Math.log(0.989))).toBeCloseTo(-1.1, 5)
  })
})

describe('logReturnToPrice', () => {
  it('returns the reference close unchanged for a zero log return', () => {
    expect(logReturnToPrice(0, 100)).toBeCloseTo(100, 10)
  })

  it('scales the reference close by e^x', () => {
    expect(logReturnToPrice(Math.log(1.05), 100)).toBeCloseTo(105, 5)
  })
})

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
