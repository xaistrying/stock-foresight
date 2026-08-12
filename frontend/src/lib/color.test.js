import { describe, expect, it } from 'vitest'
import { resolveToLegacyColor } from './color'

describe('resolveToLegacyColor', () => {
  it('converts a percentage-lightness oklch() to rgb()', () => {
    expect(resolveToLegacyColor('oklch(42% 0.012 260)')).toMatch(/^rgb\(\d+, \d+, \d+\)$/)
  })

  it('converts a bare-number-lightness oklch() to rgb() identically to the percentage form', () => {
    // Regression: getComputedStyle() (and some browsers' color-serialization
    // paths) can re-serialize "42%" as "0.42" with no percent sign — this
    // exact shape ("oklch(0.42 0.012 260)") reached lightweight-charts
    // unconverted once and crashed its parser. Both forms must resolve to
    // the same color.
    const percentForm = resolveToLegacyColor('oklch(42% 0.012 260)')
    const bareForm = resolveToLegacyColor('oklch(0.42 0.012 260)')
    expect(bareForm).toBe(percentForm)
  })

  it('produces a near-white rgb for a near-white oklch input', () => {
    const result = resolveToLegacyColor('oklch(99% 0.002 260)')
    const [r, g, b] = result.match(/\d+/g).map(Number)
    expect(r).toBeGreaterThan(240)
    expect(g).toBeGreaterThan(240)
    expect(b).toBeGreaterThan(240)
  })

  it('leaves an already-legacy color string unchanged', () => {
    expect(resolveToLegacyColor('rgb(10, 20, 30)')).toBe('rgb(10, 20, 30)')
    expect(resolveToLegacyColor('#ff0000')).toBe('#ff0000')
  })
})
