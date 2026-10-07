import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { readChartTheme } from './chartTheme'

// readChartTheme() reads the design's tokens from the document's computed style, so the chart
// follows the active theme. Tokens are set directly via style.setProperty rather than by importing
// tokens.css, since Vitest does not apply imported stylesheets to jsdom's document.
const TOKENS = {
  '--surface-200': '#ffffff',
  '--line': '#d3d9e1',
  '--ink': '#12161d',
  '--ink-muted': '#4a5463',
  '--candle-up': '#0f8f5e',
  '--candle-down': '#d1334a',
  '--accent': '#1d4ed8',
  '--band-fill': '#1d4ed826',
}

beforeEach(() => {
  for (const [name, value] of Object.entries(TOKENS)) document.documentElement.style.setProperty(name, value)
})

afterEach(() => {
  for (const name of Object.keys(TOKENS)) document.documentElement.style.removeProperty(name)
})

describe('readChartTheme', () => {
  it('reads the chart ground, lines, inks, candle colours, accent and band fill from the design tokens', () => {
    expect(readChartTheme()).toEqual({
      surface: '#ffffff',
      line: '#d3d9e1',
      ink: '#12161d',
      inkMuted: '#4a5463',
      candleUp: '#0f8f5e',
      candleDown: '#d1334a',
      accent: '#1d4ed8',
      bandFill: '#1d4ed826',
    })
  })

  it('returns hex or rgb() values only, never a modern colour function the chart cannot parse', () => {
    for (const [key, value] of Object.entries(readChartTheme())) {
      expect(value, `${key} should not be an oklch() string`).not.toMatch(/oklch|color-mix|var\(/i)
      expect(value, `${key} should be hex or rgb()`).toMatch(/^(#|rgb)/)
    }
  })

  it('follows a token change, so a theme switch is picked up on the next read', () => {
    document.documentElement.style.setProperty('--accent', '#7ea6ff')

    expect(readChartTheme().accent).toBe('#7ea6ff')
  })
})
