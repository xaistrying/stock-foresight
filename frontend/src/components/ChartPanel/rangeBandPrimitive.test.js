import { describe, expect, it, vi } from 'vitest'
import { RangeBandPrimitive } from './rangeBandPrimitive'

// The draw code runs on a canvas that jsdom does not have, so a recording context stands in for
// it: what is asserted is what would be drawn and where, never pixels (those are checked by eye in
// a browser, task 12.4).
const COLORS = { line: 'rgb(0, 0, 200)', fill: 'rgba(0, 0, 200, 0.15)', text: 'rgb(20, 20, 20)' }
const BAND = { time: '2026-08-05', upper: 11.55, lower: 10.45, label: '±5.00%' }

function attach(primitive, { x = 500, spacing = 12 } = {}) {
  const requestUpdate = vi.fn()
  primitive.attached({
    chart: {
      timeScale: () => ({
        timeToCoordinate: () => x,
        logicalToCoordinate: (index) => index * spacing,
        options: () => ({ barSpacing: 99 }),
      }),
    },
    series: { priceToCoordinate: (price) => (price === BAND.upper ? 40 : 160) },
    requestUpdate,
  })
  return requestUpdate
}

function recordingContext() {
  const calls = []
  const record = (name) => (...args) => calls.push([name, ...args])
  const context = {
    calls,
    save: record('save'),
    restore: record('restore'),
    fillRect: (...args) => calls.push(['fillRect', context.fillStyle, ...args]),
    fillText: (...args) => calls.push(['fillText', context.fillStyle, context.textAlign, ...args]),
    setLineDash: record('setLineDash'),
    beginPath: record('beginPath'),
    moveTo: record('moveTo'),
    lineTo: record('lineTo'),
    stroke: (...args) => calls.push(['stroke', context.strokeStyle, ...args]),
  }
  return context
}

function drawOn(primitive, mediaWidth = 700) {
  const context = recordingContext()
  primitive.updateAllViews()
  primitive.paneViews()[0].renderer().draw({
    useBitmapCoordinateSpace: (callback) =>
      callback({
        context,
        horizontalPixelRatio: 1,
        verticalPixelRatio: 1,
        mediaSize: { width: mediaWidth, height: 300 },
      }),
  })
  return context.calls
}

describe('RangeBandPrimitive', () => {
  it('keeps the colours it was constructed with', () => {
    expect(new RangeBandPrimitive(COLORS).colors).toEqual(COLORS)
  })

  it('setColors replaces them and asks the chart to redraw', () => {
    const primitive = new RangeBandPrimitive(COLORS)
    const requestUpdate = attach(primitive)
    const dark = { line: 'rgb(126, 166, 255)', fill: 'rgba(126, 166, 255, 0.18)', text: 'rgb(233, 236, 241)' }

    primitive.setColors(dark)

    expect(primitive.colors).toEqual(dark)
    expect(requestUpdate).toHaveBeenCalled()
  })

  it('carries the label text on the band geometry, one session wide around the t+5 position', () => {
    const primitive = new RangeBandPrimitive(COLORS)
    attach(primitive, { x: 500, spacing: 12 })
    primitive.setBand(BAND)
    primitive.updateAllViews()

    expect(primitive.geometry()).toEqual({ left: 494, right: 506, top: 40, bottom: 160, label: '±5.00%' })
  })

  it('has no geometry, draws nothing and takes no part in the price scale when there is no band', () => {
    const primitive = new RangeBandPrimitive(COLORS)
    attach(primitive)
    primitive.setBand(null)

    expect(drawOn(primitive)).toEqual([])
    expect(primitive.geometry()).toBeNull()
    expect(primitive.autoscaleInfo()).toBeNull()
  })

  it('asks the chart to redraw when the band changes', () => {
    const primitive = new RangeBandPrimitive(COLORS)
    const requestUpdate = attach(primitive)

    primitive.setBand(BAND)

    expect(requestUpdate).toHaveBeenCalledTimes(1)
  })

  it('fills between the bounds with the fill colour and strokes both bounds dashed in the line colour', () => {
    const primitive = new RangeBandPrimitive(COLORS)
    attach(primitive)
    primitive.setBand(BAND)

    const calls = drawOn(primitive)

    expect(calls).toContainEqual(['fillRect', COLORS.fill, 494, 40, 12, 120])
    expect(calls).toContainEqual(['setLineDash', [5, 4]])
    expect(calls).toContainEqual(['stroke', COLORS.line])
    // Both bounds, top then bottom, as one path.
    const lines = calls.filter(([name]) => name === 'moveTo' || name === 'lineTo')
    expect(lines).toEqual([
      ['moveTo', 494, 40],
      ['lineTo', 506, 40],
      ['moveTo', 494, 160],
      ['lineTo', 506, 160],
    ])
  })

  it('writes the label to the right of the band when there is room', () => {
    const primitive = new RangeBandPrimitive(COLORS)
    attach(primitive, { x: 300 })
    primitive.setBand(BAND)

    const text = drawOn(primitive, 700).find(([name]) => name === 'fillText')

    expect(text[1]).toBe(COLORS.text)
    expect(text[2]).toBe('left')
    expect(text[3]).toBe('±5.00%')
    expect(text[4]).toBeGreaterThan(306) // right of the band's right edge
  })

  it('writes the label to the left of the band when the right side would leave the card', () => {
    const primitive = new RangeBandPrimitive(COLORS)
    attach(primitive, { x: 690 })
    primitive.setBand(BAND)

    const text = drawOn(primitive, 700).find(([name]) => name === 'fillText')

    expect(text[2]).toBe('right')
    expect(text[4]).toBeLessThan(684) // left of the band's left edge
  })

  it('never draws the label without text', () => {
    const primitive = new RangeBandPrimitive(COLORS)
    attach(primitive)
    primitive.setBand({ ...BAND, label: null })

    expect(drawOn(primitive).some(([name]) => name === 'fillText')).toBe(false)
  })

  it('falls back to the configured bar spacing when the logical scale cannot answer', () => {
    const primitive = new RangeBandPrimitive(COLORS)
    primitive.attached({
      chart: {
        timeScale: () => ({
          timeToCoordinate: () => 100,
          logicalToCoordinate: () => null,
          options: () => ({ barSpacing: 10 }),
        }),
      },
      series: { priceToCoordinate: () => 50 },
      requestUpdate: () => {},
    })
    primitive.setBand(BAND)
    primitive.updateAllViews()

    expect(primitive.geometry()).toMatchObject({ left: 95, right: 105 })
  })
})
