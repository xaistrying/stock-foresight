import { describe, expect, it } from 'vitest'
import { parseTokens } from './styles/parseTokens'
import { declarations, parseRules, readSrc, rulesFor } from './test/cssText'

// The dashboard uses the whole viewport width (design.md Decision 15; the owner's rule). jsdom
// computes no layout, so this is checked three ways: the stylesheet text (no cap, no centring,
// equal padding, flexible Stage), the arithmetic of the zone widths from the token values, and,
// in ChartPanel.test.jsx, the chart's re-layout. The pixels are checked by eye in task 12.8.

const tokens = parseTokens(readSrc('styles/tokens.css')).light
const px = (name) => Number(tokens[`--${name}`].replace('px', ''))

/** Widths of the three zones, the gutters and the padding at `viewport` px, from the tokens. */
export function zoneWidths(viewport) {
  const wide = viewport >= 1440
  const padding = px(wide ? 'space-6' : 'space-4')
  const gutter = px('space-4')
  const rail = wide ? px('rail-w') : px('rail-w-min')
  const verdict = px('verdict-w')
  const stage = viewport - 2 * padding - rail - verdict - 2 * gutter
  const gap = px('space-3')
  return { padding, gutter, rail, verdict, stage, debateColumn: (stage - 2 * gap) / 3 }
}

const SHELL_SELECTORS = ['.app-shell', '.workspace', '.topbar']
const files = { '.app-shell': 'App.css', '.workspace': 'App.css', '.topbar': 'components/Topbar/topbar.css' }

describe('no cap and no centring', () => {
  it.each(SHELL_SELECTORS)('%s declares no max-width and no automatic horizontal margin', (selector) => {
    const rules = rulesFor(readSrc(files[selector]), selector)

    expect(rules.length).toBeGreaterThan(0)
    for (const rule of rules) {
      const found = declarations(rule.body)
      expect(found['max-width'], `${selector} max-width`).toBeUndefined()
      expect(found.width ?? '', `${selector} width`).not.toMatch(/^min\(/)
      for (const property of ['margin', 'margin-inline', 'margin-left', 'margin-right']) {
        expect(found[property] ?? '', `${selector} ${property}`).not.toMatch(/\bauto\b/)
      }
    }
  })

  it('has no max-width on any zone or the debate grid in the shell stylesheet', () => {
    for (const rule of parseRules(readSrc('App.css'))) {
      expect(declarations(rule.body)['max-width'], rule.selector).toBeUndefined()
    }
  })
})

describe('equal page padding', () => {
  it('pads left and right with the same single value: space-4 below 1440px, space-6 from 1440px', () => {
    const shell = rulesFor(readSrc('App.css'), '.app-shell')

    const base = shell.find((rule) => rule.media === '')
    const wide = shell.find((rule) => rule.media === '(min-width: 1440px)')

    expect(declarations(base.body)['padding-inline']).toBe('var(--space-4)')
    expect(declarations(wide.body)['padding-inline']).toBe('var(--space-6)')
    for (const rule of shell) {
      expect(declarations(rule.body)['padding-left']).toBeUndefined()
      expect(declarations(rule.body)['padding-right']).toBeUndefined()
    }
  })
})

describe('zone widths', () => {
  it('gives the Rail --rail-w from 1440px and --rail-w-min from 1144px, and the Verdict panel --verdict-w', () => {
    const columns = (media) =>
      declarations(rulesFor(readSrc('App.css'), '.app-shell').find((rule) => rule.media === media).body)[
        'grid-template-columns'
      ]

    expect(columns('(min-width: 1144px)')).toBe('var(--rail-w-min) minmax(0, 1fr)')
    expect(columns('(min-width: 1440px)')).toBe('var(--rail-w) minmax(0, 1fr)')
    const workspace = rulesFor(readSrc('App.css'), '.workspace').find((rule) => rule.media === '(min-width: 1144px)')
    expect(declarations(workspace.body)['grid-template-columns']).toBe('minmax(0, 1fr) var(--verdict-w)')
  })

  it('gives every remaining pixel to the Stage, and equal widths to the three Debate columns', () => {
    const debate = declarations(rulesFor(readSrc('App.css'), '.debate-grid')[0].body)

    expect(debate['grid-template-columns']).toBe('repeat(3, minmax(0, 1fr))')
    expect(debate.gap).toBe('var(--space-3)')
  })

  it.each([
    [1440, 772, 249.33],
    [1920, 1252, 409.33],
    [2560, 1892, 622.67],
  ])('at %ipx the Stage is %ipx and each Debate column %f px', (viewport, stage, column) => {
    const zones = zoneWidths(viewport)

    expect(zones.stage).toBe(stage)
    expect(zones.debateColumn).toBeCloseTo(column, 2)
    expect(zones.rail + zones.stage + zones.verdict + 2 * zones.gutter + 2 * zones.padding).toBe(viewport)
    expect(zones.padding).toBe(32)
    expect(zones.rail).toBe(232)
    expect(zones.verdict).toBe(340)
  })

  it('keeps three Debate columns of at least 220px at 1144px (Stage 684px) and 768px', () => {
    expect(zoneWidths(1144).stage).toBe(684)
    expect(zoneWidths(1144).debateColumn).toBeGreaterThanOrEqual(220)
    // Below 1144 the Rail is a drawer and the Verdict panel a strip, so the Stage is the page.
    const drawerStage = 768 - 2 * px('space-4')
    expect((drawerStage - 2 * px('space-3')) / 3).toBeGreaterThanOrEqual(220)
  })

  it('floats no zone: a zone shorter than its row is top-aligned, never auto-margined', () => {
    for (const selector of ['.rail', '.verdict-panel']) {
      const found = rulesFor(readSrc('App.css'), selector).map((rule) => declarations(rule.body))
      expect(found.some((d) => d['align-self'] === 'start'), selector).toBe(true)
    }
  })
})
