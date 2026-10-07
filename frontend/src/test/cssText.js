// Test helper: read a stylesheet and answer small questions about its rules, for the
// layout properties jsdom cannot compute (sticky, widths, breakpoints, focus outline).
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

export const SRC = join(process.cwd(), 'src')

export function readSrc(relative) {
  return readFileSync(join(SRC, relative), 'utf-8')
}

export function stripComments(css) {
  return css.replace(/\/\*[\s\S]*?\*\//g, '')
}

/** Every `.css` file under `src`, as paths relative to it. */
export function allCssFiles(dir = SRC, base = '') {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name)
    const relative = base ? `${base}/${name}` : name
    if (statSync(full).isDirectory()) return allCssFiles(full, relative)
    return name.endsWith('.css') ? [relative] : []
  })
}

/**
 * Flat list of `{ media, selector, body }`, one per rule, with `media` the text of the
 * enclosing `@media (...)` (or '') — one level of nesting, which is all these files use.
 */
export function parseRules(css) {
  const text = stripComments(css)
  const rules = []
  const walk = (chunk, media) => {
    let i = 0
    while (i < chunk.length) {
      const open = chunk.indexOf('{', i)
      if (open === -1) break
      const prelude = chunk.slice(i, open).trim()
      let depth = 1
      let j = open + 1
      while (j < chunk.length && depth > 0) {
        if (chunk[j] === '{') depth += 1
        else if (chunk[j] === '}') depth -= 1
        j += 1
      }
      const body = chunk.slice(open + 1, j - 1)
      if (prelude.startsWith('@media')) walk(body, prelude.replace(/^@media\s*/, ''))
      else if (!prelude.startsWith('@')) rules.push({ media, selector: prelude, body })
      i = j
    }
  }
  walk(text, '')
  return rules
}

/** Declarations of a rule body as `{ property: value }`. */
export function declarations(body) {
  return Object.fromEntries(
    body
      .split(';')
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => {
        const colon = part.indexOf(':')
        return [part.slice(0, colon).trim(), part.slice(colon + 1).trim()]
      }),
  )
}

/** Rules whose comma-separated selector list contains exactly `selector`. */
export function rulesFor(css, selector) {
  return parseRules(css).filter((rule) =>
    rule.selector.split(',').some((part) => part.trim() === selector),
  )
}

/** The `@media` width numbers a stylesheet uses, e.g. [768, 1144, 1440]. */
export function mediaWidths(css) {
  const found = new Set()
  for (const { media } of parseRules(css)) {
    for (const match of media.matchAll(/(?:min|max)-width:\s*(\d+)px/g)) found.add(Number(match[1]))
  }
  return [...found].sort((a, b) => a - b)
}
