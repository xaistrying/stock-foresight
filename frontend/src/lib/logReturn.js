// Rule 2 (CLAUDE.md / openspec/config.yaml): the raw predicted_log_return
// value must never reach any render path unconverted. This is the single
// shared conversion, reused by the prediction display (task 9) and the
// chart panel's single predicted point (task 8.3) — see tasks.md 9.2.

/**
 * Converts a log return to a simple percentage move: `(e^x - 1) * 100`.
 * @param {number} logReturn
 * @returns {number} percentage, e.g. 2.3 for a +2.3% move
 */
export function logReturnToPercent(logReturn) {
  return (Math.exp(logReturn) - 1) * 100
}

/**
 * Converts a log return to an absolute predicted price, given the
 * reference (most recent) close: `close * e^x`.
 * @param {number} logReturn
 * @param {number} referenceClose
 * @returns {number} predicted price
 */
export function logReturnToPrice(logReturn, referenceClose) {
  return referenceClose * Math.exp(logReturn)
}

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
 * Approximate calendar date for the chart's t+5 predicted point (Rule 1:
 * the target is 5 TRADING sessions ahead, not calendar days — but
 * `GET /tickers/{ticker}/prediction` only returns `as_of`, the date the
 * prediction was made *from*, never a target date). `/history` has no
 * future rows to count real sessions against, so this steps forward 5
 * weekdays from `as_of` as a visual stand-in for 5 trading sessions — an
 * approximation of the x-axis position only (it doesn't know Vietnamese
 * market holidays). It does not affect the predicted value itself (Rule
 * 2's percentage conversion), only where the point is drawn.
 * @param {string} asOfDate - YYYY-MM-DD
 * @returns {string} YYYY-MM-DD, 5 weekdays after asOfDate
 */
export function approximateTargetDate(asOfDate) {
  return addWeekdays(asOfDate, 5)
}

/**
 * The 4 intermediate trading-session dates (t+1..t+4) between `asOfDate`
 * and the t+5 predicted point, ascending. Used only to reserve x-axis
 * width on the chart via lightweight-charts' whitespace-data mechanism
 * (a `{time}` point with no `value`) — never given a plotted value or
 * connected by a line, since the model produces exactly one scalar and
 * Decision 8 (design.md) forbids implying intermediate predicted values.
 * @param {string} asOfDate - YYYY-MM-DD
 * @returns {string[]} 4 YYYY-MM-DD dates, ascending, all before the t+5 date
 */
export function intermediateSessionDates(asOfDate) {
  return [1, 2, 3, 4].map((n) => addWeekdays(asOfDate, n))
}
