import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parseTokens, themeTokens } from './parseTokens'
import { declarations, parseRules, readSrc } from '../test/cssText'

// The design's token file (Claude Design project "Stock Foresight", version 10: light
// --warn-line is #a05a00), copied exactly. A stylesheet edit that drifts from the design
// fails here.
const COLORS = {
  'surface-100': ['#f4f6f9', '#0f1217'],
  'surface-200': ['#ffffff', '#171b22'],
  'surface-300': ['#e9edf2', '#222833'],
  line: ['#d3d9e1', '#2d3541'],
  'line-strong': ['#76808f', '#8892a2'],
  ink: ['#12161d', '#e9ecf1'],
  'ink-muted': ['#4a5463', '#a6b0be'],
  accent: ['#1d4ed8', '#7ea6ff'],
  'on-accent': ['#ffffff', '#0a1430'],
  'up-ink': ['#0a6b46', '#4cc58b'],
  'up-bg': ['#e1f3ea', '#10301f'],
  'down-ink': ['#b3202f', '#ff8591'],
  'down-bg': ['#fbe6e8', '#3a1b21'],
  'candle-up': ['#0f8f5e', '#2fbf80'],
  'candle-down': ['#d1334a', '#f0566b'],
  'band-fill': ['#1d4ed826', '#7ea6ff2e'],
  'warn-bg': ['#fff3d1', '#2e2510'],
  'warn-line': ['#a05a00', '#e3a22f'],
  'warn-ink': ['#4d3000', '#f7e0ad'],
}

const SPACING = { 'space-1': '4px', 'space-2': '8px', 'space-3': '12px', 'space-4': '16px', 'space-5': '24px', 'space-6': '32px' }
const RADIUS = { 'radius-sm': '4px', 'radius-md': '8px' }
const LAYOUT = { 'topbar-h': '52px', 'rail-w': '232px', 'rail-w-min': '56px', 'verdict-w': '340px', 'chart-h': '440px' }

const STYLESHEET = 'styles/tokens.css'
const parsed = parseTokens(readSrc(STYLESHEET))

describe('design tokens stylesheet', () => {
  it.each(Object.entries(COLORS))('defines --%s with the design values in both themes', (name, [light, dark]) => {
    expect(themeTokens(parsed, 'light')[`--${name}`]).toBe(light)
    expect(themeTokens(parsed, 'dark')[`--${name}`]).toBe(dark)
  })

  it.each(Object.entries({ ...SPACING, ...RADIUS, ...LAYOUT }))('defines --%s as %s', (name, value) => {
    expect(parsed.light[`--${name}`]).toBe(value)
  })

  it('declares the dark values twice, under the OS preference and under an explicit choice, and they agree', () => {
    for (const name of Object.keys(COLORS)) {
      expect(parsed.darkByOs[`--${name}`], name).toBe(parsed.darkByChoice[`--${name}`])
    }
  })

  it('does not apply the OS dark values when the user chose light', () => {
    const byOs = parseRules(readSrc(STYLESHEET)).filter((rule) => rule.media === '(prefers-color-scheme: dark)')

    expect(byOs.map((rule) => rule.selector)).toEqual([':root:not([data-theme="light"])'])
  })

  it('sets color-scheme to match each theme', () => {
    const rules = parseRules(readSrc(STYLESHEET))
    const scheme = (selector, media) =>
      declarations(rules.find((rule) => rule.selector === selector && rule.media === media).body)['color-scheme']

    expect(scheme(':root', '')).toBe('light')
    expect(scheme(':root[data-theme="dark"]', '')).toBe('dark')
    expect(scheme(':root:not([data-theme="light"])', '(prefers-color-scheme: dark)')).toBe('dark')
  })

  it('uses the design system font stacks and no web font', () => {
    expect(parsed.light['--font-sans']).toBe('system-ui, -apple-system, "Segoe UI", Roboto, sans-serif')
    expect(parsed.light['--font-mono']).toBe('ui-monospace, SFMono-Regular, Menlo, Consolas, monospace')
    expect(readSrc(STYLESHEET)).not.toMatch(/@font-face/)
  })

  it.each([
    ['t-kpi', '40px', '44px', '700'],
    ['t-ticker', '28px', '32px', '700'],
    ['t-heading', '16px', '22px', '600'],
    ['t-body', '14px', '20px', '400'],
    ['t-small', '12px', '16px', '400'],
    ['t-label', '11px', '14px', '600'],
    ['t-num', '13px', '18px', '500'],
  ])('defines the .%s type style as %s/%s weight %s', (name, size, line, weight) => {
    const rule = parseRules(readSrc(STYLESHEET)).find((r) => r.selector === `.${name}`)

    const found = declarations(rule.body)

    expect(found['font-size']).toBe(size)
    expect(found['line-height']).toBe(line)
    expect(found['font-weight']).toBe(weight)
  })

  it('gives the label style its uppercase tracking and the numeric styles the mono family', () => {
    const rules = parseRules(readSrc(STYLESHEET))
    const of = (name) => declarations(rules.find((r) => r.selector === `.${name}`).body)

    expect(of('t-label')['letter-spacing']).toBe('0.06em')
    expect(of('t-label')['text-transform']).toBe('uppercase')
    for (const name of ['t-kpi', 't-ticker', 't-num']) expect(of(name)['font-family']).toBe('var(--font-mono)')
  })

  it('has no oklch value left: every colour is hex, so the chart and canvas read it unchanged', () => {
    expect(readSrc(STYLESHEET)).not.toMatch(/oklch\(/)
  })
})

describe('index.html', () => {
  const html = readFileSync(join(process.cwd(), 'index.html'), 'utf-8')

  it('links no font host and defines no web font', () => {
    expect(html).not.toMatch(/fonts\.(googleapis|gstatic)\.com/)
    expect(html).not.toMatch(/<link[^>]+rel="(?:stylesheet|preload|preconnect)"[^>]*font/i)
    expect(html).not.toMatch(/@font-face/)
  })

  it('applies a stored theme choice before first paint with a small guarded inline script', () => {
    const inline = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map((m) => m[1])

    expect(inline).toHaveLength(1)
    expect(inline[0]).toContain('localStorage')
    expect(inline[0]).toContain('data-theme')
    expect(inline[0]).toMatch(/try\s*{/)
  })
})
