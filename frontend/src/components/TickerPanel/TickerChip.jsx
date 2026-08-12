import { FRESHNESS, useTickerFreshness } from '../../hooks/useTickerFreshness'
import { describeLoadStatus, useLoadTicker } from '../../hooks/useLoadTicker'
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
 */
export function TickerChip({ ticker, catalogEntry, isSelected, onSelect }) {
  const isLoaded = catalogEntry?.loaded ?? true // searched-in tickers are loaded by construction
  const featuresFailed = catalogEntry?.features_computed === false
  const loadMutation = useLoadTicker(ticker)

  const { freshness } = useTickerFreshness(ticker, {
    enabled: isLoaded && !featuresFailed,
  })

  const effectiveFreshness = loadMutation.isPending ? FRESHNESS.LOADING : freshness
  const freshnessDescription = FRESHNESS_DESCRIPTION[effectiveFreshness]

  let statusText = null
  let statusKind = 'neutral'
  let showFreshnessDot = false
  if (loadMutation.isPending) {
    showFreshnessDot = true
  } else if (loadMutation.isError) {
    statusText =
      loadMutation.error instanceof ApiError
        ? 'Something went wrong — try again'
        : 'Network error — try again'
    statusKind = 'error'
  } else if (loadMutation.isSuccess && loadMutation.data.status !== 'ok') {
    statusText = describeLoadStatus(loadMutation.data.status, ticker)
    statusKind = 'error'
  } else if (!isLoaded) {
    statusText = 'Not loaded'
  } else if (featuresFailed) {
    statusText = 'Feature computation failed'
    statusKind = 'error'
  } else if (freshnessDescription) {
    showFreshnessDot = true
  }

  function handleClick() {
    if (!isLoaded) {
      loadMutation.mutate(undefined, {
        onSuccess: (result) => {
          if (result.status === 'ok') onSelect(ticker)
        },
      })
      return
    }
    onSelect(ticker)
  }

  return (
    <button
      type="button"
      className="ticker-chip"
      data-selected={isSelected || undefined}
      data-freshness={effectiveFreshness}
      data-status={statusKind}
      disabled={loadMutation.isPending}
      aria-pressed={isSelected}
      onClick={handleClick}
    >
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
      {statusText && <span className="ticker-chip__status">{statusText}</span>}
    </button>
  )
}
