// The 5-session range band, drawn at one position (the t+5 session): a light fill between an upper
// and a lower bound, each bound a dashed line in the accent colour, and its `±X.XX%` label beside it.
// A series primitive rather than series data on purpose: nothing is drawn between the last close and
// t+5, and no series receives a valued point there (dashboard-ui: the range is a position, not a path).
//
// The draw code runs on a canvas and cannot execute under jsdom; its geometry and colours are what the
// unit tests assert (against a recording context), and the pixels are checked by eye in a browser.

export const MONO_FONT_STACK = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'

const DASH_PATTERN_PX = [5, 4]
const BOUND_LINE_WIDTH_PX = 1.5
const LABEL_FONT_PX = 12
const LABEL_GAP_PX = 8
// A monospace glyph is about 0.6 em wide in every stack above.
const GLYPH_WIDTH_EM = 0.6

/** Width the label needs, in CSS pixels (estimated: a monospace string is its length in glyphs). */
export function bandLabelWidthPx(label) {
  return label ? label.length * GLYPH_WIDTH_EM * LABEL_FONT_PX : 0
}

/** Space the label needs beside the band: its width and the gap to the band. */
export const bandLabelRoomPx = (label) => (label ? bandLabelWidthPx(label) + LABEL_GAP_PX : 0)

export class RangeBandPrimitive {
  /** @param {{line: string, fill: string, text: string}} colors the bounds (accent), the fill and the label */
  constructor(colors) {
    this.colors = colors
    /** @type {{time: string, upper: number, lower: number, label?: string|null} | null} */
    this.band = null
    this._chart = null
    this._series = null
    this._requestUpdate = null
    this._geometry = null
    this._paneViews = [
      {
        zOrder: () => 'normal',
        renderer: () => ({ draw: (target) => this._draw(target) }),
      },
    ]
  }

  attached({ chart, series, requestUpdate }) {
    this._chart = chart
    this._series = series
    this._requestUpdate = requestUpdate
  }

  detached() {
    this._chart = null
    this._series = null
    this._requestUpdate = null
  }

  /** Sets the band to draw, or null to draw nothing. */
  setBand(band) {
    this.band = band
    this._requestUpdate?.()
  }

  /** Re-colours the band (a theme change) and asks the chart to redraw. */
  setColors(colors) {
    this.colors = colors
    this._requestUpdate?.()
  }

  paneViews() {
    return this._paneViews
  }

  updateAllViews() {
    this._geometry = this._computeGeometry()
  }

  /** The band's box in chart coordinates and its label, or null when there is no band to draw. */
  geometry() {
    return this._geometry
  }

  /** Makes the price scale include both bounds; no band means no say in the scale. */
  autoscaleInfo() {
    if (!this.band) return null
    return { priceRange: { minValue: this.band.lower, maxValue: this.band.upper } }
  }

  // One session wide: the distance between two neighbouring logical slots.
  _sessionWidth(timeScale) {
    const first = timeScale.logicalToCoordinate(0)
    const second = timeScale.logicalToCoordinate(1)
    if (first !== null && second !== null) return Math.abs(second - first)
    return timeScale.options().barSpacing
  }

  _computeGeometry() {
    if (!this.band || !this._chart || !this._series) return null
    const timeScale = this._chart.timeScale()
    const x = timeScale.timeToCoordinate(this.band.time)
    const top = this._series.priceToCoordinate(this.band.upper)
    const bottom = this._series.priceToCoordinate(this.band.lower)
    if (x === null || top === null || bottom === null) return null
    const half = this._sessionWidth(timeScale) / 2
    return { left: x - half, right: x + half, top, bottom, label: this.band.label ?? null }
  }

  _draw(target) {
    const geometry = this._geometry
    if (!geometry) return
    target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio: hr, verticalPixelRatio: vr, mediaSize }) => {
      const left = geometry.left * hr
      const right = geometry.right * hr
      const top = geometry.top * vr
      const bottom = geometry.bottom * vr

      context.save()
      context.fillStyle = this.colors.fill
      context.fillRect(left, top, right - left, bottom - top)

      context.strokeStyle = this.colors.line
      context.lineWidth = Math.max(1, Math.round(BOUND_LINE_WIDTH_PX * vr))
      context.setLineDash(DASH_PATTERN_PX.map((length) => length * hr))
      context.beginPath()
      context.moveTo(left, top)
      context.lineTo(right, top)
      context.moveTo(left, bottom)
      context.lineTo(right, bottom)
      context.stroke()

      if (geometry.label) this._drawLabel(context, geometry, { hr, vr, mediaWidth: mediaSize.width })
      context.restore()
    })
  }

  // To the right of the band when it fits inside the card, else to its left, so it never leaves the card.
  _drawLabel(context, geometry, { hr, vr, mediaWidth }) {
    const fitsRight = geometry.right + LABEL_GAP_PX + bandLabelWidthPx(geometry.label) <= mediaWidth
    context.setLineDash([])
    context.fillStyle = this.colors.text
    context.font = `600 ${LABEL_FONT_PX * vr}px ${MONO_FONT_STACK}`
    context.textBaseline = 'middle'
    context.textAlign = fitsRight ? 'left' : 'right'
    const x = fitsRight ? geometry.right + LABEL_GAP_PX : geometry.left - LABEL_GAP_PX
    context.fillText(geometry.label, x * hr, ((geometry.top + geometry.bottom) / 2) * vr)
  }
}
