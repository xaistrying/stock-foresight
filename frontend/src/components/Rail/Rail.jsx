import { useEffect, useRef, useState } from 'react'
import { useFavorites } from '../../hooks/useFavorites'
import { useRailRows } from '../../hooks/useRailRows'
import { RailRow } from './RailRow'
import './rail.css'

const SKELETON_ROWS = 4

/**
 * The Rail: the loaded catalog (plus symbols loaded through the search this session) as one
 * vertical list, sorted by Symbol or Last loaded and filtered by the topbar search. It has no
 * input of its own and issues no request of its own: rows come from the one `GET /tickers`.
 *
 * The layout mode decides its shape. `wide`: the full column. `collapsed`: symbols only, expanded as
 * an overlay by hover, keyboard focus or the toggle button (no mouse needed, never modal). `drawer`:
 * hidden until the topbar "Tickers" button, or typing in the search, opens it (also never modal, so
 * the search stays usable). `phone` has no Rail: the search lists the matches itself.
 *
 * @param {{
 *   mode: 'wide'|'collapsed'|'drawer'|'phone',
 *   selectedTicker: string|null,
 *   onSelectTicker: (ticker: string) => void,
 *   searched: Array<{ticker: string, loadedAt: string}>,
 *   query: string,
 *   drawerOpen?: boolean,
 *   id?: string,
 * }} props
 */
export function Rail({ mode, selectedTicker, onSelectTicker, searched, query, drawerOpen = false, id = 'rail' }) {
  const [sort, setSort] = useState('symbol')
  const [pinned, setPinned] = useState(false)
  const toggleRef = useRef(null)
  const navRef = useRef(null)
  const firstSort = useRef(true)
  const { rows, allRows, isLoading, isError } = useRailRows({ searched, sort, query })
  const { favorites } = useFavorites()
  // The Watchlist is the tickers starred in the Stage header, in the same order and under the same search as the rest; a
  // starred ticker is listed there and not again below.
  const watchlist = rows.filter((row) => favorites.includes(row.ticker))
  const others = rows.filter((row) => !favorites.includes(row.ticker))

  const collapsed = mode === 'collapsed'
  const isPinned = collapsed && pinned
  const listId = `${id}-list`
  const shownQuery = query.trim()

  // Escape closes a pinned overlay and puts focus back on its toggle, wherever focus is.
  useEffect(() => {
    if (!isPinned) return undefined
    const onKeyDown = (event) => {
      if (event.key !== 'Escape') return
      setPinned(false)
      toggleRef.current?.focus()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [isPinned])

  // The Rail scrolls on its own, so a ticker selected elsewhere (the search, or by Enter) can sit in a
  // row that is out of view: bring it into view, nearest edge only. This runs when the SELECTION
  // changes (or its row appears), never when the order changes: re-sorting must not send the list
  // after the selected row. jsdom has no scrollIntoView.
  const selectedListed = rows.some((row) => row.ticker === selectedTicker)
  useEffect(() => {
    if (!selectedTicker || !selectedListed) return
    navRef.current?.querySelector('[aria-current="true"]')?.closest('li')?.scrollIntoView?.({ block: 'nearest' })
  }, [selectedTicker, selectedListed])

  // A new order starts at its top. Without this the list keeps its scroll offset (and the browser may
  // follow a row to its new place), so changing the sort looked like the list rolling down.
  useEffect(() => {
    if (firstSort.current) {
      firstSort.current = false
      return
    }
    if (navRef.current) navRef.current.scrollTop = 0
  }, [sort])

  function handleSelect(ticker) {
    setPinned(false)
    onSelectTicker(ticker)
  }

  const renderRow = (row) => (
    <RailRow
      key={row.ticker}
      row={row}
      isSelected={selectedTicker === row.ticker}
      onSelect={handleSelect}
    />
  )

  return (
    <nav
      ref={navRef}
      className="rail"
      id={id}
      aria-label="Tickers"
      data-mode={mode}
      data-pinned={isPinned || undefined}
      hidden={mode === 'drawer' && !drawerOpen}
    >
      {collapsed ? (
        <button
          ref={toggleRef}
          type="button"
          className="rail__toggle"
          aria-expanded={isPinned}
          aria-controls={listId}
          aria-label="Show full ticker list"
          onClick={() => setPinned((open) => !open)}
        >
          <span className="rail__chevron" aria-hidden="true" />
        </button>
      ) : null}

      <div className="rail__header">
        <select
          className="rail__sort t-small"
          aria-label="Sort tickers"
          value={sort}
          onChange={(event) => setSort(event.target.value)}
        >
          <option value="symbol">Symbol</option>
          <option value="loaded">Last loaded</option>
        </select>
      </div>

      {isError ? (
        <p className="rail__message t-small" role="alert">
          Couldn't load the ticker list — please refresh.
        </p>
      ) : null}

      <div className="rail__lists" id={listId}>
        {watchlist.length > 0 ? (
          <section className="rail__section">
            <h2 className="rail__heading t-label">Watchlist</h2>
            <ul className="rail__list">{watchlist.map(renderRow)}</ul>
          </section>
        ) : null}
        <section className="rail__section">
          <h2 className="rail__heading t-label">All tickers</h2>
          <ul className="rail__list">
            {isLoading
              ? Array.from({ length: SKELETON_ROWS }, (_, index) => (
                  <li key={index} className="rail-row rail-row--skeleton" aria-hidden="true" />
                ))
              : null}
            {others.map(renderRow)}
          </ul>
        </section>
      </div>

      {shownQuery && !isLoading && rows.length === 0 ? (
        <p className="rail__message t-small">
          No ticker in the Rail matches "{shownQuery.toUpperCase()}". Press Enter to load it.
        </p>
      ) : null}

      {/* Announces the filtered count: the list changing as the user types would otherwise be
          silent. Always mounted, so a polite live region exists before its first update. */}
      <p className="sr-only" aria-live="polite">
        {shownQuery ? `${rows.length} of ${allRows.length} tickers` : ''}
      </p>
    </nav>
  )
}
