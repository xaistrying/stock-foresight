import { useCallback, useSyncExternalStore } from 'react'

export const FAVORITES_STORAGE_KEY = 'stock-foresight-favorites'

// The starred symbols, kept in this browser only (nothing is sent anywhere). One list for the whole
// page, so a star in a Rail row and the Rail's Watchlist section read the same value. The list is read
// once and then held in memory, so it keeps working for the session when storage is blocked, and the
// same array object is returned until it changes (a store snapshot must be stable).
const listeners = new Set()
let memory = null

function read() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(FAVORITES_STORAGE_KEY))
    return Array.isArray(parsed) && parsed.every((symbol) => typeof symbol === 'string') ? parsed : []
  } catch {
    return []
  }
}

function snapshot() {
  if (memory === null) memory = read()
  return memory
}

function publish(next) {
  memory = next
  try {
    window.localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(next))
  } catch {
    // Storage is unavailable: the stars last for this page view only.
  }
  listeners.forEach((listener) => listener())
}

// Another tab changed the list: read it again.
function onStorage(event) {
  if (event.key !== FAVORITES_STORAGE_KEY) return
  memory = read()
  listeners.forEach((listener) => listener())
}

function subscribe(listener) {
  if (listeners.size === 0) window.addEventListener('storage', onStorage)
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) window.removeEventListener('storage', onStorage)
  }
}

/** Forgets the held list so the next read goes to storage again. For tests. */
export function resetFavoritesCache() {
  memory = null
}

/** @returns {{favorites: string[], isFavorite: (ticker: string) => boolean, toggle: (ticker: string) => void}} */
export function useFavorites() {
  const favorites = useSyncExternalStore(subscribe, snapshot)

  const toggle = useCallback((ticker) => {
    const current = snapshot()
    publish(current.includes(ticker) ? current.filter((symbol) => symbol !== ticker) : [...current, ticker])
  }, [])

  const isFavorite = useCallback((ticker) => favorites.includes(ticker), [favorites])

  return { favorites, isFavorite, toggle }
}
