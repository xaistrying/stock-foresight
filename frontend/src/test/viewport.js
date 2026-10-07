// Test helper: a `matchMedia` that evaluates width and colour-scheme queries against
// a viewport the test controls, and tells the listeners when it changes. jsdom has no
// layout, so `useLayoutMode` and `useTheme` are tested against this instead.
const listeners = new Set()
let state = { width: 1440, dark: false, hover: true }
let installed = false

function evaluate(query) {
  const min = query.match(/\(min-width:\s*(\d+)px\)/)
  const max = query.match(/\(max-width:\s*(\d+)px\)/)
  if (min) return state.width >= Number(min[1])
  if (max) return state.width <= Number(max[1])
  if (/prefers-color-scheme:\s*dark/.test(query)) return state.dark
  if (/hover:\s*none/.test(query)) return !state.hover
  return false
}

function mediaQueryList(query) {
  const own = new Set()
  return {
    get matches() {
      return evaluate(query)
    },
    media: query,
    onchange: null,
    addEventListener: (type, fn) => {
      if (type !== 'change') return
      own.add(fn)
      listeners.add({ fn, query, own })
    },
    removeEventListener: (type, fn) => {
      for (const entry of listeners) if (entry.fn === fn && entry.query === query) listeners.delete(entry)
      own.delete(fn)
    },
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }
}

const original = typeof window !== 'undefined' ? window.matchMedia : undefined

/** Install the mock; later calls update the same viewport. */
export function setViewport(width, { dark = false, hover = true } = {}) {
  state = { width, dark, hover }
  window.innerWidth = width
  window.matchMedia = (query) => mediaQueryList(query)
  installed = true
  return controller
}

function notify() {
  for (const { fn, query } of [...listeners]) fn({ matches: evaluate(query), media: query })
}

export const controller = {
  setWidth(width) {
    state = { ...state, width }
    window.innerWidth = width
    notify()
  },
  setDark(dark) {
    state = { ...state, dark }
    notify()
  },
}

export function resetViewport() {
  listeners.clear()
  state = { width: 1440, dark: false, hover: true }
  if (installed) window.matchMedia = original
  installed = false
}
