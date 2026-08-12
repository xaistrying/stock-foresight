import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { readChartTheme } from './chartTheme'

// Regression test: an earlier version of readChartTheme() read
// `--color-paper` etc. via getComputedStyle().getPropertyValue(), which
// returns a custom property's literal, UNRESOLVED source text —
// "oklch(99% 0.002 260)" verbatim — not something lightweight-charts'
// color parser can read (it only understands hex/rgb/rgba/named colors,
// confirmed against the library's own docs). That bug shipped once and
// blanked the whole dashboard with "Failed to parse color: oklch(...)".
// This test locks in that every theme value comes back normalized to a
// format lightweight-charts can actually parse.
//
// Tokens are set directly via style.setProperty rather than importing
// tokens.css, since Vitest doesn't apply imported stylesheets to jsdom's
// document without `test.css: true` in vite.config.js — setting the
// custom properties directly is a more targeted way to exercise
// readChartTheme() against real oklch() values without a global test
// config change.
const TEST_TOKENS = {
  '--color-paper': 'oklch(99% 0.002 260)',
  '--color-border': 'oklch(88% 0.006 260)',
  '--color-ink-2': 'oklch(42% 0.012 260)',
  '--color-ink-3': 'oklch(58% 0.01 260)',
  '--color-positive': 'oklch(48% 0.13 155)',
  '--color-negative': 'oklch(50% 0.15 25)',
  '--color-accent': 'oklch(48% 0.13 250)',
}

beforeEach(() => {
  for (const [name, value] of Object.entries(TEST_TOKENS)) {
    document.documentElement.style.setProperty(name, value)
  }
})

afterEach(() => {
  for (const name of Object.keys(TEST_TOKENS)) {
    document.documentElement.style.removeProperty(name)
  }
})

describe('readChartTheme', () => {
  it('resolves every token to a legacy rgb()/rgba() color, never a bare oklch() string', () => {
    const theme = readChartTheme()
    for (const [key, value] of Object.entries(theme)) {
      expect(value, `${key} should not be an unresolved oklch() string`).not.toMatch(/oklch/i)
      expect(value, `${key} should resolve to a color lightweight-charts can parse`).toMatch(
        /^(rgb|rgba)\(/,
      )
    }
  })
})
