import { resolveToLegacyColor } from '../../lib/color'

// lightweight-charts draws to <canvas> using its own lightweight color
// parser (hex / rgb() / rgba() / named colors) — it does NOT understand
// oklch(), which this project's design tokens (tokens.css) use. Reading a
// custom property via getComputedStyle().getPropertyValue() returns its
// literal source text, unresolved by the browser either way — so this
// converts oklch() to rgb() directly in JS (src/lib/color.js) rather than
// relying on the browser to do it. See color.js's header comment for why
// two browser-dependent approaches (computed style, canvas fillStyle
// getter) were tried and abandoned first.
function readToken(name) {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return resolveToLegacyColor(raw)
}

export function readChartTheme() {
  return {
    paper: readToken('--color-paper'),
    border: readToken('--color-border'),
    ink2: readToken('--color-ink-2'),
    ink3: readToken('--color-ink-3'),
    positive: readToken('--color-positive'),
    negative: readToken('--color-negative'),
    accent: readToken('--color-accent'),
  }
}
