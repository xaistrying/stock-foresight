// The 5-session range band, drawn at one position (the t+5 session): a light fill between an
// upper and a lower bound, each bound a dashed line, all in one neutral colour. A series
// primitive rather than series data on purpose: nothing is drawn between the last close and t+5,
// and no series receives a valued point there (dashboard-ui: the range is a position, not a path).
//
// The draw code runs on a canvas and cannot execute under jsdom; its geometry inputs (`band`,
// `color`, `autoscaleInfo`) are what the unit tests assert, and the pixels are checked by eye in a
// browser (retire-direction-model tasks.md 5.8).

const FILL_OPACITY = 0.1
const DASH_PATTERN_PX = [5, 4]
const BOUND_LINE_WIDTH_PX = 1.5

export class RangeBandPrimitive {
  /** @param {string} color the chart's neutral ink colour (never the up/down colours) */
  constructor(color) {
    this.color = color
    /** @type {{time: string, upper: number, lower: number} | null} */
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

  paneViews() {
    return this._paneViews
  }

  updateAllViews() {
    this._geometry = this._computeGeometry()
  }

  /** Makes the price scale include both bounds; no band means no say in the scale. */
  autoscaleInfo() {
    if (!this.band) return null
    return { priceRange: { minValue: this.band.lower, maxValue: this.band.upper } }
  }

  _computeGeometry() {
    if (!this.band || !this._chart || !this._series) return null
    const timeScale = this._chart.timeScale()
    const x = timeScale.timeToCoordinate(this.band.time)
    const top = this._series.priceToCoordinate(this.band.upper)
    const bottom = this._series.priceToCoordinate(this.band.lower)
    if (x === null || top === null || bottom === null) return null
    // One session wide, centred on the t+5 slot.
    const halfSession = timeScale.options().barSpacing / 2
    const left = x - halfSession
    const right = x + halfSession
    return { left, right, top, bottom }
  }

  _draw(target) {
    const geometry = this._geometry
    if (!geometry) return
    target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio, verticalPixelRatio }) => {
      const left = geometry.left * horizontalPixelRatio
      const right = geometry.right * horizontalPixelRatio
      const top = geometry.top * verticalPixelRatio
      const bottom = geometry.bottom * verticalPixelRatio

      context.save()
      context.globalAlpha = FILL_OPACITY
      context.fillStyle = this.color
      context.fillRect(left, top, right - left, bottom - top)

      context.globalAlpha = 1
      context.strokeStyle = this.color
      context.lineWidth = Math.max(1, Math.round(BOUND_LINE_WIDTH_PX * verticalPixelRatio))
      context.setLineDash(DASH_PATTERN_PX.map((length) => length * horizontalPixelRatio))
      context.beginPath()
      context.moveTo(left, top)
      context.lineTo(right, top)
      context.moveTo(left, bottom)
      context.lineTo(right, bottom)
      context.stroke()
      context.restore()
    })
  }
}
