import { useRef } from 'react'
import { FRESHNESS, useTickerFreshness } from '../../hooks/useTickerFreshness'
import { describeLoadStatus, useLoadTicker, useIsTickerLoading } from '../../hooks/useLoadTicker'
import { formatLastLoadedAt } from '../../lib/relativeTime'
import { ApiError } from '../../api/client'

// Accessible name/description for each freshness state — the dot alone
// (color-not-only, WCAG) never carries the meaning by itself. Exposed via
// aria-label/title on the dot so it's reachable by screen reader and mouse
// hover alike; TickerPanel's legend spells the same mapping out visibly
// for sighted users who haven't hovered yet.
const FRESHNESS_DESCRIPTION = {
  [FRESHNESS.LOADING]: 'Loading',
  [FRESHNESS.FRESH]: 'Fresh — up to date with the latest trading session',
  [FRESHNESS.STALE]: 'Stale — a newer trading session is available',
  [FRESHNESS.UNKNOWN]: null,
}

/**
 * One selectable ticker chip (tasks.md 7.1/7.3/7.4/7.5/7.6). A not-yet-
 * loaded chip triggers `POST /tickers/{ticker}/load` on click (same flow
 * search uses) and selects the ticker once the load succeeds — clicking
 * an unloaded chip is itself the "load" action, not a separate control.
 * Shows Loading/Fresh/Stale (design.md Decision 10) as a color dot (post-
 * ship revision — the words previously sat in the status slot as visible
 * text; a legend in TickerPanel now explains the color mapping instead),
 * or a load-failure message distinct per status (Decision 4/7) as real
 * text if the load fails — those failure/not-loaded messages carry
 * information a dot can't express and are unaffected by this change.
 *
 * The chip's root is a non-interactive container with two sibling
 * interactive children (ticker-manual-refresh tasks.md 1.1): the select
 * button (symbol + freshness dot + status text, everything this
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
 */
export function TickerChip({ ticker, catalogEntry, isSelected, onSelect }) {
  const isLoaded = catalogEntry?.loaded ?? true // searched-in tickers are loaded by construction
  const featuresFailed = catalogEntry?.features_computed === false
  const loadMutation = useLoadTicker(ticker)
  const isTickerLoading = useIsTickerLoading(ticker)
  const wasRefreshRef = useRef(false)

  const { freshness } = useTickerFreshness(ticker, {
    enabled: isLoaded && !featuresFailed,
  })

  const effectiveFreshness = isTickerLoading ? FRESHNESS.LOADING : freshness
  const freshnessDescription = FRESHNESS_DESCRIPTION[effectiveFreshness]
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
  let showFreshnessDot = false
  if (isRefreshOutcome) {
    // Selection status slot stays on the ticker's steady-state (freshness
    // dot) while refresh reports its own outcome separately.
    if (freshnessDescription) showFreshnessDot = true
  } else if (loadMutation.isPending) {
    showFreshnessDot = true
  } else if (mutationOutcomeText) {
    statusText = mutationOutcomeText
    statusKind = 'error'
  } else if (!isLoaded) {
    statusText = 'Not loaded'
  } else if (featuresFailed) {
    statusText = 'Feature computation failed'
    statusKind = 'error'
  } else if (freshnessDescription) {
    showFreshnessDot = true
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
      className="ticker-chip"
      data-selected={isSelected || undefined}
      data-freshness={effectiveFreshness}
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
          {showFreshnessDot && (
            <span
              className="ticker-chip__dot"
              data-freshness={effectiveFreshness}
              role="img"
              aria-label={freshnessDescription}
              title={freshnessDescription}
            />
          )}
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
