import { describe, expect, it } from 'vitest'
import { formatBandPct } from './formatBand'

describe('formatBandPct', () => {
  it.each([
    [4.12, '±4.12%'],
    [5, '±5.00%'],
    [0.1, '±0.10%'],
    [12.345, '±12.35%'],
    [0, '±0.00%'],
  ])('writes %f as %s: the ± sign and two decimals', (value, text) => {
    expect(formatBandPct(value)).toBe(text)
  })

  it('is never signed, even for a negative input (the band has no direction)', () => {
    expect(formatBandPct(-4.12)).toBe('±4.12%')
  })

  it.each([[null], [undefined], [Number.NaN], [Infinity], ['4.12']])('has no text for %s', (value) => {
    expect(formatBandPct(value)).toBeNull()
  })
})
