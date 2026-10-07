import { useState } from 'react'
import { Topbar } from './components/Topbar/Topbar'
import { TickerSearch } from './components/Topbar/TickerSearch'
import { Rail } from './components/Rail/Rail'
import { StageHeader } from './components/Stage/StageHeader'
import { ChartPanel } from './components/ChartPanel/ChartPanel'
import { RangeBlock } from './components/VerdictPanel/RangeBlock'
import { VerdictPanel } from './components/VerdictPanel/VerdictPanel'
import { DebateMatrix } from './components/DebateMatrix/DebateMatrix'
import { useDebateAnalysis } from './hooks/useDebateAnalysis'
import { useLayoutMode } from './hooks/useLayoutMode'
import { useRailDrawer } from './hooks/useRailDrawer'
import { useRailRows } from './hooks/useRailRows'
import { useSearchedTickers } from './hooks/useSearchedTickers'
import './App.css'

const RAIL_ID = 'ticker-rail'

// Dashboard assembly: a fixed topbar over three zones, the Rail (the ticker list), the Stage and
// the Verdict panel, all driven by the same `selectedTicker`. Selecting a ticker is also what
// fetches its data: one `/history` and one `/range` request, nothing per unselected ticker.
//
// The layout mode (wide, collapsed, drawer, phone) comes from one hook and decides where a
// component renders; the stylesheet decides how each zone is laid out. DOM order is the reading
// and tab order in every mode.
function App() {
  const layoutMode = useLayoutMode()
  const [selectedTicker, setSelectedTicker] = useState(null)
  // The one search's text: the Rail filters by it, the search itself selects or loads from it.
  const [query, setQuery] = useState('')
  const { searchedTickers, addSearchedTicker } = useSearchedTickers()
  const { allRows } = useRailRows({ searched: searchedTickers })
  const drawer = useRailDrawer({ layoutMode, drawerId: RAIL_ID })

  function handleQueryChange(value) {
    setQuery(value)
    drawer.onQueryChange(value)
  }

  // A row chosen in the drawer closes it and hands focus back to the "Tickers" button; Enter in the
  // search closes it too, but leaves focus where the user is typing.
  function handleRailSelect(ticker) {
    setSelectedTicker(ticker)
    if (drawer.isOpen) drawer.close({ focusButton: true })
  }

  function handleSearchSelect(ticker) {
    setSelectedTicker(ticker)
    if (drawer.isOpen) drawer.close()
  }

  return (
    <div className="app-shell" data-layout={layoutMode}>
      <Topbar
        layoutMode={layoutMode}
        drawerOpen={drawer.isOpen}
        drawerId={RAIL_ID}
        drawerButtonRef={drawer.buttonRef}
        onToggleDrawer={drawer.toggle}
        search={
          <TickerSearch
            rows={allRows}
            value={query}
            onValueChange={handleQueryChange}
            onSelectTicker={handleSearchSelect}
            onLoaded={addSearchedTicker}
            layoutMode={layoutMode}
          />
        }
      />
      {/* Below 768px there is no Rail: the search lists the matches itself. */}
      {layoutMode === 'phone' ? null : (
        <Rail
          id={RAIL_ID}
          mode={layoutMode}
          drawerOpen={drawer.isOpen}
          selectedTicker={selectedTicker}
          onSelectTicker={handleRailSelect}
          searched={searchedTickers}
          query={query}
        />
      )}
      {drawer.isOpen ? <div className="rail-scrim" aria-hidden="true" /> : null}
      <Workspace ticker={selectedTicker} layoutMode={layoutMode} />
    </div>
  )
}

// The Stage (header, chart with its history control, Debate matrix) and the Verdict panel. The
// analysis run is read here, once, and handed to the panel and the matrix, so both show one run and
// one kept result per ticker. Each piece renders in exactly one place per layout mode: on a phone the
// range block sits above the chart and the panel does not repeat it. DOM order is the visual order;
// the drawer-mode strip and the wide column are CSS.
function Workspace({ ticker, layoutMode }) {
  const analysis = useDebateAnalysis(ticker)
  const isPhone = layoutMode === 'phone'

  return (
    <main className="workspace">
      <StageHeader ticker={ticker} />
      {isPhone ? <RangeBlock ticker={ticker} disclaimer /> : null}
      <ChartPanel ticker={ticker} />
      <VerdictPanel ticker={ticker} analysis={analysis} showRange={!isPhone} />
      {/* key: the matrix's own state (the chosen agent tab) starts again for each ticker. */}
      <DebateMatrix key={ticker} ticker={ticker} analysis={analysis} layoutMode={layoutMode} />
    </main>
  )
}

export default App
