import { useCallback, useState } from 'react'

/**
 * Tracks the symbols that joined the Rail through the search rather than being a loaded catalog
 * entry (dashboard-ui: a searched-in ticker is an ordinary Rail row for the rest of the session).
 * Session-only and in memory: no backend concept of a searched-in ticker exists.
 *
 * Each entry carries the client clock at load success, so the Rail can say "Loaded just now" for a
 * symbol the catalog has no `last_loaded_at` for.
 * @returns {{searchedTickers: Array<{ticker: string, loadedAt: string}>, addSearchedTicker: (ticker: string) => void}}
 */
export function useSearchedTickers() {
  const [searchedTickers, setSearchedTickers] = useState([])

  const addSearchedTicker = useCallback((ticker) => {
    setSearchedTickers((current) =>
      current.some((entry) => entry.ticker === ticker)
        ? current
        : [...current, { ticker, loadedAt: new Date().toISOString() }],
    )
  }, [])

  return { searchedTickers, addSearchedTicker }
}
