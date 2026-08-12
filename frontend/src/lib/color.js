// OKLCH -> sRGB conversion (CSS Color 4 reference formulas). Needed
// because lightweight-charts' own color parser only understands legacy
// sRGB syntax (hex / rgb() / rgba() / named colors) — it cannot parse
// oklch(), which this project's design tokens (tokens.css) use.
//
// This does the conversion directly in JS rather than relying on the
// browser to do it, after two browser-dependent approaches both failed
// in practice:
//   1. getComputedStyle(...).color on a probe element — per the CSS
//      Color 4 serialization spec, oklch()/oklab()/lch()/lab() inputs are
//      NOT coerced to rgb() the way legacy sRGB colors are; they're
//      preserved in their own function form. Confirmed via MDN before
//      shipping the second attempt.
//   2. CanvasRenderingContext2D.fillStyle's getter — expected (per the
//      HTML Canvas spec's "for compatibility reasons" normalization
//      language) to always normalize to rgb()/rgba(). In practice, the
//      browser this shipped to returned the oklch() value largely
//      unchanged (just re-serialized, e.g. "42%" -> "0.42"), which still
//      crashed lightweight-charts' parser. Spec text and real browser
//      behavior diverged; this file exists so the conversion no longer
//      depends on either.
//
// Only oklch() is handled — the one color function this project's tokens
// actually use (frontend/src/styles/tokens.css). Extend the parser if a
// token ever uses a different modern color function.

function oklchToSrgb(l, c, hDeg) {
  const h = (hDeg * Math.PI) / 180
  const a = c * Math.cos(h)
  const b = c * Math.sin(h)

  const l_ = l + 0.3963377774 * a + 0.2158037573 * b
  const m_ = l - 0.1055613458 * a - 0.0638541728 * b
  const s_ = l - 0.0894841775 * a - 1.291485548 * b

  const lCubed = l_ ** 3
  const mCubed = m_ ** 3
  const sCubed = s_ ** 3

  const rLinear = 4.0767416621 * lCubed - 3.3077115913 * mCubed + 0.2309699292 * sCubed
  const gLinear = -1.2684380046 * lCubed + 2.6097574011 * mCubed - 0.3413193965 * sCubed
  const bLinear = -0.0041960863 * lCubed - 0.7034186147 * mCubed + 1.707614701 * sCubed

  const toSrgb8 = (channel) => {
    const clamped = Math.max(0, Math.min(1, channel))
    const gammaCorrected =
      clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * clamped ** (1 / 2.4) - 0.055
    return Math.round(Math.max(0, Math.min(1, gammaCorrected)) * 255)
  }

  return [toSrgb8(rLinear), toSrgb8(gLinear), toSrgb8(bLinear)]
}

// Lightness may be written as a percentage ("42%") or, as browsers
// re-serialize it in getComputedStyle, a bare 0-1 number ("0.42") — both
// forms have shipped from the same token in practice, so both are parsed.
const OKLCH_PATTERN = /^oklch\(\s*([\d.]+)(%)?\s+([\d.]+)\s+([\d.]+)\s*\)$/i

/**
 * Converts any oklch() color string to a legacy rgb() string that
 * lightweight-charts (and any other legacy-sRGB-only color parser) can
 * read. Non-oklch input passes through unchanged.
 * @param {string} cssColor
 * @returns {string}
 */
export function resolveToLegacyColor(cssColor) {
  const trimmed = cssColor.trim()
  const match = OKLCH_PATTERN.exec(trimmed)
  if (!match) return trimmed

  const [, lightness, percentSign, chroma, hue] = match
  const l = percentSign ? Number(lightness) / 100 : Number(lightness)
  const [r, g, b] = oklchToSrgb(l, Number(chroma), Number(hue))
  return `rgb(${r}, ${g}, ${b})`
}
