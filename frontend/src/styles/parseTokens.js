// Reads the custom properties out of the stylesheet text of the design tokens, per theme.
// Shared by the tests and by `scripts/check-contrast.mjs`, so the numbers they assert on
// are the ones the browser gets.
//
// Light values sit on `:root`. Dark values are declared twice, on purpose: under the
// operating-system preference (unless the user chose light) and under an explicit
// `data-theme="dark"`. Both are returned so a test can check they agree.
const LIGHT = ':root'
const DARK_BY_OS = ':root:not([data-theme="light"])'
const DARK_BY_CHOICE = ':root[data-theme="dark"]'

function customProperties(body) {
  const found = {}
  for (const match of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) found[match[1]] = match[2].trim()
  return found
}

function blocks(text) {
  const stripped = text.replace(/\/\*[\s\S]*?\*\//g, '')
  const out = []
  const walk = (chunk, media) => {
    let i = 0
    while (i < chunk.length) {
      const open = chunk.indexOf('{', i)
      if (open === -1) return
      const prelude = chunk.slice(i, open).trim()
      let depth = 1
      let j = open + 1
      while (j < chunk.length && depth > 0) {
        depth += chunk[j] === '{' ? 1 : chunk[j] === '}' ? -1 : 0
        j += 1
      }
      const body = chunk.slice(open + 1, j - 1)
      if (prelude.startsWith('@media')) walk(body, prelude.replace(/^@media\s*/, ''))
      else if (!prelude.startsWith('@')) out.push({ media, selector: prelude, body })
      i = j
    }
  }
  walk(stripped, '')
  return out
}

export function parseTokens(text) {
  const all = blocks(text)
  const pick = (selector, media) =>
    Object.assign(
      {},
      ...all
        .filter((block) => block.selector === selector && block.media === media)
        .map((block) => customProperties(block.body)),
    )
  return {
    light: pick(LIGHT, ''),
    darkByOs: pick(DARK_BY_OS, '(prefers-color-scheme: dark)'),
    darkByChoice: pick(DARK_BY_CHOICE, ''),
  }
}

/** The theme's full token map: light values with the theme's own overrides on top. */
export function themeTokens(parsed, theme) {
  if (theme === 'light') return parsed.light
  return { ...parsed.light, ...parsed.darkByChoice }
}
