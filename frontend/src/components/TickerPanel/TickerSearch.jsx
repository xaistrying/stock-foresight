import { useId, useState } from 'react'
import { describeLoadStatus } from '../../hooks/useLoadTicker'
import { ApiError } from '../../api/client'

/**
 * Search input resolving a typed ticker symbol (tasks.md 7.2/7.6).
 * If the symbol is already selectable (a chip or a previously
 * searched-in ticker), selects it directly with no network request
 * (dashboard-ui spec: "Searching an already-loaded ticker selects it
 * directly"). Otherwise triggers `POST /tickers/{ticker}/load` and only
 * adds it to the selectable list on `status: "ok"`.
 */
export function TickerSearch({ knownTickers, onResolveKnown, onLoad, isLoading }) {
  const inputId = useId()
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
      <label htmlFor={inputId} className="ticker-search__label">
        Search ticker
      </label>
      <div className="ticker-search__row">
        <input
          id={inputId}
          type="text"
          className="ticker-search__input"
          placeholder="e.g. VND"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          disabled={isLoading}
          autoComplete="off"
          spellCheck={false}
        />
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
