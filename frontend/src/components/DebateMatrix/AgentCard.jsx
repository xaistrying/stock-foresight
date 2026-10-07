import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { Inline } from '../Inline'
import { DEGRADED_REASON_TEXT, agentLabel, degradedText, stanceMark } from '../../lib/debateText'

// The text is clamped to five lines of body text by height (not -webkit-line-clamp, whose
// display: -webkit-box drops list semantics in Safari and VoiceOver); "Show more" appears only when the
// text overflows, measured here. An open card keeps its button even though it no longer overflows.
function ClampedBullets({ bullets }) {
  const id = useId()
  const textRef = useRef(null)
  const [expanded, setExpanded] = useState(false)
  const [overflowing, setOverflowing] = useState(false)

  const measure = useCallback(() => {
    const element = textRef.current
    if (element) setOverflowing(element.scrollHeight > element.clientHeight)
  }, [])

  // Measured collapsed only: open, the text is as tall as its content and would read as not overflowing.
  useLayoutEffect(() => {
    if (!expanded) measure()
  }, [expanded, bullets, measure])

  useEffect(() => {
    if (expanded) return undefined
    window.addEventListener('resize', measure)
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    if (observer && textRef.current) observer.observe(textRef.current)
    return () => {
      window.removeEventListener('resize', measure)
      observer?.disconnect()
    }
  }, [expanded, measure])

  return (
    <>
      <div ref={textRef} id={id} className="agent-card__text t-body" data-expanded={expanded || undefined}>
        <ul className="agent-card__list">
          {bullets.map((bullet, index) => (
            <li key={index}>
              <Inline text={bullet} />
            </li>
          ))}
        </ul>
      </div>
      {overflowing || expanded ? (
        <button
          type="button"
          className="agent-card__more t-small"
          aria-expanded={expanded}
          aria-controls={id}
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      ) : null}
    </>
  )
}

/**
 * One agent's position in one round: its label (Rule 5), its stance as an arrow and a word, and its
 * reasoning. An agent that did not answer gets a dashed card reading "Unavailable — did not vote" with
 * the plain reason, and none of its placeholder reasoning.
 */
export function AgentCard({ agentId, position }) {
  const label = agentLabel(agentId)

  if (!position || position.degraded_reason) {
    return (
      <article className="agent-card agent-card--unavailable">
        <h4 className="agent-card__heading t-small">{label}</h4>
        <p className="agent-card__unavailable t-body">Unavailable — did not vote</p>
        <p className="agent-card__reason t-small">
          {position ? degradedText(position) : DEGRADED_REASON_TEXT.agent_error}
        </p>
      </article>
    )
  }

  return (
    <article className="agent-card">
      <div className="agent-card__head">
        <h4 className="agent-card__heading t-small">{label}</h4>
        <span className="agent-card__stance t-small">{stanceMark(position.stance)}</span>
      </div>
      <ClampedBullets bullets={position.reasoning} />
    </article>
  )
}

/** Six empty cells, hidden from assistive technology, while a run is going. */
export function SkeletonCells() {
  return Array.from({ length: 6 }, (_, index) => (
    <div key={index} className="agent-card agent-card--skeleton" aria-hidden="true" />
  ))
}
