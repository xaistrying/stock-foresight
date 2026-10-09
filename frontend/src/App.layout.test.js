import { describe, expect, it } from 'vitest'
import { allCssFiles, declarations, parseRules, readSrc, rulesFor } from './test/cssText'

// jsdom computes no layout, so the layout rules are checked in the stylesheets' own text
// (house style of the old App.test.jsx 'fills the viewport width' test).


describe('shell layout', () => {
  it('fixes the topbar to the top at --topbar-h', () => {
    const [rule] = rulesFor(readSrc('components/Topbar/topbar.css'), '.topbar')

    const found = declarations(rule.body)

    expect(found.position).toBe('fixed')
    expect(found.height).toBe('var(--topbar-h)')
    expect(found.top).toBe('0')
  })

  it.each(['.rail', '.verdict-panel'])('makes %s sticky below the topbar with its own scroll', (selector) => {
    const sticky = rulesFor(readSrc('App.css'), selector).find((rule) => declarations(rule.body).position === 'sticky')

    const found = declarations(sticky.body)

    expect(found.top).toBe('calc(var(--topbar-h) + var(--space-4))')
    expect(found['overflow-y']).toBe('auto')
    expect(found['max-height']).toBe('calc(100vh - var(--topbar-h) - 2 * var(--space-4))')
    expect(sticky.media).toBe('(min-width: 1144px)')
  })

  it('keeps a focused element out from under the fixed topbar', () => {
    const [root] = rulesFor(readSrc('index.css'), 'html')
    const [body] = rulesFor(readSrc('index.css'), 'body')

    expect(declarations(root.body)['scroll-padding-top']).toBe('calc(var(--topbar-h) + var(--space-4))')
    expect(declarations(body.body)['padding-top']).toBe('var(--topbar-h)')
  })

  it('has no shadow anywhere: panels are separated by a 1px border', () => {
    for (const file of allCssFiles()) {
      expect(readSrc(file), file).not.toMatch(/box-shadow\s*:\s*(?!none)/)
    }
  })

  it('sets no max-width on the shell', () => {
    for (const selector of ['.app-shell', '.workspace']) {
      for (const rule of rulesFor(readSrc('App.css'), selector)) {
        expect(declarations(rule.body)['max-width'], selector).toBeUndefined()
      }
    }
  })
})

describe('drawer-mode strip', () => {
  const css = readSrc('App.css')
  const rule = (selector) => declarations(rulesFor(css, selector)[0].body)
  const DRAWER = ".app-shell[data-layout='drawer']"

  it('lays the Verdict panel out as a two-column strip under the chart', () => {
    const strip = rule(`${DRAWER} .verdict-panel`)

    expect(strip.display).toBe('grid')
    expect(strip['grid-template-columns'].split(' minmax').length).toBe(2)
    expect(strip['row-gap']).toBe('0')
  })

  it('puts the range block at the left, the verdict at the right, and the foot on a full-width row', () => {
    expect(rule(`${DRAWER} .verdict-panel > .range-block`)['grid-column']).toBe('1')
    expect(rule(`${DRAWER} .verdict-panel__foot`)['grid-column']).toBe('1 / -1')
    // Every cell of the panel's wrappers (which dissolve into the grid) sits in the second column.
    const cells = parseRules(css).filter((r) => r.selector.includes(DRAWER) && r.selector.trim().endsWith('> *'))
    expect(cells.map((r) => declarations(r.body)['grid-column'])).toEqual(['2'])
  })

  it('has no third column and no rule for the removed Key tension or Synthesis blocks', () => {
    expect(css).not.toMatch(/verdict-panel__(tension|synthesis)/)
    for (const { selector, body } of parseRules(css)) {
      if (!selector.includes("[data-layout='drawer']")) continue
      expect(declarations(body)['grid-column'] ?? '', selector).not.toBe('3')
    }
  })

  it('puts the result\'s data, time and report lines on full-width rows under the chips, before the foot', () => {
    const meta = rule(`${DRAWER} .verdict-panel__result > .verdict-panel__meta`)

    expect(meta['grid-column']).toBe('1 / -1')
    expect(Number(meta.order)).toBeLessThan(Number(rule(`${DRAWER} .verdict-panel__foot`).order))
  })
})

describe('chart card height', () => {
  const heightAt = (media) => {
    const rule = rulesFor(readSrc('components/ChartPanel/chart-panel.css'), '.chart-panel').find((r) => r.media === media)
    return declarations(rule.body).height
  }

  it('is 240px on phones, --chart-h from 768px, and grows to 56vh from 1144px', () => {
    expect(heightAt('')).toBe('240px')
    expect(heightAt('(min-width: 768px)')).toBe('var(--chart-h)')
    expect(heightAt('(min-width: 1144px)')).toBe('max(var(--chart-h), 56vh)')
  })

  it('draws a failure in the primary ink and never uses a candle colour as a text colour', () => {
    const css = readSrc('components/ChartPanel/chart-panel.css')
    const error = rulesFor(css, ".chart-panel__overlay[data-kind='error'] .chart-panel__message")[0]

    expect(declarations(error.body).color).toBe('var(--ink)')
    for (const rule of parseRules(css)) {
      expect(declarations(rule.body).color ?? '', rule.selector).not.toMatch(/--candle-/)
    }
  })
})

describe('keyboard focus ring', () => {
  it('is one global rule: 2px solid accent with a 2px offset', () => {
    const [rule] = rulesFor(readSrc('index.css'), ':focus-visible')

    const found = declarations(rule.body)

    expect(found.outline).toBe('2px solid var(--accent)')
    expect(found['outline-offset']).toBe('2px')
  })

  it('is never redefined differently by a component stylesheet', () => {
    const offenders = []
    for (const file of allCssFiles()) {
      for (const rule of parseRules(readSrc(file))) {
        if (!rule.selector.includes(':focus-visible')) continue
        const found = declarations(rule.body)
        if (found.outline && found.outline !== '2px solid var(--accent)') offenders.push(`${file} ${rule.selector}`)
        if (found['outline-offset'] && found['outline-offset'] !== '2px') offenders.push(`${file} ${rule.selector}`)
      }
    }

    expect(offenders).toEqual([])
  })

  it('never removes the outline of a focusable control outside a :focus-visible rule', () => {
    for (const file of allCssFiles()) {
      for (const rule of parseRules(readSrc(file))) {
        const found = declarations(rule.body)
        const removes = /^(none|0)$/.test(found.outline ?? '')
        expect(removes && !rule.selector.includes(':focus-visible'), `${file} ${rule.selector}`).toBe(false)
      }
    }
  })
})
