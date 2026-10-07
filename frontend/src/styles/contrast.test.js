import { spawnSync } from 'node:child_process'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { PAIRS, checkContrast, contrastRatio, formatRows } from '../../scripts/check-contrast.mjs'
import { allCssFiles, declarations, parseRules, readSrc } from '../test/cssText'

const css = readSrc('styles/tokens.css')

describe('token colour pairs', () => {
  it('computes WCAG 2 ratios correctly', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 5)
    expect(contrastRatio('#ffffff', '#ffffff')).toBeCloseTo(1, 5)
    expect(contrastRatio('#767676', '#ffffff')).toBeCloseTo(4.54, 2)
  })

  it('checks every pair in both themes, from the real stylesheet', () => {
    const rows = checkContrast(css)

    expect(rows).toHaveLength(PAIRS.length * 2)
    expect(new Set(rows.map((row) => row.theme))).toEqual(new Set(['light', 'dark']))
  })

  it('meets 4.5:1 for text and 3:1 for marks in both themes', () => {
    const failures = checkContrast(css).filter((row) => !row.passes)

    expect(failures.map((row) => `${row.theme}: ${row.foreground} on ${row.background} = ${row.ratio.toFixed(2)}`)).toEqual([])
  })

  it('covers the pairs the design names: Key tension label, the band bounds and the focus ring', () => {
    const named = PAIRS.map(([foreground, background]) => `${foreground} on ${background}`)

    expect(named).toContain('warn-line on warn-bg')
    expect(named).toContain('accent on surface-200')
    for (const surface of ['surface-100', 'surface-200', 'surface-300']) expect(named).toContain(`accent on ${surface}`)
  })

  it('has its lowest text pair at about 4.80:1 and its lowest mark at about 3.69:1, as the design records', () => {
    const rows = checkContrast(css)

    expect(Math.min(...rows.filter((r) => r.required === 4.5).map((r) => r.ratio))).toBeCloseTo(4.8, 2)
    expect(Math.min(...rows.filter((r) => r.required === 3).map((r) => r.ratio))).toBeCloseTo(3.69, 2)
  })

  it('fails, naming the pair and the theme, when a token edit drops a pair below its requirement', () => {
    const broken = css.replace('--ink-muted: #4a5463;', '--ink-muted: #b9c0cb;')

    const failures = checkContrast(broken).filter((row) => !row.passes)

    expect(failures.some((row) => row.theme === 'light' && row.foreground === 'ink-muted' && row.background === 'surface-100')).toBe(true)
    expect(formatRows(failures)).toMatch(/FAIL\s+light\s+\d\.\d\d\s+>= 4\.5\s+ink-muted on surface-100/)
  })

  it('treats the dark theme as its own set of values', () => {
    const broken = css.replaceAll('--warn-line: #e3a22f;', '--warn-line: #3a2a05;')

    const failures = checkContrast(broken).filter((row) => !row.passes)

    expect(failures.every((row) => row.theme === 'dark')).toBe(true)
    expect(failures.map((row) => row.foreground)).toContain('warn-line')
  })

  it('is run by `node scripts/check-contrast.mjs`, which exits 0 when every pair holds', () => {
    const result = spawnSync(process.execPath, [join(process.cwd(), 'scripts/check-contrast.mjs')], { encoding: 'utf-8' })

    expect(result.status).toBe(0)
    expect(result.stdout).toContain('lowest text pair')
  })
})

describe('candle colours are marks, never text', () => {
  it('is used as a text colour by no stylesheet', () => {
    const offenders = []
    for (const file of allCssFiles()) {
      for (const rule of parseRules(readSrc(file))) {
        const found = declarations(rule.body)
        if (/--candle-/.test(found.color ?? '')) offenders.push(`${file} ${rule.selector}`)
      }
    }

    expect(offenders).toEqual([])
  })
})
