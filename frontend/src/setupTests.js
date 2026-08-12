import '@testing-library/jest-dom/vitest'
import { resolveToLegacyColor } from './lib/color'

// jsdom doesn't implement matchMedia; lightweight-charts (via fancy-canvas)
// queries it to observe devicePixelRatio changes. A minimal stub is enough
// for tests — no real media-query matching is needed under jsdom.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })
}

// jsdom doesn't implement canvas 2D rendering (no `canvas` native package
// installed — see ChartPanel's test file for why). lightweight-charts
// draws to canvas on every animation frame; without a stub, its internal
// draw loop throws on jsdom's unimplemented getContext(). Component tests
// only assert on DOM text/roles, never on rendered pixels, so a minimal
// no-op 2D context is enough to let the library's draw loop run without
// crashing — this does not make canvas *content* testable, only silent.
//
// `fillStyle`'s setter runs values through the same resolveToLegacyColor()
// used in production (src/lib/color.js) — not because production code
// depends on canvas fillStyle for color resolution anymore (an earlier
// version did, and that assumption turned out to be browser-dependent and
// wrong in practice — see color.js's header comment), but so this stub
// stays a faithful-enough approximation of a real canvas context rather
// than silently accepting any string, including one production code
// should never hand it.
if (typeof HTMLCanvasElement !== 'undefined') {
  const noop = () => {}
  function createNoopContext2D() {
    let fillStyleValue = '#000000'
    return {
      fillRect: noop,
      clearRect: noop,
      getContextAttributes: () => ({}),
      save: noop,
      restore: noop,
      scale: noop,
      translate: noop,
      rotate: noop,
      setTransform: noop,
      measureText: () => ({ width: 0 }),
      fillText: noop,
      strokeText: noop,
      beginPath: noop,
      moveTo: noop,
      lineTo: noop,
      closePath: noop,
      stroke: noop,
      fill: noop,
      arc: noop,
      rect: noop,
      createLinearGradient: () => ({ addColorStop: noop }),
      drawImage: noop,
      putImageData: noop,
      getImageData: () => ({ data: [] }),
      get fillStyle() {
        return fillStyleValue
      },
      set fillStyle(value) {
        fillStyleValue = resolveToLegacyColor(value)
      },
    }
  }
  HTMLCanvasElement.prototype.getContext = () => createNoopContext2D()
}
