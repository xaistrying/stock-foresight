/**
 * What the dashboard knows about whether a ticker can be analysed, from the catalog entry's
 * `eligibility` (the server ran `assess_eligibility`) and, for a ticker the catalog does not list,
 * from `/range`'s `status` and `reasons` (which carry the same reasons, minus `indicators_missing`).
 * Never worked out in the browser: no age is compared with a threshold here.
 *
 * @returns {{eligible: boolean|null, reasons: string[], ageSessions: number|null}} `eligible` is null
 *   when neither source has answered yet.
 */
export function resolveEligibility(eligibility, range) {
  if (eligibility) {
    return {
      eligible: eligibility.eligible,
      reasons: eligibility.reasons ?? [],
      ageSessions: eligibility.age_sessions ?? null,
    }
  }
  if (range) return { eligible: range.status !== 'ineligible', reasons: range.reasons ?? [], ageSessions: null }
  return { eligible: null, reasons: [], ageSessions: null }
}

/**
 * Which of the Verdict panel's states to show, chosen without a request from the latest run, the
 * kept result and the ticker's eligibility, in that order:
 *
 * - none: no ticker.
 * - running: a run is pending (over everything: a kept result is not shown as if current).
 * - failed: the latest run ended in an error (a kept result stays visible beneath it).
 * - insufficient: a run abstained or refused, or the ticker cannot be analysed and no run exists.
 * - partial: a result in which an agent did not vote.
 * - result: a result.
 * - ready: the ticker can be analysed (or is not yet known not to be) and no run exists.
 *
 * @param {{ticker: string|null, run: {isPending?: boolean, error?: unknown}, result: object|null,
 *   eligibility: object|null, range: object|null}} input
 * @returns {'none'|'running'|'failed'|'insufficient'|'partial'|'result'|'ready'}
 */
export function chooseVerdictState({ ticker, run, result, eligibility, range }) {
  if (!ticker) return 'none'
  if (run.isPending) return 'running'
  if (run.error) return 'failed'
  if (result) {
    if (result.verdict === 'INSUFFICIENT_DATA') return 'insufficient'
    return (result.agents_degraded ?? []).length > 0 ? 'partial' : 'result'
  }
  return resolveEligibility(eligibility, range).eligible === false ? 'insufficient' : 'ready'
}
