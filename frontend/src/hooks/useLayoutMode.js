import { useSyncExternalStore } from 'react'
import { BREAKPOINTS, minWidthQuery } from '../lib/layout'

// The hook decides where a component renders (one place per mode); the stylesheet decides how it
// is laid out. `matchMedia` is read synchronously on the first render so the first paint already
// has the right structure, and listened to rather than polled.
const QUERIES = Object.values(BREAKPOINTS).map(minWidthQuery)

function currentMode() {
  const matches = (width) => window.matchMedia(minWidthQuery(width)).matches
  if (matches(BREAKPOINTS.wide)) return 'wide'
  if (matches(BREAKPOINTS.collapsed)) return 'collapsed'
  if (matches(BREAKPOINTS.drawer)) return 'drawer'
  return 'phone'
}

function subscribe(onChange) {
  const lists = QUERIES.map((query) => window.matchMedia(query))
  lists.forEach((list) => list.addEventListener('change', onChange))
  return () => lists.forEach((list) => list.removeEventListener('change', onChange))
}

/** @returns {'wide'|'collapsed'|'drawer'|'phone'} */
export function useLayoutMode() {
  return useSyncExternalStore(subscribe, currentMode)
}
