// WCAG 2 contrast of every colour pair the dashboard's design relies on, computed from the real
// stylesheet (src/styles/tokens.css), in both themes. A token edit that breaks a pair fails here.
//
//   node scripts/check-contrast.mjs          prints every ratio, exits non-zero on a failure
//
// 4.5:1 is required of text, 3:1 of non-text marks (the strong line, the candle colours, the band's
// dashed bounds, the focus ring). The candle colours are marks only: they are never a text colour.
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseTokens, themeTokens } from '../src/styles/parseTokens.js'

const TEXT = 4.5
const NON_TEXT = 3

// [foreground, background, requirement, what it is]
export const PAIRS = [
  ['ink', 'surface-100', TEXT, 'text on the page'],
  ['ink', 'surface-200', TEXT, 'text on a panel (legend values included)'],
  ['ink', 'surface-300', TEXT, 'text on an inset'],
  ['ink-muted', 'surface-100', TEXT, 'secondary text on the page'],
  ['ink-muted', 'surface-200', TEXT, 'secondary text on a panel'],
  ['ink-muted', 'surface-300', TEXT, 'secondary text on an inset'],
  ['accent', 'surface-100', TEXT, 'accent text on the page'],
  ['accent', 'surface-200', TEXT, 'accent text on a panel'],
  ['on-accent', 'accent', TEXT, 'text on a filled accent control'],
  ['up-ink', 'surface-200', TEXT, 'bullish text on a panel'],
  ['up-ink', 'up-bg', TEXT, 'bullish chip and badge'],
  ['down-ink', 'surface-200', TEXT, 'bearish text on a panel'],
  ['down-ink', 'down-bg', TEXT, 'bearish chip and badge'],
  ['warn-ink', 'warn-bg', TEXT, 'Key tension body text'],
  ['warn-line', 'warn-bg', TEXT, 'Key tension label (11px text)'],
  ['line-strong', 'surface-100', NON_TEXT, 'border of an input or chip on the page'],
  ['line-strong', 'surface-200', NON_TEXT, 'border of an input or chip on a panel'],
  ['candle-up', 'surface-200', NON_TEXT, 'rising candle and volume bar'],
  ['candle-down', 'surface-200', NON_TEXT, 'falling candle and volume bar'],
  ['accent', 'surface-200', NON_TEXT, 'range-band bounds on the chart card'],
  ['accent', 'surface-100', NON_TEXT, 'focus ring on the page'],
  ['accent', 'surface-300', NON_TEXT, 'focus ring on an inset'],
]

function channel(value) {
  const scaled = value / 255
  return scaled <= 0.03928 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4
}

function luminance(hex) {
  const match = /^#([0-9a-f]{6})(?:[0-9a-f]{2})?$/i.exec(hex)
  if (!match) throw new Error(`not a hex colour: ${hex}`)
  const [r, g, b] = [0, 2, 4].map((offset) => channel(parseInt(match[1].slice(offset, offset + 2), 16)))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrastRatio(foreground, background) {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((a, b) => b - a)
  return (lighter + 0.05) / (darker + 0.05)
}

/** One row per pair and theme: {theme, foreground, background, what, required, ratio, passes}. */
export function checkContrast(css) {
  const parsed = parseTokens(css)
  const rows = []
  for (const theme of ['light', 'dark']) {
    const tokens = themeTokens(parsed, theme)
    for (const [foreground, background, required, what] of PAIRS) {
      const ratio = contrastRatio(tokens[`--${foreground}`], tokens[`--${background}`])
      rows.push({ theme, foreground, background, what, required, ratio, passes: ratio >= required })
    }
  }
  return rows
}

export function formatRows(rows) {
  return rows
    .map((row) =>
      [
        row.passes ? 'ok  ' : 'FAIL',
        row.theme.padEnd(5),
        row.ratio.toFixed(2).padStart(5),
        `>= ${row.required}`.padEnd(6),
        `${row.foreground} on ${row.background}`.padEnd(30),
        row.what,
      ].join('  '),
    )
    .join('\n')
}

const here = dirname(fileURLToPath(import.meta.url))
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const rows = checkContrast(readFileSync(join(here, '../src/styles/tokens.css'), 'utf-8'))
  console.log(formatRows(rows))
  const text = rows.filter((row) => row.required === TEXT).map((row) => row.ratio)
  const marks = rows.filter((row) => row.required === NON_TEXT).map((row) => row.ratio)
  console.log(`\nlowest text pair ${Math.min(...text).toFixed(2)}, lowest non-text pair ${Math.min(...marks).toFixed(2)}`)
  process.exit(rows.every((row) => row.passes) ? 0 : 1)
}
