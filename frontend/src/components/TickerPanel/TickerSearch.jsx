import { useState } from 'react'
import { MagnifyingGlass } from '@phosphor-icons/react'
import { describeLoadStatus } from '../../hooks/useLoadTicker'
import { ApiError } from '../../api/client'

/**
 * Search input resolving a typed ticker symbol (tasks.md 7.2/7.6).
 * If the symbol is already selectable (a chip or a previously
 * searched-in ticker), selects it directly with no network request
 * (dashboard-ui spec: "Searching an already-loaded ticker selects it
 * directly"). Otherwise triggers `POST /tickers/{ticker}/load` and only
 * adds it to the selectable list on `status: "ok"`.
 *
 * `onFilterChange` (redesign-dashboard-visual-look Decision 5) fires on
 * every keystroke, in addition to this component's own submit-to-load
 * behavior — the same input drives both a live filter of TickerPanel's
 * "Searched tickers" list and, on submit, the existing resolve-or-load
 * flow. It has no effect on the fixed Watchlist.
 */
export function TickerSearch({ knownTickers, onResolveKnown, onLoad, isLoading, onFilterChange }) {
  const [value, setValue] = useState('')
  const [feedback, setFeedback] = useState(null) // { kind: 'error'|'info', text }

  async function handleSubmit(event) {
    event.preventDefault()
    const symbol = value.trim().toUpperCase()
    if (!symbol) return

    if (knownTickers.includes(symbol)) {
      setFeedback(null)
      onResolveKnown(symbol)
      return
    }

    setFeedback(null)
    try {
      const result = await onLoad(symbol)
      if (result.status === 'ok') {
        setValue('')
        onFilterChange?.('')
        setFeedback(null)
      } else {
        // Distinct message per status (design.md Decision 4/7) — never
        // collapsed into one generic "load failed" line.
        setFeedback({ kind: 'error', text: describeLoadStatus(result.status, symbol) })
      }
    } catch (error) {
      // Non-2xx / network-level failure below the status-classification
      // layer (tasks.md 7.6) — kept visibly distinct from the four named
      // statuses above, not merged into the same message.
      const text =
        error instanceof ApiError
          ? 'Something went wrong loading this ticker — please try again.'
          : 'Network error — could not reach the server.'
      setFeedback({ kind: 'error', text })
    }
  }

  return (
    <form className="ticker-search" onSubmit={handleSubmit} role="search">
      <div className="ticker-search__row">
        <div className="ticker-search__input-wrap">
          <MagnifyingGlass className="ticker-search__icon" size={16} weight="regular" aria-hidden="true" />
          <input
            type="text"
            className="ticker-search__input"
            aria-label="Search ticker"
            placeholder="Search ticker"
            value={value}
            onChange={(event) => {
              const nextValue = event.target.value.toUpperCase()
              setValue(nextValue)
              onFilterChange?.(nextValue)
            }}
            disabled={isLoading}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        <button type="submit" className="ticker-search__button" disabled={isLoading || !value.trim()}>
          {isLoading ? (
            <>
              <span className="ticker-chip__spinner" aria-hidden="true" />
              Loading…
            </>
          ) : (
            'Load'
          )}
        </button>
      </div>
      {feedback && (
        <p className="ticker-search__feedback" data-kind={feedback.kind} role="alert">
          {feedback.text}
        </p>
      )}
    </form>
  )
}
