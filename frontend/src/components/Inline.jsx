// Model text often carries Markdown bold (**like this**). Shown as bold, never as raw asterisks, and
// without HTML: the text is split and rebuilt as React nodes, so nothing in it is interpreted.
const BOLD = /\*\*([^*]+)\*\*/g

export function Inline({ text }) {
  const parts = text.split(BOLD) // odd indexes are the bold spans
  return parts.map((part, i) => (i % 2 === 1 ? <strong key={i}>{part}</strong> : part))
}
