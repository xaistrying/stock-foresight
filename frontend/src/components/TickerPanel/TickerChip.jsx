import { useEffect, useRef } from 'react'
import { describeLoadStatus, useLoadTicker, useIsTickerLoading } from '../../hooks/useLoadTicker'
import { formatLastLoadedAt } from '../../lib/relativeTime'
import { ApiError } from '../../api/client'

/**
 * One selectable ticker chip (tasks.md 7.1/7.3/7.4/7.5/7.6). A not-yet-
 * loaded chip triggers `POST /tickers/{ticker}/load` on click (same flow
 * search uses) and selects the ticker once the load succeeds — clicking
 * an unloaded chip is itself the "load" action, not a separate control.
 * Shows "Loaded Nd ago" in the footer, or a load-failure message distinct
 * per status (Decision 4/7) as real text if the load fails. A chip issues
 * no query of its own: the page load is one request (`GET /tickers`), and
 * a ticker's history and range are fetched only once it is selected.
 *
 * The chip's root is a non-interactive container with two sibling
 * interactive children (ticker-manual-refresh tasks.md 1.1): the select
 * button (symbol + status text, everything this
 * component already did) and a Refresh button, shown only when the
 * ticker is already loaded. A `<button>` cannot nest another `<button>`
 * (invalid HTML, breaks keyboard/screen-reader semantics — design.md
 * Risk 2 of that change), so the two now live side by side instead.
 *
 * Both buttons share a single `useLoadTicker(ticker)` mutation instance
 * (design.md Decision 2) — there is exactly one `/load` call site per
 * chip, just two triggers for it. `wasRefreshRef` records which trigger
 * started the mutation currently reflected by `loadMutation`, purely to
 * decide *where* to render the outcome message (select's status slot vs.
 * refresh's) — it does not affect request behavior.
 *
 * `variant` (redesign-dashboard-visual-look Decision 4) switches only the
 * CSS layout — 'chip' (default) is the bordered card used for the fixed
 * Watchlist; 'row' is a full-width, borderless list row used for the
 * scrollable "Searched tickers" list, which needs to read as a list once
 * a session accumulates many entries, not a wrapping wall of cards. All
 * markup, ARIA, and behavior are identical between the two variants.
 */
export function TickerChip({ ticker, catalogEntry, isSelected, onSelect, variant = 'chip' }) {
  const isLoaded = catalogEntry?.loaded ?? true // searched-in tickers are loaded by construction
  const featuresFailed = catalogEntry?.features_computed === false
  const loadMutation = useLoadTicker(ticker)
  const isTickerLoading = useIsTickerLoading(ticker)
  const wasRefreshRef = useRef(false)
  const rootRef = useRef(null)

  // The Watchlist is a fixed-height scroll region, so a ticker selected
  // from elsewhere (search) can sit in an out-of-view row. 'nearest' makes
  // this a no-op when the chip is already visible (the normal click case).
  // Watchlist chips only: a searched-in ticker also has a row in the
  // Searched list, and scrollIntoView would scroll the page for that
  // duplicate too. Optional call: jsdom has no scrollIntoView.
  useEffect(() => {
    if (isSelected && variant === 'chip') rootRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [isSelected, variant])

  const lastLoadedText = formatLastLoadedAt(catalogEntry?.last_loaded_at)

  const mutationOutcomeText = (() => {
    if (loadMutation.isError) {
      return loadMutation.error instanceof ApiError
        ? 'Something went wrong — try again'
        : 'Network error — try again'
    }
    if (loadMutation.isSuccess && loadMutation.data.status !== 'ok') {
      return describeLoadStatus(loadMutation.data.status, ticker)
    }
    return null
  })()

  // Refresh's own outcome renders in the refresh group, not the select
  // button's status slot (tasks.md 3.3) — the two buttons are siblings
  // now and must not render two competing status messages for the same
  // chip at once.
  const isRefreshOutcome = wasRefreshRef.current && mutationOutcomeText
  const refreshStatusText = isRefreshOutcome ? mutationOutcomeText : null

  let statusText = null
  let statusKind = 'neutral'
  // While refresh reports its own outcome, or a load is in flight, the select button's status
  // slot stays on the steady-state footer.
  if (isRefreshOutcome || loadMutation.isPending) {
    // no status text
  } else if (mutationOutcomeText) {
    statusText = mutationOutcomeText
    statusKind = 'error'
  } else if (!isLoaded) {
    statusText = 'Not loaded'
  } else if (featuresFailed) {
    statusText = 'Feature computation failed'
    statusKind = 'error'
  }

  function handleSelectClick() {
    if (!isLoaded) {
      wasRefreshRef.current = false
      loadMutation.mutate(undefined, {
        onSuccess: (result) => {
          if (result.status === 'ok') onSelect(ticker)
        },
      })
      return
    }
    onSelect(ticker)
  }

  function handleRefreshClick() {
    // No onSelect here (ticker-manual-refresh tasks.md 2.2) — refreshing
    // an already-loaded ticker must not change which ticker is selected.
    wasRefreshRef.current = true
    loadMutation.mutate()
  }

  // A single footer line below the symbol row carries whichever message
  // applies, in precedence order: refresh's own outcome (tasks.md 3.3) >
  // the select button's own status text (mutation error, "Feature
  // computation failed") > last-loaded-at > nothing. Only one message
  // ever renders per card, keeping card height constant across states.
  const footerText = refreshStatusText ?? statusText ?? lastLoadedText
  const footerKind = refreshStatusText ? 'error' : statusText ? statusKind : 'neutral'

  return (
    <div
      ref={rootRef}
      className="ticker-chip"
      data-variant={variant}
      data-selected={isSelected || undefined}
      data-status={statusKind}
    >
      <button
        type="button"
        className="ticker-chip__select"
        disabled={loadMutation.isPending}
        aria-pressed={isSelected}
        onClick={handleSelectClick}
      >
        <span className="ticker-chip__top">
          <span className="ticker-chip__symbol">{ticker}</span>
        </span>
        {footerText && (
          <span
            className="ticker-chip__footer"
            data-status={footerKind}
            title={footerKind === 'neutral' ? catalogEntry?.last_loaded_at : undefined}
          >
            {footerText}
          </span>
        )}
      </button>
      {isLoaded && (
        <button
          type="button"
          className="ticker-chip__refresh"
          disabled={isTickerLoading}
          data-loading={isTickerLoading || undefined}
          onClick={handleRefreshClick}
          aria-label={`Refresh ${ticker}`}
          title={`Refresh ${ticker}`}
        >
          <svg
            className="ticker-chip__refresh-icon"
            width="13"
            height="13"
            viewBox="0 0 16 16"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M2 8a6 6 0 1 1 1.76 4.24M2 8V4m0 4h4"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      )}
    </div>
  )
}
