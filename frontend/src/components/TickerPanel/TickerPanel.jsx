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
 * Ticker panel (tasks.md section 7): the 9 TRAINING_TICKERS chips, always
 * visible, plus a search box that resolves and loads any real ticker
 * (dashboard-ui spec: "Ticker panel shows the fixed set plus search for
 * any real ticker"). Selecting a ticker (chip or search) is reported via
 * `onSelectTicker` for the rest of the dashboard (chart/prediction/insight
 * panels, task 11) to consume.
 *
 * redesign-dashboard-visual-look Decision 4/5: the fixed 9 tickers render
 * as the "Watchlist" group, unchanged in behavior. Every other,
 * searched-in ticker renders in a separate "Searched tickers" group — a
 * scrollable list rather than a wrapping chip row, since this list has no
 * bound on how many entries a session can accumulate. `TickerSearch`'s
 * input live-filters this second group only (`filterValue`); the
 * Watchlist is never affected by it.
 */
export function TickerPanel({ selectedTicker, onSelectTicker }) {
  const { data, isLoading, isError } = useTickers()
  const { searchedTickers, addSearchedTicker } = useSearchedTickers()
  const queryClient = useQueryClient()
  const [filterValue, setFilterValue] = useState('')

  const catalogTickers = data?.tickers ?? []
  const knownTickers = [...catalogTickers.map((entry) => entry.ticker), ...searchedTickers]

  const visibleSearchedTickers = filterValue.trim()
    ? searchedTickers.filter((ticker) => ticker.toLowerCase().includes(filterValue.trim().toLowerCase()))
    : searchedTickers

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
      queryClient.invalidateQueries({ queryKey: queryKeys.prediction(ticker) })
      queryClient.invalidateQueries({ queryKey: queryKeys.insight(ticker) })
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

      {/* Watchlist — the fixed 9 TRAINING_TICKERS, always visible
          regardless of the search input's filter state (dashboard-ui
          spec: "Fixed Watchlist remains visible regardless of filter
          input"). */}
      <div className="ticker-panel__chips" role="group" aria-label="Watchlist">
        {isLoading && (
          <>
            <span className="ticker-chip ticker-chip--skeleton" aria-hidden="true" />
            <span className="ticker-chip ticker-chip--skeleton" aria-hidden="true" />
            <span className="ticker-chip ticker-chip--skeleton" aria-hidden="true" />
          </>
        )}
        {catalogTickers.map((entry) => (
          <TickerChip
            key={entry.ticker}
            ticker={entry.ticker}
            catalogEntry={entry}
            isSelected={selectedTicker === entry.ticker}
            onSelect={onSelectTicker}
          />
        ))}
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
          {/* Announces the filtered count to screen readers — the visible
              row count changing as the user types would otherwise be
              silent (dashboard-ui spec: "Filter narrows the searched-in
              list only"). */}
          <p className="ticker-panel__sr-only" aria-live="polite">
            {filterValue.trim()
              ? `${visibleSearchedTickers.length} of ${searchedTickers.length} tickers`
              : `${searchedTickers.length} searched ${searchedTickers.length === 1 ? 'ticker' : 'tickers'}`}
          </p>
        </div>
      )}

      {/* Freshness legend (post-ship revision) — chips show a color dot
          instead of a "Fresh"/"Stale"/"Loading" text label; this spells out
          the mapping visibly so it isn't color-only (WCAG color-not-only),
          without needing to hover every chip's dot to find out. */}
      <div className="ticker-panel__legend" aria-hidden="true">
        <span className="ticker-panel__legend-item">
          <span className="ticker-chip__dot" data-freshness="fresh" />
          Fresh
        </span>
        <span className="ticker-panel__legend-item">
          <span className="ticker-chip__dot" data-freshness="stale" />
          Stale
        </span>
        <span className="ticker-panel__legend-item">
          <span className="ticker-chip__dot ticker-panel__legend-dot--loading" />
          Loading
        </span>
      </div>
    </section>
  )
}
