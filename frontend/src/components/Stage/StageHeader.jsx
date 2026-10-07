import { useTickerContext } from '../../hooks/useTickerContext'
import { FavoriteStar } from './FavoriteStar'
import './stage-header.css'

function ageText(sessions) {
  if (sessions === 0) return 'current'
  return `${sessions} ${sessions === 1 ? 'session' : 'sessions'} old`
}

/**
 * The Stage's header: the selected ticker (the page's one h1), its last close, and the date of the
 * last session used with its age in sessions, all available before any debate has run. A ticker the
 * catalog does not list shows the date with no age; "Stale" is the server's word (a reason), shown
 * as text beside the date. No status dot, no colour carrying the meaning, no direction mark.
 *
 * With no ticker selected the header keeps its shape with placeholders, so selecting one adds no lines.
 */
export function StageHeader({ ticker }) {
  const context = useTickerContext(ticker)

  let asOfText = 'As of —'
  if (ticker && context.asOf) {
    asOfText = `As of ${context.asOf}`
    if (context.ageSessions !== null) asOfText += ` · ${ageText(context.ageSessions)}`
  }

  return (
    <div className="stage-header">
      <h1 className="stage-header__ticker t-ticker" data-empty={ticker ? undefined : ''}>
        {ticker ?? 'No ticker selected'}
      </h1>
      <span className="stage-header__close t-num">
        {ticker && context.lastClose !== null ? context.lastClose.toFixed(2) : '—'}
      </span>
      <span className="stage-header__asof t-small">{asOfText}</span>
      {ticker && context.stale ? <span className="stage-header__stale">Stale</span> : null}
      {ticker ? <FavoriteStar ticker={ticker} /> : null}
    </div>
  )
}
