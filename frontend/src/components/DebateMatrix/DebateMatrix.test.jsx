import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'
import { DebateMatrix } from './DebateMatrix'
import { INLINE_DISCLAIMER, LM_NOTE } from '../../lib/disclaimer'
import { readSrc, rulesFor, declarations } from '../../test/cssText'
import {
  DONE_AT, FORBIDDEN_TEXT, MOCK_RESULT, analysisState, insufficient, oneDegraded, populated, position,
} from '../../test/debateFixtures'

// The matrix reads the run it is given (useDebateAnalysis is called once, in the workspace) and
// needs no query client.
const finished = (result) => analysisState({ result, completedAt: DONE_AT })
const renderMatrix = (analysis = finished(populated()), props = {}) =>
  render(<DebateMatrix ticker="VCB" analysis={analysis} layoutMode="wide" {...props} />)

const AGENTS = ['Technical Signal', 'News Context', 'Macro']
const cardHeadings = () => screen.getAllByRole('heading', { level: 4 }).map((h) => h.textContent)

afterEach(() => {
  delete HTMLElement.prototype.scrollHeight
  delete HTMLElement.prototype.clientHeight
})

describe('Debate matrix: three agents by two rounds', () => {
  it('has two rows headed "Round 1 · Initial positions" and "Round 2 · Responses", three cards each, in agent order', () => {
    renderMatrix()

    expect(screen.getByRole('heading', { name: 'Round 1 · Initial positions' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Round 2 · Responses' })).toBeInTheDocument()
    expect(cardHeadings()).toEqual([...AGENTS, ...AGENTS])
  })

  it('puts the cards in the 3-column grid, one row per round', () => {
    const { container } = renderMatrix()

    const grid = container.querySelector('.debate-grid')
    expect(grid.querySelectorAll('.agent-card')).toHaveLength(6)
    expect(grid.querySelectorAll('.debate-grid__row-label')).toHaveLength(2)
  })

  it('shows each agent\'s stance as an arrow and a word, outside the heading, and its reasoning', () => {
    renderMatrix()

    const round1 = within(screen.getAllByRole('article')[0])
    expect(round1.getByRole('heading', { level: 4, name: 'Technical Signal' })).toBeInTheDocument()
    expect(round1.getByText('↑ Bullish')).toBeInTheDocument()
    expect(round1.getByText('RSI at 62 is bullish')).toBeInTheDocument()
    expect(round1.getByText('MACD positive')).toBeInTheDocument()
    expect(screen.getAllByText('→ Neutral')).toHaveLength(2)
  })

  it('shows Round 1 and Round 2 positions side by side by agent, not as one text column', () => {
    renderMatrix()

    expect(screen.getByText('RSI at 62 is bullish')).toBeInTheDocument()
    expect(screen.getByText('Maintained — RSI still above 55')).toBeInTheDocument()
  })

  it('names the cards exactly Technical Signal, News Context and Macro, and never Market Sentiment', () => {
    const { container } = renderMatrix()

    expect(cardHeadings()).toEqual([...AGENTS, ...AGENTS])
    expect(container.textContent).not.toMatch(/market sentiment/i)
  })

  it('keeps list semantics for the reasoning', () => {
    renderMatrix()

    const card = screen.getAllByRole('article')[0]
    expect(within(card).getByRole('list')).toBeInTheDocument()
    expect(within(card).getAllByRole('listitem')).toHaveLength(2)
  })
})

describe('Debate matrix: clamp and Show more', () => {
  function stubOverflow(scrollHeight, clientHeight) {
    Object.defineProperty(HTMLElement.prototype, 'scrollHeight', { configurable: true, get: () => scrollHeight })
    Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, get: () => clientHeight })
  }

  it('shows no button when the text fits in five lines', () => {
    stubOverflow(80, 100)
    renderMatrix()

    expect(screen.queryByRole('button', { name: /show (more|less)/i })).not.toBeInTheDocument()
  })

  it('shows "Show more" with aria-expanded false for a card whose text is longer, and opens it', async () => {
    stubOverflow(200, 100)
    renderMatrix()

    const [first] = screen.getAllByRole('button', { name: 'Show more' })
    expect(first).toHaveAttribute('aria-expanded', 'false')
    const region = document.getElementById(first.getAttribute('aria-controls'))
    expect(region).toHaveClass('agent-card__text')
    expect(region).not.toHaveAttribute('data-expanded')

    await userEvent.click(first)

    expect(first).toHaveAttribute('aria-expanded', 'true')
    expect(first).toHaveTextContent('Show less')
    expect(region).toHaveAttribute('data-expanded')
  })

  it('keeps the button once the card is open, so it can be closed again', async () => {
    stubOverflow(200, 100)
    renderMatrix()
    const [first] = screen.getAllByRole('button', { name: 'Show more' })

    await userEvent.click(first)
    // Open, the text is as tall as its content, so it no longer measures as overflowing.
    stubOverflow(200, 200)
    fireEvent(window, new Event('resize'))

    expect(screen.getByRole('button', { name: 'Show less' })).toBeInTheDocument()
    stubOverflow(200, 100)
    await userEvent.click(screen.getByRole('button', { name: 'Show less' }))
    expect(screen.getAllByRole('button', { name: 'Show more' }).length).toBeGreaterThan(0)
  })

  it('clamps by height, with list semantics kept (never -webkit-line-clamp)', () => {
    const css = readSrc('components/DebateMatrix/debate-matrix.css')
    const [clamp] = rulesFor(css, '.agent-card__text')

    expect(css).not.toMatch(/-webkit-line-clamp|-webkit-box/)
    expect(declarations(clamp.body)['max-height']).toBe('calc(5 * 20px)')
    expect(declarations(clamp.body).overflow).toBe('hidden')
  })
})

describe('Debate matrix: unavailable agents', () => {
  it('gives a degraded agent an Unavailable card in both rounds, with the plain reason', () => {
    renderMatrix(finished(oneDegraded()))

    expect(screen.getAllByText('Unavailable — did not vote')).toHaveLength(2)
    expect(screen.getAllByText('The language-model analysis failed.')).toHaveLength(2)
    const unavailable = document.querySelectorAll('.agent-card--unavailable')
    expect(unavailable).toHaveLength(2)
    expect(within(unavailable[0]).getByRole('heading', { level: 4, name: 'News Context' })).toBeInTheDocument()
  })

  it.each([
    ['agent_error', 'The agent failed to run.'],
    ['no_input', 'No usable input data.'],
    ['llm_failed', 'The language-model analysis failed.'],
  ])('says "%s" as "%s"', (code, text) => {
    const news = position('news', 'neutral', ['x'], { degraded_reason: code })
    renderMatrix(finished(oneDegraded({ round1: { ...MOCK_RESULT.round1, news }, round2: { ...oneDegraded().round2, news } })))

    expect(screen.getAllByText(text)).toHaveLength(2)
  })

  it('does not print the placeholder reasoning of an agent that did not vote', () => {
    renderMatrix(finished(oneDegraded()))

    expect(screen.queryByText('PLACEHOLDER news')).not.toBeInTheDocument()
  })

  it('after a Round 2 failure shows its Round 1 position normally and an Unavailable card in Round 2, without repeating the bullets', () => {
    const failed = position('technical', 'bull', ['RSI high', 'Round 2 unavailable — Round 1 position kept, not counted in the vote.'], {
      degraded_reason: 'round2_failed',
    })
    renderMatrix(finished(populated({
      round1: { ...MOCK_RESULT.round1, technical: position('technical', 'bull', ['RSI high']) },
      round2: { ...MOCK_RESULT.round2, technical: failed },
      agents_degraded: ['technical'],
    })))

    expect(screen.getAllByText('RSI high')).toHaveLength(1)
    expect(screen.getByText('Round 2 failed; its Round 1 position is shown but not counted.')).toBeInTheDocument()
    expect(screen.getAllByText('Unavailable — did not vote')).toHaveLength(1)
    expect(document.querySelectorAll('.agent-card--unavailable')).toHaveLength(1)
  })

  it('shows the cards, with the Unavailable ones, after an abstention in which agents ran', () => {
    const technical = position('technical', 'bull', ['RSI high'])
    const news = position('news', 'neutral', ['x'], { degraded_reason: 'no_input' })
    const macro = position('macro', 'neutral', ['x'], { degraded_reason: 'agent_error' })
    renderMatrix(finished(insufficient([], {
      eligibility: { eligible: true, reasons: [] },
      agents_degraded: ['news', 'macro'],
      round1: { technical, news, macro },
      round2: { technical, news, macro },
    })))

    expect(screen.getAllByText('RSI high', { selector: 'li' })).toHaveLength(2) // Round 1 and Round 2
    expect(screen.getAllByText('Unavailable — did not vote')).toHaveLength(4)
  })

  it('marks the Unavailable card with a dashed strong border in the stylesheet, and no warn colour', () => {
    const css = readSrc('components/DebateMatrix/debate-matrix.css')
    const [rule] = rulesFor(css, '.agent-card--unavailable')

    expect(declarations(rule.body)['border-style']).toBe('dashed')
    expect(declarations(rule.body)['border-color']).toBe('var(--line-strong)')
    expect(css).not.toMatch(/--warn-/)
  })
})

describe('Debate matrix: states', () => {
  it('before a result shows a one-line prompt under its heading', () => {
    renderMatrix(analysisState())

    expect(screen.getByText("Run Analyse to see each agent's Round 1 and Round 2 positions.")).toBeInTheDocument()
    expect(document.querySelectorAll('.agent-card')).toHaveLength(0)
  })

  it('with no ticker selected shows the same prompt', () => {
    renderMatrix(analysisState(), { ticker: null })

    expect(screen.getByText("Run Analyse to see each agent's Round 1 and Round 2 positions.")).toBeInTheDocument()
  })

  it('while a run is going shows six skeleton cells hidden from assistive technology, and no old cards', () => {
    renderMatrix(analysisState({ isPending: true, startedAt: Date.now(), result: populated(), completedAt: DONE_AT }))

    const skeletons = document.querySelectorAll('.agent-card--skeleton')
    expect(skeletons).toHaveLength(6)
    for (const skeleton of skeletons) {
      expect(skeleton).toHaveAttribute('aria-hidden', 'true')
      expect(skeleton).toHaveTextContent('')
    }
    expect(screen.queryByRole('article')).not.toBeInTheDocument()
  })

  it('after a refusal in which no agent ran, says no debate was run', () => {
    renderMatrix(finished(insufficient(['stale'])))

    expect(screen.getByText(/no debate was run/i)).toBeInTheDocument()
    expect(document.querySelectorAll('.agent-card')).toHaveLength(0)
  })

  it('keeps the kept cards, under the Verdict panel\'s error, after a failed re-run', () => {
    renderMatrix(analysisState({ result: populated(), completedAt: DONE_AT, error: new Error('boom') }))

    expect(screen.getAllByRole('article')).toHaveLength(6)
  })
})

describe('Debate matrix: provenance and disclaimer (Rule 5, Rule 6)', () => {
  it('shows the inline disclaimer under its heading in every state', () => {
    const states = [
      analysisState(),
      analysisState({ isPending: true, startedAt: Date.now() }),
      finished(populated()),
      finished(insufficient(['stale'])),
      analysisState({ error: new Error('boom') }),
    ]

    for (const state of states) {
      const { unmount } = renderMatrix(state)
      expect(screen.getAllByText(INLINE_DISCLAIMER)).toHaveLength(1)
      const heading = screen.getByRole('heading', { level: 2, name: 'Debate' })
      expect(heading.compareDocumentPosition(screen.getByText(INLINE_DISCLAIMER)) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
      unmount()
    }
  })

  it('says the reasoning is written by a language model, above the cards, whenever a result is shown', () => {
    renderMatrix()

    const note = screen.getByText(LM_NOTE)
    expect(note.compareDocumentPosition(screen.getAllByRole('article')[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('does not show the note when there is no result', () => {
    renderMatrix(analysisState())

    expect(screen.queryByText(LM_NOTE)).not.toBeInTheDocument()
  })

  it('does not show Key tension or Synthesis: they belong to the Verdict panel only', () => {
    const { container } = renderMatrix()

    expect(container.textContent).not.toContain(MOCK_RESULT.synthesis.key_tension)
    expect(container.textContent).not.toContain(MOCK_RESULT.synthesis.reasoning)
    expect(screen.queryByRole('heading', { name: /key tension|synthesis/i })).not.toBeInTheDocument()
  })

  it('uses no transaction verb, enum text, Confidence or Market Sentiment in its fixed text', () => {
    const clean = (container) => {
      const text = container.textContent
        .replace(INLINE_DISCLAIMER, '')
        .replace(MOCK_RESULT.round1.technical.reasoning.join(''), '')
      for (const guard of FORBIDDEN_TEXT) expect(text).not.toMatch(guard)
    }
    for (const state of [analysisState(), finished(populated()), finished(insufficient(['stale'])), finished(oneDegraded())]) {
      const { container, unmount } = renderMatrix(state)
      clean(container)
      unmount()
    }
  })
})

describe('Debate matrix: Markdown bold in model text', () => {
  it('renders **text** as bold and shows no asterisks', () => {
    const { container } = renderMatrix(finished(populated({
      round2: {
        ...MOCK_RESULT.round2,
        technical: position('technical', 'bull', ['**RSI at 39.6** is below the midpoint, **and** momentum is weak']),
      },
    })))

    expect(container.textContent).not.toContain('**')
    expect(screen.getByText('RSI at 39.6').tagName).toBe('STRONG')
    expect(screen.getByText('and').tagName).toBe('STRONG')
  })

  it('leaves a lone or unmatched asterisk alone and never treats text as HTML', () => {
    renderMatrix(finished(populated({
      round2: { ...MOCK_RESULT.round2, technical: position('technical', 'bull', ['5 * 3 and **unclosed', '<b>not bold</b>']) },
    })))

    expect(screen.getByText('5 * 3 and **unclosed')).toBeInTheDocument()
    expect(screen.getByText('<b>not bold</b>')).toBeInTheDocument()
  })
})

describe('Debate matrix on a phone: one agent per tab', () => {
  const renderPhone = (analysis = finished(populated())) => renderMatrix(analysis, { layoutMode: 'phone' })
  const tab = (name) => screen.getByRole('tab', { name })

  it('is a tablist named Agents with three tabs, the first selected, wired to its panels', () => {
    renderPhone()

    const list = screen.getByRole('tablist', { name: 'Agents' })
    const tabs = within(list).getAllByRole('tab')
    expect(tabs.map((t) => t.textContent)).toEqual(AGENTS)
    expect(tabs.map((t) => t.getAttribute('aria-selected'))).toEqual(['true', 'false', 'false'])
    for (const t of tabs) expect(document.getElementById(t.getAttribute('aria-controls'))).toHaveAttribute('role', 'tabpanel')
    expect(tabs.map((t) => t.getAttribute('tabindex'))).toEqual(['0', '-1', '-1'])
  })

  it('holds the selected agent\'s Round 1 card above its Round 2 card in the panel', () => {
    renderPhone()

    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveAttribute('aria-labelledby', tab('Technical Signal').id)
    expect(panel).toHaveAttribute('tabindex', '0')
    const headings = within(panel).getAllByRole('heading').map((h) => h.textContent)
    expect(headings).toEqual(['Round 1 · Initial positions', 'Technical Signal', 'Round 2 · Responses', 'Technical Signal'])
    expect(within(panel).getByText('RSI at 62 is bullish')).toBeInTheDocument()
    expect(within(panel).getByText('Maintained — RSI still above 55')).toBeInTheDocument()
    expect(within(panel).queryByText('Positive Q3 earnings reported')).not.toBeInTheDocument()
  })

  it('moves between tabs with Right, Left, Home and End, activating the one it lands on', async () => {
    renderPhone()
    tab('Technical Signal').focus()

    await userEvent.keyboard('{ArrowRight}')
    expect(tab('News Context')).toHaveAttribute('aria-selected', 'true')
    expect(tab('News Context')).toHaveFocus()
    expect(within(screen.getByRole('tabpanel')).getByText('Positive Q3 earnings reported')).toBeInTheDocument()

    await userEvent.keyboard('{End}')
    expect(tab('Macro')).toHaveAttribute('aria-selected', 'true')

    await userEvent.keyboard('{ArrowRight}')
    expect(tab('Technical Signal')).toHaveAttribute('aria-selected', 'true') // wraps

    await userEvent.keyboard('{ArrowLeft}')
    expect(tab('Macro')).toHaveAttribute('aria-selected', 'true') // wraps

    await userEvent.keyboard('{Home}')
    expect(tab('Technical Signal')).toHaveAttribute('aria-selected', 'true')
  })

  it('selects a tab when it is clicked', async () => {
    renderPhone()

    await userEvent.click(tab('Macro'))

    expect(tab('Macro')).toHaveAttribute('aria-selected', 'true')
    expect(within(screen.getByRole('tabpanel')).getByText('VN-Index flat over 20 sessions')).toBeInTheDocument()
  })

  it('says in text that an agent is unavailable, on its tab and in its panel', async () => {
    renderPhone(finished(oneDegraded()))

    expect(screen.getByRole('tab', { name: 'News Context (unavailable)' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('tab', { name: 'News Context (unavailable)' }))
    expect(within(screen.getByRole('tabpanel')).getAllByText('Unavailable — did not vote')).toHaveLength(2)
  })

  it('shows the same prompt before a result, with no tabs to choose among', () => {
    renderPhone(analysisState())

    expect(screen.getByText("Run Analyse to see each agent's Round 1 and Round 2 positions.")).toBeInTheDocument()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
  })

  it('is not a tablist at any wider layout', () => {
    for (const layoutMode of ['wide', 'collapsed', 'drawer']) {
      const { unmount } = renderMatrix(finished(populated()), { layoutMode })
      expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
      unmount()
    }
  })
})
