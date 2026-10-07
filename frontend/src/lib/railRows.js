// Pure construction of the Rail's rows: which tickers the Rail lists, in what order, and which of
// them the topbar search keeps. The Rail and the search both build their rows from here, so what
// the user sees and what Enter can select are the same list.

/** Why a ticker cannot be analysed, as the short text a Rail row shows (design.md Decision 3). */
export const REASON_TAGS = {
  delisted: 'Delisted',
  insufficient_history: 'Short history',
  stale: 'Stale',
  near_gap: 'Data gaps',
  hard_quality_flag: 'Quality flag',
  indicators_missing: 'No indicators',
}

/**
 * Every reason an eligibility summary gives, as text, in the server's order. Empty for an eligible
 * ticker and for one with no summary (an unloaded entry, or an older backend): the dashboard never
 * works a reason out for itself, so no summary means no tag.
 */
export function reasonLabels(eligibility) {
  return (eligibility?.reasons ?? []).map((reason) => REASON_TAGS[reason] ?? reason)
}

// Milliseconds since the epoch, or null when there is no usable time.
function loadedTime(row) {
  const time = row.loadedAt ? Date.parse(row.loadedAt) : NaN
  return Number.isNaN(time) ? null : time
}

const bySymbol = (a, b) => (a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : 0)

function byLastLoaded(a, b) {
  const timeA = loadedTime(a)
  const timeB = loadedTime(b)
  if (timeA === timeB) return bySymbol(a, b)
  if (timeA === null) return 1
  if (timeB === null) return -1
  return timeB - timeA
}

/**
 * @param {{
 *   catalog?: Array<{ticker: string, loaded: boolean, last_loaded_at?: string|null, eligibility?: object|null}>,
 *   searched?: Array<{ticker: string, loadedAt: string}>,
 *   sort?: 'symbol'|'loaded',
 *   query?: string,
 * }} input
 * @returns {Array<{ticker: string, loadedAt: string|null, eligibility: object|null}>}
 */
export function buildRailRows({ catalog = [], searched = [], sort = 'symbol', query = '' }) {
  const rows = new Map()
  for (const entry of catalog) {
    if (!entry.loaded) continue
    rows.set(entry.ticker, {
      ticker: entry.ticker,
      loadedAt: entry.last_loaded_at ?? null,
      eligibility: entry.eligibility ?? null,
    })
  }
  // A symbol loaded through the search that the catalog does not (yet) list. Once the refetched
  // catalog lists it, the catalog's row wins.
  for (const { ticker, loadedAt } of searched) {
    if (!rows.has(ticker)) rows.set(ticker, { ticker, loadedAt, eligibility: null })
  }

  const needle = query.trim().toLowerCase()
  return [...rows.values()]
    .filter((row) => !needle || row.ticker.toLowerCase().includes(needle))
    .sort(sort === 'loaded' ? byLastLoaded : bySymbol)
}
