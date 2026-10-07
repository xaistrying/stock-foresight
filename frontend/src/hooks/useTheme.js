import { useCallback, useEffect, useSyncExternalStore } from 'react'

export const THEME_STORAGE_KEY = 'stock-foresight-theme'
const DARK_QUERY = '(prefers-color-scheme: dark)'
const isTheme = (value) => value === 'light' || value === 'dark'

// One theme for the whole page, so the topbar toggle and the chart read the same value. The source
// of truth is the `data-theme` attribute on <html> (what the stylesheet reads); with no attribute
// the page follows the operating system. Storage can be blocked, so every access is guarded: the
// page must render, and the toggle must work for the session, without it.
const listeners = new Set()
const notify = () => listeners.forEach((listener) => listener())

function readStored() {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY)
    return isTheme(stored) ? stored : null
  } catch {
    return null
  }
}

function writeStored(theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // Storage is unavailable: the choice lasts for this page view only.
  }
}

const operatingSystemTheme = () => (window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light')

function currentTheme() {
  const attribute = document.documentElement.getAttribute('data-theme')
  if (isTheme(attribute)) return attribute
  return readStored() ?? operatingSystemTheme()
}

function subscribe(onChange) {
  listeners.add(onChange)
  const list = window.matchMedia(DARK_QUERY)
  list.addEventListener('change', onChange)
  return () => {
    listeners.delete(onChange)
    list.removeEventListener('change', onChange)
  }
}

/** @returns {{theme: 'light'|'dark', toggle: () => void}} */
export function useTheme() {
  const theme = useSyncExternalStore(subscribe, currentTheme)

  // The inline script in index.html applies a stored choice before first paint; this does the
  // same when that script did not run (tests, or a page opened without it).
  useEffect(() => {
    const stored = readStored()
    const root = document.documentElement
    if (stored && root.getAttribute('data-theme') !== stored) {
      root.setAttribute('data-theme', stored)
      notify()
    }
  }, [])

  const toggle = useCallback(() => {
    const next = currentTheme() === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', next)
    writeStored(next)
    notify()
  }, [])

  return { theme, toggle }
}
