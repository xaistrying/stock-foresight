import { useCallback, useState } from 'react'

/**
 * Tracks tickers that joined the selectable list via search rather than
 * being one of the 9 TRAINING_TICKERS (dashboard-ui spec: "A searched-in
 * ticker persists as a selectable entry" — for the rest of the session,
 * not persisted across reloads). Session-only, in-memory — no backend
 * concept of "searched tickers" exists; GET /tickers only ever returns
 * the fixed 9 (ticker-catalog spec).
 */
export function useSearchedTickers() {
  const [searchedTickers, setSearchedTickers] = useState([])

  const addSearchedTicker = useCallback((ticker) => {
    setSearchedTickers((current) =>
      current.includes(ticker) ? current : [...current, ticker],
    )
  }, [])

  return { searchedTickers, addSearchedTicker }
}
