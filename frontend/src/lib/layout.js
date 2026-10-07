// The viewport widths at which the dashboard changes layout. App.css repeats these numbers in
// its @media queries; lib/layout.test.js fails if the two ever differ.
export const BREAKPOINTS = { wide: 1440, collapsed: 1144, drawer: 768 }

/** 'wide' (1440+), 'collapsed' (1144-1439), 'drawer' (768-1143) or 'phone' (below 768). */
export function layoutModeFor(width) {
  if (width >= BREAKPOINTS.wide) return 'wide'
  if (width >= BREAKPOINTS.collapsed) return 'collapsed'
  if (width >= BREAKPOINTS.drawer) return 'drawer'
  return 'phone'
}

export const minWidthQuery = (width) => `(min-width: ${width}px)`
