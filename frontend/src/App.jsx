import { useState } from 'react'
import { TickerPanel } from './components/TickerPanel/TickerPanel'
import { ChartPanel } from './components/ChartPanel/ChartPanel'
import { PredictionDisplay } from './components/PredictionDisplay/PredictionDisplay'
import { AIInsightPanel } from './components/AIInsightPanel/AIInsightPanel'
import './App.css'

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
        <ChartPanel ticker={selectedTicker} />
        <div className="app-shell__side">
          <PredictionDisplay ticker={selectedTicker} />
          <AIInsightPanel ticker={selectedTicker} />
        </div>
      </div>
    </div>
  )
}

export default App
