/**
 * The typical 5-session move as the dashboard writes it: the ± sign and two decimals, never signed
 * (Rule 1: five sessions; Rule 2: a simple percentage, never a log return). One formatter, used by
 * the chart's band label and by the Verdict panel's figure, so the two cannot disagree.
 * @param {unknown} rangePct `range_5s_pct`, the band's half-width in percent
 * @returns {string|null} e.g. "±4.12%", or null when there is no number to show
 */
export function formatBandPct(rangePct) {
  if (typeof rangePct !== 'number' || !Number.isFinite(rangePct)) return null
  return `±${Math.abs(rangePct).toFixed(2)}%`
}
