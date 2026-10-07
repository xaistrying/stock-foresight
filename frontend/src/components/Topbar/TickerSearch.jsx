import { useEffect, useId, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { loadTicker } from '../../api/tickers'
import { ApiError } from '../../api/client'
import { describeLoadStatus, invalidateAfterLoad } from '../../hooks/useLoadTicker'
import { formatLastLoadedAt } from '../../lib/relativeTime'
import { reasonLabels } from '../../lib/railRows'
import './ticker-search.css'

const MAX_SYMBOL_LENGTH = 12

function failureText(error) {
  return error instanceof ApiError
    ? 'Something went wrong loading this ticker — please try again.'
    : 'Network error — could not reach the server.'
}

/**
 * The one ticker search, in the topbar. It filters the Rail by symbol as you type (the text lives
 * in the app, which hands it to the Rail). Enter on a symbol that is in the Rail selects it with no
 * request; Enter on any other symbol loads it first, then selects it. There is no Load button.
 *
 * Below 768px there is no Rail, so the input is a combobox listing the matches (and, for a symbol
 * with no match, one "Load SYM" option). At every other width it is a plain input and opens no popup.
 *
 * @param {{
 *   rows: Array<{ticker: string, loadedAt: string|null, eligibility: object|null}>,
 *   value: string,
 *   onValueChange: (value: string) => void,
 *   onSelectTicker: (ticker: string) => void,
 *   onLoaded: (ticker: string) => void,
 *   layoutMode: 'wide'|'collapsed'|'drawer'|'phone',
 * }} props
 */
export function TickerSearch({ rows, value, onValueChange, onSelectTicker, onLoaded, layoutMode }) {
  const queryClient = useQueryClient()
  const inputRef = useRef(null)
  const listboxId = useId()
  const [failure, setFailure] = useState(null)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [dismissed, setDismissed] = useState(false)

  // The symbol being searched is arbitrary, so this cannot be a ticker-scoped useLoadTicker; it does
  // the same load and the same invalidation (what a completed load refreshes is shared).
  const loadMutation = useMutation({
    mutationFn: (ticker) => loadTicker(ticker),
    onSuccess: (result, ticker) => {
      if (result.status === 'ok') invalidateAfterLoad(queryClient, ticker)
    },
  })

  const isPhone = layoutMode === 'phone'
  const symbol = value.trim().toUpperCase()
  const matches = symbol ? rows.filter((row) => row.ticker.includes(symbol)) : []
  const options = matches.length > 0 ? matches.map((row) => ({ kind: 'match', row })) : [{ kind: 'load' }]
  const isOpen = isPhone && Boolean(symbol) && !dismissed
  const optionId = (index) => `${listboxId}-option-${index}`

  // The input is disabled while a load runs, and a browser drops focus from a disabled element. When
  // the load settles, focus returns to it: to correct a failed symbol, or to carry on after a success.
  const wasPending = useRef(false)
  useEffect(() => {
    if (wasPending.current && !loadMutation.isPending) inputRef.current?.focus()
    wasPending.current = loadMutation.isPending
  }, [loadMutation.isPending])

  async function commit(target) {
    setFailure(null)
    if (rows.some((row) => row.ticker === target)) {
      onSelectTicker(target)
      onValueChange('')
      return
    }
    try {
      const result = await loadMutation.mutateAsync(target)
      if (result.status === 'ok') {
        onLoaded(target)
        onSelectTicker(target)
        onValueChange('')
      } else {
        // One message per status, never collapsed into a generic "load failed" line.
        setFailure(describeLoadStatus(result.status, target))
      }
    } catch (error) {
      setFailure(failureText(error))
    }
  }

  function handleEnter() {
    if (!symbol) return
    const active = isOpen ? options[activeIndex] : undefined
    commit(active?.kind === 'match' ? active.row.ticker : symbol)
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter') {
      event.preventDefault()
      handleEnter()
      return
    }
    if (!isPhone) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!symbol) return
      setDismissed(false)
      const step = event.key === 'ArrowDown' ? 1 : -1
      setActiveIndex((index) => Math.min(options.length - 1, Math.max(0, index + step)))
    } else if (event.key === 'Escape') {
      if (isOpen) setDismissed(true)
      else if (value) onValueChange('')
    }
  }

  function handleClear() {
    setFailure(null)
    setDismissed(false)
    setActiveIndex(-1)
    onValueChange('')
    inputRef.current?.focus()
  }

  function handleChange(event) {
    setFailure(null)
    setDismissed(false)
    setActiveIndex(-1)
    onValueChange(event.target.value.toUpperCase())
  }

  const comboboxProps = isPhone
    ? {
        role: 'combobox',
        'aria-autocomplete': 'list',
        'aria-expanded': isOpen,
        'aria-controls': isOpen ? listboxId : undefined,
        'aria-activedescendant': isOpen && activeIndex >= 0 ? optionId(activeIndex) : undefined,
      }
    : {}

  return (
    <form className="ticker-search" role="search" onSubmit={(event) => event.preventDefault()}>
      <div className="ticker-search__field">
      <input
        ref={inputRef}
        type="text"
        className="ticker-search__input"
        aria-label="Search ticker"
        placeholder="Search ticker"
        value={value}
        maxLength={MAX_SYMBOL_LENGTH}
        disabled={loadMutation.isPending}
        aria-busy={loadMutation.isPending || undefined}
        autoComplete="off"
        spellCheck={false}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        {...comboboxProps}
      />
      {value && !loadMutation.isPending ? (
        <button type="button" className="ticker-search__clear" aria-label="Clear search" onClick={handleClear}>
          <span aria-hidden="true">×</span>
        </button>
      ) : null}
      </div>

      {loadMutation.isPending ? (
        <p className="ticker-search__notice t-small" role="status">
          Loading {loadMutation.variables}…
        </p>
      ) : null}

      {failure ? (
        <p className="ticker-search__notice t-small" role="alert">
          {failure}
        </p>
      ) : null}

      {isOpen ? (
        <ul className="ticker-search__listbox" id={listboxId} role="listbox" aria-label="Matching tickers">
          {options.map((option, index) => (
            <li
              key={option.kind === 'match' ? option.row.ticker : 'load'}
              id={optionId(index)}
              role="option"
              aria-selected={index === activeIndex}
              className="ticker-search__option"
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => commit(option.kind === 'match' ? option.row.ticker : symbol)}
            >
              {option.kind === 'match' ? (
                <>
                  <span className="t-num">{option.row.ticker}</span>
                  {option.row.loadedAt ? (
                    <span className="ticker-search__age t-small">{formatLastLoadedAt(option.row.loadedAt)}</span>
                  ) : null}
                  {reasonLabels(option.row.eligibility).length > 0 ? (
                    <span className="ticker-search__tag">{reasonLabels(option.row.eligibility)[0]}</span>
                  ) : null}
                </>
              ) : (
                <span>Load {symbol}</span>
              )}
            </li>
          ))}
        </ul>
      ) : null}

      {isPhone ? (
        <p className="sr-only" aria-live="polite">
          {symbol ? `${matches.length} of ${rows.length} tickers` : ''}
        </p>
      ) : null}
    </form>
  )
}
