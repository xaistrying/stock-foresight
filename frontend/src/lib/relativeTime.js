// Renders a "last loaded" timestamp as a short relative string for the
// ticker chip's refresh control (design.md Decision 5, tasks.md 4.2) —
// e.g. "Loaded 14d ago". Deliberately coarse (minutes/hours/days), not a
// full i18n relative-time formatter: the chip only needs a compact "is
// this old?" signal, with the exact ISO timestamp available via `title`
// for anyone who wants it (see TickerChip's use of this).

const MINUTE_MS = 60 * 1000
const HOUR_MS = 60 * MINUTE_MS
const DAY_MS = 24 * HOUR_MS

/**
 * @param {string | null | undefined} isoTimestamp - `last_loaded_at` from
 *   `GET /tickers`, or null/undefined for a never-loaded ticker.
 * @param {number} [now] - current time in ms since epoch; defaults to
 *   `Date.now()`, overridable for deterministic tests.
 * @returns {string | null} e.g. "Loaded just now" / "Loaded 3h ago" /
 *   "Loaded 14d ago", or null when `isoTimestamp` is null/undefined.
 */
export function formatLastLoadedAt(isoTimestamp, now = Date.now()) {
  if (!isoTimestamp) return null

  const loadedAt = new Date(isoTimestamp).getTime()
  if (Number.isNaN(loadedAt)) return null

  const elapsedMs = Math.max(0, now - loadedAt)

  if (elapsedMs < MINUTE_MS) return 'Loaded just now'
  if (elapsedMs < HOUR_MS) return `Loaded ${Math.floor(elapsedMs / MINUTE_MS)}m ago`
  if (elapsedMs < DAY_MS) return `Loaded ${Math.floor(elapsedMs / HOUR_MS)}h ago`
  return `Loaded ${Math.floor(elapsedMs / DAY_MS)}d ago`
}
