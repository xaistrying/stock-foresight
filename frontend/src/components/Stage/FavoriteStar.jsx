import { useFavorites } from '../../hooks/useFavorites'

/**
 * The star that keeps the selected ticker in the Rail's Watchlist section. A toggle: its name says what
 * it is, aria-pressed says whether it is on. It selects, loads and requests nothing; the list is kept
 * in this browser only.
 */
export function FavoriteStar({ ticker }) {
  const { isFavorite, toggle } = useFavorites()
  const favorite = isFavorite(ticker)

  return (
    <button
      type="button"
      className="favorite-star"
      aria-label={`Favorite ${ticker}`}
      aria-pressed={favorite}
      title={favorite ? `Remove ${ticker} from the Watchlist` : `Add ${ticker} to the Watchlist`}
      onClick={() => toggle(ticker)}
    >
      <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true">
        <path
          d="M8 1.8l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.6l-3.8 2 .7-4.3-3.1-3 4.3-.6z"
          fill={favorite ? 'currentColor' : 'none'}
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  )
}
