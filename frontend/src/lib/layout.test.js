import { describe, expect, it } from 'vitest'
import { BREAKPOINTS, layoutModeFor } from './layout'
import { mediaWidths, readSrc } from '../test/cssText'

describe('layout constants', () => {
  it('names the three breakpoints of the design: 1440, 1144 and 768', () => {
    expect(BREAKPOINTS).toEqual({ wide: 1440, collapsed: 1144, drawer: 768 })
  })

  it.each([
    [1440, 'wide'],
    [1439, 'collapsed'],
    [1144, 'collapsed'],
    [1143, 'drawer'],
    [768, 'drawer'],
    [767, 'phone'],
  ])('layoutModeFor(%i) is %s', (width, mode) => {
    expect(layoutModeFor(width)).toBe(mode)
  })

  // The hook decides where a component renders; the stylesheet decides how it is laid out.
  // They must break at the same widths, so a change to one alone fails here.
  it('uses the same breakpoints in the layout stylesheet as in lib/layout.js', () => {
    const widths = mediaWidths(readSrc('App.css'))

    expect(widths).toEqual([...Object.values(BREAKPOINTS)].sort((a, b) => a - b))
  })
})
