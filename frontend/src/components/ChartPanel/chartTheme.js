// The chart's colours, read from the design tokens in the document's computed style so they follow
// the active theme. Every token is a hex value, which lightweight-charts and canvas read as they are;
// the band fill is `#rrggbbaa`, which only the band primitive's canvas uses.
function readToken(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export function readChartTheme() {
  return {
    surface: readToken('--surface-200'),
    line: readToken('--line'),
    ink: readToken('--ink'),
    inkMuted: readToken('--ink-muted'),
    candleUp: readToken('--candle-up'),
    candleDown: readToken('--candle-down'),
    accent: readToken('--accent'),
    bandFill: readToken('--band-fill'),
  }
}
