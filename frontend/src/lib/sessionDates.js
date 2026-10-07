// Session-date helpers for the chart's t+5 range band. Dates are an approximation of trading
// sessions (weekdays); the band's bounds come from the backend's range, never from here.

/**
 * Steps forward from `asOfDate` by `count` WEEKDAYS (Mon-Fri), skipping
 * Saturday/Sunday — an approximation of trading sessions. It does not know
 * Vietnamese market holidays, so it can occasionally land a day or two off
 * a real session, but it's much closer than a flat calendar-day offset.
 * @param {string} asOfDate - YYYY-MM-DD
 * @param {number} count - number of weekdays to step forward (>= 1)
 * @returns {string} YYYY-MM-DD
 */
function addWeekdays(asOfDate, count) {
  const date = new Date(`${asOfDate}T00:00:00Z`)
  let remaining = count
  while (remaining > 0) {
    date.setUTCDate(date.getUTCDate() + 1)
    const dayOfWeek = date.getUTCDay() // 0 = Sunday, 6 = Saturday
    if (dayOfWeek !== 0 && dayOfWeek !== 6) {
      remaining -= 1
    }
  }
  return date.toISOString().slice(0, 10)
}

/**
 * Approximate calendar date for the chart's t+5 band (Rule 1: the horizon
 * is 5 TRADING sessions ahead, not calendar days — but
 * `GET /tickers/{ticker}/range` only returns `as_of`, the date the range
 * was computed *from*, never a target date). `/history` has no future rows
 * to count real sessions against, so this steps forward 5 weekdays from
 * `as_of` as a visual stand-in for 5 trading sessions — an approximation
 * of the x-axis position only (it doesn't know Vietnamese market holidays).
 * It does not affect the band's bounds, only where the band is drawn.
 * @param {string} asOfDate - YYYY-MM-DD
 * @returns {string} YYYY-MM-DD, 5 weekdays after asOfDate
 */
export function approximateTargetDate(asOfDate) {
  return addWeekdays(asOfDate, 5)
}

/**
 * The 4 intermediate trading-session dates (t+1..t+4) between `asOfDate`
 * and the t+5 band, ascending. Used only to reserve x-axis width on the
 * chart via lightweight-charts' whitespace-data mechanism (a `{time}`
 * point with no `value`) — never given a plotted value or drawn on, since
 * the range describes one position (t+5), not a path.
 * @param {string} asOfDate - YYYY-MM-DD
 * @returns {string[]} 4 YYYY-MM-DD dates, ascending, all before the t+5 date
 */
export function intermediateSessionDates(asOfDate) {
  return [1, 2, 3, 4].map((n) => addWeekdays(asOfDate, n))
}

/**
 * The range band at the t+5 position: bounds `close x (1 +/- r/100)`, symmetric about the last
 * close. One position, never a path, and no direction.
 * @param {number} lastClose - the most recent historical close
 * @param {string} asOfDate - YYYY-MM-DD, `as_of` of the range
 * @param {number} rangePct - `range_5s_pct`, the half-width in percent
 * @returns {{time: string, upper: number, lower: number}}
 */
export function rangeBand(lastClose, asOfDate, rangePct) {
  const halfWidth = rangePct / 100
  return {
    time: approximateTargetDate(asOfDate),
    upper: lastClose * (1 + halfWidth),
    lower: lastClose * (1 - halfWidth),
  }
}
