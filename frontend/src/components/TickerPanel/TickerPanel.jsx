import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTickers } from '../../hooks/useTickers'
import { useSearchedTickers } from '../../hooks/useSearchedTickers'
import { loadTicker } from '../../api/tickers'
import { queryKeys } from '../../lib/queryClient'
import { TickerChip } from './TickerChip'
import { TickerSearch } from './TickerSearch'
import './ticker-panel.css'

/**
 * Ticker panel: loaded tickers as the Watchlist chips, plus a search box
 * that resolves and loads any real ticker from the 208-symbol universe.
 * Selecting a ticker (chip or search) is reported via `onSelectTicker` for
 * the rest of the dashboard to consume.
 *
 * Watchlist shows every ticker that has been loaded (loaded: true), so all 208
 * modelling-universe tickers are accessible as chips once loaded. Chips issue no
 * request of their own; a ticker's history and range are fetched when it is selected.
 *
 * Tickers not yet loaded are reachable via the search box, which resolves
 * against the full catalog and loads on demand.
 */
export function TickerPanel({ selectedTicker, onSelectTicker }) {
  const { data, isLoading, isError } = useTickers()
  const { searchedTickers, addSearchedTicker } = useSearchedTickers()
  const queryClient = useQueryClient()
  const [filterValue, setFilterValue] = useState('')

  const catalogTickers = data?.tickers ?? []
  // Show every ticker that has been loaded as a Watchlist chip.
  // Unloaded universe symbols are reachable via search.
  const watchlistTickers = catalogTickers.filter((entry) => entry.loaded)
  // "Known" = already loaded, i.e. selectable without a /load. A catalog
  // entry that hasn't been loaded has no chip, so search is the only way to
  // load it; counting it as known made search select it without loading.
  const knownTickers = [...watchlistTickers.map((entry) => entry.ticker), ...searchedTickers]

  // The search input live-filters BOTH groups: the Watchlist is every loaded
  // ticker (208 in the real universe), so leaving it unfiltered made the
  // input useless for finding one.
  const query = filterValue.trim().toLowerCase()
  const matchesFilter = (symbol) => !query || symbol.toLowerCase().includes(query)
  const visibleWatchlistTickers = watchlistTickers.filter((entry) => matchesFilter(entry.ticker))
  const visibleSearchedTickers = searchedTickers.filter(matchesFilter)

  // A searched-in ticker also appears in the Watchlist once /tickers
  // refetches it as loaded, so counts are over unique symbols.
  const totalSymbols = new Set([...watchlistTickers.map((entry) => entry.ticker), ...searchedTickers])
  const visibleSymbols = new Set([
    ...visibleWatchlistTickers.map((entry) => entry.ticker),
    ...visibleSearchedTickers,
  ])
  const liveRegionText = query
    ? `${visibleSymbols.size} of ${totalSymbols.size} tickers`
    : searchedTickers.length > 0
      ? `${searchedTickers.length} searched ${searchedTickers.length === 1 ? 'ticker' : 'tickers'}`
      : ''

  // Search-triggered loads target an arbitrary, not-yet-known symbol, so
  // they can't go through a ticker-scoped useLoadTicker() hook instance
  // (that hook's identity is fixed to one ticker for the whole component
  // lifetime). This mutation performs the same load + same-shape
  // invalidation directly; only reached for a genuinely new symbol
  // (TickerSearch already short-circuits known tickers to onResolveKnown).
  const searchLoadMutation = useMutation({
    mutationFn: (ticker) => loadTicker(ticker),
    onSuccess: (result, ticker) => {
      if (result.status !== 'ok') return
      addSearchedTicker(ticker)
      queryClient.invalidateQueries({ queryKey: queryKeys.tickers })
      queryClient.invalidateQueries({ queryKey: queryKeys.history(ticker) })
      queryClient.invalidateQueries({ queryKey: queryKeys.range(ticker) })
      onSelectTicker(ticker)
    },
  })

  function handleResolveKnown(ticker) {
    onSelectTicker(ticker)
  }

  return (
    <section className="ticker-panel" aria-label="Ticker selection">
      <div className="ticker-panel__header">
        <h1 className="ticker-panel__title">Stock Foresight</h1>
        <TickerSearch
          knownTickers={knownTickers}
          onResolveKnown={handleResolveKnown}
          onLoad={(ticker) => searchLoadMutation.mutateAsync(ticker)}
          isLoading={searchLoadMutation.isPending}
          onFilterChange={setFilterValue}
        />
      </div>

      {isError && (
        <p className="ticker-panel__error" role="alert">
          Couldn't load the ticker list — please refresh.
        </p>
      )}

      {/* Watchlist — every loaded ticker as a chip. Unloaded tickers
          are reachable via the search box. The chip count grows as
          more tickers are loaded across sessions. */}
      <div className="ticker-panel__chips" role="group" aria-label="Watchlist">
        {isLoading && (
          <>
            <span className="ticker-chip ticker-chip--skeleton" aria-hidden="true" />
            <span className="ticker-chip ticker-chip--skeleton" aria-hidden="true" />
            <span className="ticker-chip ticker-chip--skeleton" aria-hidden="true" />
          </>
        )}
        {visibleWatchlistTickers.map((entry) => (
          <TickerChip
            key={entry.ticker}
            ticker={entry.ticker}
            catalogEntry={entry}
            isSelected={selectedTicker === entry.ticker}
            onSelect={onSelectTicker}
          />
        ))}
        {/* Reuses the searched list's empty-state style. Only when both
            groups are empty, so a match in "Searched tickers" never gets a
            contradictory "no matches" line above it. */}
        {query && !isLoading && visibleSymbols.size === 0 && (
          <p className="ticker-panel__searched-empty">
            No loaded tickers match "{filterValue.trim()}" — press Load to fetch it.
          </p>
        )}
      </div>

      {/* Searched tickers — every symbol searched-and-loaded beyond the
          Watchlist, in a separate scrollable group (redesign-dashboard-
          visual-look Decision 4). Only rendered once there's at least one,
          so an empty session doesn't show an empty list with nothing to
          scroll. */}
      {searchedTickers.length > 0 && (
        <div className="ticker-panel__searched">
          <h2 className="ticker-panel__searched-heading">Searched tickers</h2>
          <div className="ticker-panel__searched-list" role="group" aria-label="Searched tickers">
            {visibleSearchedTickers.length > 0 ? (
              visibleSearchedTickers.map((ticker) => (
                <TickerChip
                  key={ticker}
                  ticker={ticker}
                  catalogEntry={null}
                  isSelected={selectedTicker === ticker}
                  onSelect={onSelectTicker}
                  variant="row"
                />
              ))
            ) : (
              <p className="ticker-panel__searched-empty">No searched tickers match "{filterValue.trim()}".</p>
            )}
          </div>
        </div>
      )}

      {/* Announces the filtered count to screen readers — the visible chip
          count changing as the user types would otherwise be silent. Always
          mounted (even when empty) so a polite live region exists before
          its first update, and so it covers the Watchlist when nothing has
          been searched in yet. */}
      <p className="ticker-panel__sr-only" aria-live="polite">
        {liveRegionText}
      </p>
    </section>
  )
}
