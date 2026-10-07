// @vitest-environment node
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { FULL_DISCLAIMER, INLINE_DISCLAIMER } from './disclaimer'

const DISCLAIMER_MD = fileURLToPath(new URL('../../../docs/DISCLAIMER.md', import.meta.url))

// The blockquote under `## <heading>`: `>` lines joined with one space, whitespace collapsed.
function section(heading) {
  const lines = readFileSync(DISCLAIMER_MD, 'utf-8').split('\n')
  const start = lines.findIndex(line => line.trim() === `## ${heading}`)
  const quote = lines.slice(start + 1).filter(l => l.trim() !== '').slice(0, 20)
  const text = []
  for (const line of quote) {
    if (!line.startsWith('>')) break
    text.push(line.slice(1))
  }
  return text.join(' ').replace(/\s+/g, ' ').trim()
}

describe('disclaimer copy matches docs/DISCLAIMER.md', () => {
  it('inline version', () => {
    expect(INLINE_DISCLAIMER).toBe(section('Inline version'))
  })

  it('full version', () => {
    expect(FULL_DISCLAIMER).toBe(section('Full disclaimer'))
  })

  it('carries no repo path', () => {
    expect(INLINE_DISCLAIMER).not.toMatch(/DISCLAIMER\.md/)
    expect(FULL_DISCLAIMER).not.toMatch(/DISCLAIMER\.md/)
  })
})
