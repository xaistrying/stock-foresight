import { useState } from 'react'
import { TickerPanel } from './components/TickerPanel/TickerPanel'
import { ChartPanel } from './components/ChartPanel/ChartPanel'
import { PredictionDisplay } from './components/PredictionDisplay/PredictionDisplay'
import { AIInsightPanel } from './components/AIInsightPanel/AIInsightPanel'
import { DebatePanel } from './components/DebatePanel/DebatePanel'
import './App.css'

// VITE_DEBATE_PANEL_ENABLED=true enables the multi-agent DebatePanel.
// When false/unset, the original AIInsightPanel is shown (rollback path).
const DEBATE_PANEL_ENABLED = import.meta.env.VITE_DEBATE_PANEL_ENABLED === 'true'

// Dashboard assembly (tasks.md section 11): ticker panel (chips + search),
// chart panel, prediction display, and the AI insight panel, all wired to
// the same `selectedTicker` state — selecting a ticker via chip or search
// drives all three ticker-scoped panels at once (11.1). No top control bar
// exists here — the reference screenshot's horizonDays/adviceStyle/
// showDisclaimer bar was reviewed and deliberately dropped entirely, not
// relocated (design.md Decision 9, tasks.md 11.3), so there's nothing to
// carry into this layout.
function App() {
  const [selectedTicker, setSelectedTicker] = useState(null)

  return (
    <div className="app-shell">
      <TickerPanel selectedTicker={selectedTicker} onSelectTicker={setSelectedTicker} />
      <div className="app-shell__main">
        {/* Names what the chart/prediction/insight below belong to — with
            the ticker list now a scroll region, the highlighted chip isn't
            guaranteed to be in view. Always rendered (placeholder text when
            nothing is selected) so selecting a ticker never shifts layout,
            same rule as the panels' own N/A placeholders. */}
        <h2 className="app-shell__ticker" data-empty={selectedTicker ? undefined : ''}>
          {selectedTicker ?? 'No ticker selected'}
        </h2>
        <ChartPanel ticker={selectedTicker} />
        <div className="app-shell__side">
          <PredictionDisplay ticker={selectedTicker} />
          {DEBATE_PANEL_ENABLED
            ? <DebatePanel ticker={selectedTicker} />
            : <AIInsightPanel ticker={selectedTicker} />
          }
        </div>
      </div>
    </div>
  )
}

export default App
