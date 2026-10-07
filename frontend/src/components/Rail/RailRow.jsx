import { describeLoadOutcome, useIsTickerLoading, useLoadTicker } from '../../hooks/useLoadTicker'
import { formatLastLoadedAt } from '../../lib/relativeTime'
import { reasonLabels } from '../../lib/railRows'

/**
 * One ticker in the Rail: the symbol, when it was loaded, a Refresh control and, only when the
 * ticker cannot be analysed, a text tag naming the first reason. The tag comes from the catalog's
 * `eligibility`, never from an age or a date worked out here. A row carries no stance chip, no
 * return, no status dot and no direction mark.
 *
 * The select button's accessible name lists every reason ("TCB, Loaded 28d ago, Delisted, Stale"),
 * so it reads the same whether the Rail is shown wide, collapsed to symbols or as a drawer.
 *
 * @param {{
 *   row: {ticker: string, loadedAt: string|null, eligibility: object|null},
 *   isSelected: boolean,
 *   onSelect: (ticker: string) => void,
 * }} props
 */
export function RailRow({ row, isSelected, onSelect }) {
  const { ticker, loadedAt, eligibility } = row
  const loadMutation = useLoadTicker(ticker)
  const isTickerLoading = useIsTickerLoading(ticker)

  const labels = reasonLabels(eligibility)
  const age = formatLastLoadedAt(loadedAt)
  const name = [ticker, age, ...labels].filter(Boolean).join(', ')
  const message = describeLoadOutcome(loadMutation, ticker)

  return (
    <li className="rail-row" data-selected={isSelected || undefined}>
      <button
        type="button"
        className="rail-row__select"
        aria-current={isSelected ? 'true' : undefined}
        aria-label={name}
        title={labels.length > 0 ? labels.join(', ') : (loadedAt ?? undefined)}
        onClick={() => onSelect(ticker)}
      >
        <span className="rail-row__symbol t-num">{ticker}</span>
        {age ? <span className="rail-row__age t-small">{age}</span> : null}
        {labels.length > 0 ? <span className="rail-row__tag">{labels[0]}</span> : null}
      </button>
      {/* Refresh never changes the selection. It is in the tab order at every width; the stylesheet
          only makes it visible on hover and focus (always on touch), never display: none. */}
      <button
        type="button"
        className="rail-row__refresh"
        disabled={isTickerLoading}
        data-loading={isTickerLoading || undefined}
        aria-label={`Refresh ${ticker}`}
        title={`Refresh ${ticker}`}
        onClick={() => loadMutation.mutate()}
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path
            d="M2 8a6 6 0 1 1 1.76 4.24M2 8V4m0 4h4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      {message ? (
        <span className="rail-row__message t-small" role="alert">
          {message}
        </span>
      ) : null}
    </li>
  )
}
