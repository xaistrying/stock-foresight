import { Fragment, useId, useRef, useState } from 'react'
import { INLINE_DISCLAIMER, LM_NOTE } from '../../lib/disclaimer'
import { AGENT_ORDER, agentLabel } from '../../lib/debateText'
import { AgentCard, SkeletonCells } from './AgentCard'
import './debate-matrix.css'

const ROUNDS = [
  { key: 'round1', title: 'Round 1 · Initial positions' },
  { key: 'round2', title: 'Round 2 · Responses' },
]

const hasPositions = (result) => Object.keys(result.round1 ?? {}).length + Object.keys(result.round2 ?? {}).length > 0

// Three agent columns by two round rows, the cards aligned by row, so a reader scans one agent top to
// bottom or one round left to right. Never one scrolling text column.
function MatrixGrid({ result }) {
  return (
    <div className="debate-grid">
      {ROUNDS.map(({ key, title }) => (
        <Fragment key={key}>
          <h3 className="debate-grid__row-label t-label">{title}</h3>
          {AGENT_ORDER.map((id) => (
            <AgentCard key={id} agentId={id} position={result[key]?.[id]} />
          ))}
        </Fragment>
      ))}
    </div>
  )
}

// Below 768px: one tab per agent, Round 1 above Round 2 inside it. Left and Right move between the
// tabs (wrapping), Home and End go to the ends, and the tab moved to is the one shown.
function AgentTabs({ result }) {
  const base = useId()
  const [selected, setSelected] = useState(0)
  const tabs = useRef([])
  const last = AGENT_ORDER.length - 1

  function handleKeyDown(event) {
    const moves = {
      ArrowRight: selected === last ? 0 : selected + 1,
      ArrowLeft: selected === 0 ? last : selected - 1,
      Home: 0,
      End: last,
    }
    const next = moves[event.key]
    if (next === undefined) return
    event.preventDefault()
    setSelected(next)
    tabs.current[next]?.focus()
  }

  return (
    <div className="debate-tabs">
      <div role="tablist" aria-label="Agents" className="debate-tabs__list" onKeyDown={handleKeyDown}>
        {AGENT_ORDER.map((id, index) => (
          <button
            key={id}
            ref={(element) => {
              tabs.current[index] = element
            }}
            type="button"
            role="tab"
            id={`${base}-tab-${index}`}
            className="debate-tabs__tab t-small"
            aria-selected={index === selected}
            aria-controls={`${base}-panel-${index}`}
            tabIndex={index === selected ? 0 : -1}
            onClick={() => setSelected(index)}
          >
            {agentLabel(id)}
            {result.round2?.[id]?.degraded_reason ? ' (unavailable)' : ''}
          </button>
        ))}
      </div>
      {AGENT_ORDER.map((id, index) => (
        <div
          key={id}
          role="tabpanel"
          id={`${base}-panel-${index}`}
          aria-labelledby={`${base}-tab-${index}`}
          tabIndex={0}
          hidden={index !== selected}
          className="debate-tabs__panel"
        >
          {ROUNDS.map(({ key, title }) => (
            <Fragment key={key}>
              <h3 className="debate-grid__row-label t-label">{title}</h3>
              <AgentCard agentId={id} position={result[key]?.[id]} />
            </Fragment>
          ))}
        </div>
      ))}
    </div>
  )
}

/**
 * The Debate matrix, below the chart: three agents (Technical Signal, News Context, Macro, in that
 * order) by two rounds, one card per cell. It reads the same run the Verdict panel reads (`analysis`),
 * so both show one result from one request, and it does not show Key tension or Synthesis: those are
 * the Verdict panel's.
 *
 * It shows agent reasoning outside the panel that carries the disclaimer, so it repeats the inline
 * disclaimer under its heading in every state (Rule 6) and says the reasoning is written by a language
 * model (Rule 5). Before a result: a one-line prompt. While a run is going: six empty cells. After a
 * refusal in which no agent ran: that no debate was run. At 768px and up the three columns stay; below
 * it the agents are tabs.
 *
 * @param {{ticker: string|null, analysis: object, layoutMode: 'wide'|'collapsed'|'drawer'|'phone'}} props
 */
export function DebateMatrix({ ticker, analysis, layoutMode }) {
  const { isPending, result } = analysis
  const showCards = !isPending && Boolean(result) && hasPositions(result)

  let body
  if (isPending) {
    body = (
      <div className="debate-grid">
        <SkeletonCells />
      </div>
    )
  } else if (!result) {
    body = (
      <p className="debate-matrix__message t-body">
        Run Analyse to see each agent&apos;s Round 1 and Round 2 positions.
      </p>
    )
  } else if (!hasPositions(result)) {
    body = (
      <p className="debate-matrix__message t-body">
        No debate was run: the stored data for {ticker} did not support an analysis. See the Verdict panel for why.
      </p>
    )
  } else {
    body = layoutMode === 'phone' ? <AgentTabs result={result} /> : <MatrixGrid result={result} />
  }

  return (
    <section className="debate-matrix" aria-label="Debate">
      <h2 className="debate-matrix__heading t-heading">Debate</h2>
      <p className="debate-matrix__disclaimer t-small">{INLINE_DISCLAIMER}</p>
      {showCards ? <p className="debate-matrix__lm-note t-small">{LM_NOTE}</p> : null}
      {body}
    </section>
  )
}
