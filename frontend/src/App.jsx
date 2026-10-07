import { useState } from 'react'
import { TickerPanel } from './components/TickerPanel/TickerPanel'
import { ChartPanel } from './components/ChartPanel/ChartPanel'
import { RangeDisplay } from './components/RangeDisplay/RangeDisplay'
import { DebatePanel } from './components/DebatePanel/DebatePanel'
import './App.css'

// Dashboard assembly: ticker panel (chips + search), chart panel, range
// display, and the debate panel, all wired to the same `selectedTicker`
// state — selecting a ticker via chip or search drives all three
// ticker-scoped panels at once. Selecting a ticker is also what fetches its
// data: one `/history` and one `/range` request, nothing per unselected chip.
// No top control bar exists here — the reference screenshot's horizonDays/
// adviceStyle/showDisclaimer bar was reviewed and deliberately dropped
// entirely, not relocated (original dashboard design.md Decision 9).
function App() {
  const [selectedTicker, setSelectedTicker] = useState(null)

  return (
    <div className="app-shell">
      <TickerPanel selectedTicker={selectedTicker} onSelectTicker={setSelectedTicker} />
      <div className="app-shell__main">
        {/* Names what the chart/range/debate below belong to — with the
            ticker list now a scroll region, the highlighted chip isn't
            guaranteed to be in view. Always rendered (placeholder text when
            nothing is selected) so selecting a ticker never shifts layout,
            same rule as the panels' own N/A placeholders. */}
        <h2 className="app-shell__ticker" data-empty={selectedTicker ? undefined : ''}>
          {selectedTicker ?? 'No ticker selected'}
        </h2>
        <ChartPanel ticker={selectedTicker} />
        <div className="app-shell__side">
          <RangeDisplay ticker={selectedTicker} />
          {/* key: each ticker gets its own panel state (disclosure level); its run and its kept
              result live in the query cache, so switching away and back loses neither. */}
          <DebatePanel key={selectedTicker} ticker={selectedTicker} />
        </div>
      </div>
    </div>
  )
}

export default App
