## ADDED Requirements

### Requirement: Dashboard layout is a fixed topbar over a Rail, a Stage and a sticky Verdict panel
The dashboard SHALL render a fixed topbar (brand, the one ticker search, a theme toggle) over exactly three zones: the **Rail** (the ticker list), the **Stage** (the symbol header, the chart history control, the chart card and the Debate matrix) and the **Verdict** panel. No fourth zone SHALL sit beside them, and no ticker list SHALL sit above the chart. At 1440 px and up the zones SHALL sit side by side with the Rail `--rail-w` (232 px) wide and sticky, and the Verdict panel `--verdict-w` (340 px) wide and sticky; each sticky zone SHALL scroll on its own and sit `--topbar-h` (52 px) plus `--space-4` below the top of the viewport. The chart card SHALL be at least `--chart-h` (440 px) high at 1144 px and up, growing to 56vh. Page padding SHALL be `--space-6` at 1440 px and up and `--space-4` below, with `--space-4` between zones and `--space-5` between sections inside the Stage. The page SHALL expose the landmarks `header`, `nav` (the Rail), `main` and `aside` (the Verdict panel) and one `h1`, the selected ticker (or "No ticker selected").

#### Scenario: Three zones under one topbar
- **WHEN** the dashboard renders at 1440 px
- **THEN** the topbar holds the brand, one search input and one theme toggle, and the page holds one Rail, one Stage and one Verdict panel and no other zone

#### Scenario: Ticker list is never above the chart
- **WHEN** the dashboard renders at any width
- **THEN** no ticker tile grid or chip group is placed above the chart; the Rail is a vertical list, a collapsed vertical strip, a drawer, or (on phones) the search's listbox

#### Scenario: Sticky zones scroll on their own
- **WHEN** the Stage is taller than the viewport and the user scrolls it
- **THEN** the Rail and the Verdict panel stay in view, each with its own overflow scroll, below the fixed topbar

#### Scenario: A focused control is not hidden under the topbar
- **WHEN** keyboard focus moves to an element near the top of the scrolled page
- **THEN** the page scrolls so the element is not covered by the fixed topbar

### Requirement: Layout mode follows the viewport width and each component renders in one place
The dashboard SHALL choose one layout mode from the viewport width: `wide` (1440 px and up), `collapsed` (1144 to 1439 px), `drawer` (768 to 1143 px) or `phone` (below 768 px). The breakpoints in the stylesheet and in the script that selects the mode SHALL be equal, and a test SHALL fail if they differ. In `collapsed` mode the Rail SHALL be `--rail-w-min` (56 px) wide and show symbols only. In `drawer` mode the Rail SHALL be a drawer opened from a "Tickers" button in the topbar, and the Verdict panel SHALL be a full-width strip between the chart and the Debate matrix: the typical move and its range check at the left, the verdict with Agreement and the stance chips in the middle, Key tension at the right, and Synthesis in a full-width row under them. In `phone` mode the page SHALL be one column ordered: the typical move and its range check, the chart (240 px high, the chart history control above it), the verdict with Agreement, Key tension, Synthesis, then the Debate matrix as three tabs. The Debate matrix SHALL keep three columns down to 768 px, each at least 220 px wide. A component whose content is the only place a figure may appear (the range check, Key tension, the disclaimer) SHALL be rendered once in every mode, never twice with one hidden.

#### Scenario: Collapsed Rail keeps three Debate columns
- **WHEN** the viewport is 1144 px wide with a ticker selected and a result present
- **THEN** the Rail is 56 px wide, the Verdict panel is 340 px wide, and the Debate matrix shows three agent columns each at least 220 px wide

#### Scenario: Drawer mode moves the Verdict panel between chart and Debate
- **WHEN** the viewport is 900 px wide
- **THEN** the Verdict panel is a strip in the flow after the chart and before the Debate matrix, and the Rail is reachable only through the topbar "Tickers" button

#### Scenario: Phone mode puts the typical move first
- **WHEN** the viewport is 390 px wide and a ticker with a served band is selected
- **THEN** the typical 5-session move and its range check appear before the chart in reading order, and the Debate matrix is a tablist of three agent tabs

#### Scenario: One copy of each single-place element
- **WHEN** the dashboard renders in each of the four modes with a result present
- **THEN** the range check text, the Key tension text and the inline disclaimer each occur exactly once in the Verdict panel in every mode

#### Scenario: Breakpoints cannot drift
- **WHEN** the breakpoint constants in the layout script are compared with the `@media` widths in the layout stylesheet
- **THEN** they are equal, and the test fails if either changes alone

### Requirement: Layout uses the full viewport width
The dashboard SHALL use the whole viewport width and SHALL stay balanced: the app shell and every zone SHALL have no `max-width`, SHALL NOT be centred between empty margins, and the left and right page padding SHALL be equal (`--space-6` at 1440 px and up, `--space-4` below). The Rail and the Verdict panel SHALL keep their token widths (`--rail-w` 232 px, `--verdict-w` 340 px) and the Stage SHALL take every remaining pixel, so on wider screens the chart and the Debate cards grow. The chart's candles, volume bars and range band SHALL be spread across the chart card from edge to edge of its plot, re-laid out when the card's width changes, with the band's `±X.XX%` label inside the card. A zone with less content than its height SHALL be top-aligned or stretched, never floated with empty space around it. The Debate matrix's three columns SHALL be equal in width.

#### Scenario: Three zones fill 1440 px
- **WHEN** the viewport is 1440 px wide
- **THEN** the Rail (232 px), the Stage (772 px) and the Verdict panel (340 px) plus the two 16 px gutters and the two 32 px paddings add up to 1440 px, with no further horizontal space

#### Scenario: Wider screens give the extra width to the Stage
- **WHEN** the viewport is 1920 px and then 2560 px wide
- **THEN** the Rail stays 232 px and the Verdict panel 340 px, the Stage is 1252 px and then 1892 px, the page paddings are both 32 px, and no zone has an empty margin beside it

#### Scenario: No cap or centring
- **WHEN** the stylesheets are inspected
- **THEN** the app shell and the zone containers declare no `max-width` and no automatic horizontal margin, and the left and right padding values are the same

#### Scenario: Chart plot fills the card
- **WHEN** the chart card is 772, 1252 and 1892 px wide and the 3M window is active
- **THEN** the same 60 sessions are shown at each width, spread over the plot from its left edge to its right edge (the price scale excluded), the volume bars use the same time axis, and the band's label is entirely inside the card

#### Scenario: Debate columns stay equal
- **WHEN** the viewport is 1440, 1920 or 2560 px wide
- **THEN** the three Debate columns have equal widths, each (Stage width minus two 12 px gaps) divided by three

#### Scenario: Resize re-lays out the chart
- **WHEN** the chart card's width changes and the user has not zoomed or panned since the window was applied
- **THEN** the active history window is applied again so the plot is still filled edge to edge

### Requirement: Rail rows show the symbol, loaded age, a refresh control and an ineligibility tag, and no direction cue
The Rail SHALL render one row per ticker as a vertical list. A row SHALL show the symbol in the monospace numeric style, then "Loaded Nd ago" (or the shorter minute and hour forms already used) in small muted text, then a Refresh control, then, only when the ticker cannot be analysed, one short text tag naming the first reason in the fixed reason order: `delisted` "Delisted", `insufficient_history` "Short history", `stale` "Stale", `near_gap` "Data gaps", `hard_quality_flag` "Quality flag", `indicators_missing` "No indicators". The row's accessible name and its `title` SHALL list every reason. The tag SHALL come from the catalog entry's `eligibility` and SHALL NOT be derived in the browser from an age or a date. The Refresh control SHALL be visible on hover and on keyboard focus within the row, always visible when the device cannot hover, always in the tab order, and SHALL call `POST /tickers/{ticker}/load` as the shipped Refresh does (disabled while that ticker's load is in flight, the same per-status messages). The selected row SHALL be marked with `aria-current="true"`, the inset fill and a 2 px accent outline, not by colour alone. A row SHALL NOT show a stance chip, a return, a percentage, a status dot or any up or down mark.

#### Scenario: Row content for an eligible, loaded ticker
- **WHEN** a catalog entry has `eligibility.eligible` true and `last_loaded_at` 28 days ago
- **THEN** its row shows the symbol and "Loaded 28d ago" and no tag

#### Scenario: Ineligible ticker is tagged in text
- **WHEN** a catalog entry has `eligibility.reasons` of `["delisted", "stale"]`
- **THEN** its row shows the text tag "Delisted", and its accessible name and title mention both "Delisted" and "Stale"

#### Scenario: Missing eligibility means no tag
- **WHEN** a catalog entry has `eligibility` null or absent
- **THEN** its row shows no tag and no age claim beyond "Loaded Nd ago"

#### Scenario: Refresh is reachable without hover
- **WHEN** a user tabs to a row
- **THEN** the Refresh control is visible and focusable, and activating it calls the load endpoint without changing the selection

#### Scenario: No direction cue on a row
- **WHEN** any row is rendered in any state
- **THEN** it contains no `↑`, `↓`, `▲`, `▼`, no percentage, no element with a status-dot role or class, and no up or down colour

### Requirement: Rail lists the loaded catalog, sorted by Symbol or Last loaded, and filtered by the topbar search
The Rail SHALL list every `GET /tickers` entry with `loaded` true, plus every symbol loaded through the search during the session that the catalog does not list, in one list (no separate "Searched tickers" group or heading). Which tickers the Rail lists beyond that is a pending owner decision (Watchlist curation) and SHALL NOT be changed by this requirement. The Rail SHALL offer a sort control with exactly two options, **Symbol** (A to Z, the default) and **Last loaded** (most recently loaded first; entries with no load time last; ties by symbol), a native `select` named "Sort tickers". The Rail SHALL contain no search or filter input of its own. When the topbar search holds text, the Rail SHALL show only the rows whose symbol contains it, case-insensitively, and SHALL announce the matching count in a polite live region. When no row matches, the Rail SHALL say so and that Enter loads the symbol. A symbol loaded through the search that the catalog does not list SHALL show "Loaded just now" from the client clock at load time and no tag.

#### Scenario: Loaded catalog entries only
- **WHEN** the catalog holds 208 entries of which 207 are loaded
- **THEN** the Rail shows 207 rows

#### Scenario: Sort by last loaded
- **WHEN** the user chooses "Last loaded"
- **THEN** the rows are ordered by `last_loaded_at` descending, with rows without a load time last, and the order of equal times is by symbol

#### Scenario: Filter narrows the Rail only
- **WHEN** the user types "CB" in the topbar search
- **THEN** only rows whose symbol contains "CB" remain, the live region says how many of how many, and the selected ticker is unchanged

#### Scenario: No second search in the Rail
- **WHEN** the Rail renders at any width
- **THEN** it contains no text input, search input or combobox of its own

#### Scenario: Searched-in symbol joins the same list
- **WHEN** a symbol that the catalog does not list loads successfully through the search
- **THEN** it appears as an ordinary row in the same Rail, sorted by the current sort, with no "Searched tickers" heading anywhere

### Requirement: One topbar search filters the Rail and selects or loads a symbol
The dashboard SHALL have one ticker search, in the topbar, and no other. It SHALL read "Search ticker" as its placeholder and filter by symbol only. Pressing Enter with a symbol that is in the Rail SHALL select it without any request and clear the input. Pressing Enter with any other symbol SHALL call `POST /tickers/{symbol}/load`, and on `status: "ok"` select that symbol and clear the input; while the request runs the input SHALL be disabled with `aria-busy` and a status line SHALL say it is loading. There SHALL be no "Load" button. A load that does not complete with `ok` SHALL show a message under the input, keep the typed value and select nothing, with a distinct message for `rate_limited` ("Rate-limited by the data provider — try again in a moment."), `invalid_symbol` (the symbol "isn't a recognized ticker symbol"), `no_data` (no data is available for the symbol and retrying is unlikely to help), a non-2xx error ("Something went wrong loading this ticker — please try again.") and a network failure ("Network error — could not reach the server."); each SHALL be announced as an alert. In `phone` mode the input SHALL be an ARIA combobox that lists the matches in a listbox (`role="combobox"` with `aria-expanded`, `aria-controls` and `aria-activedescendant`; `role="listbox"` and `role="option"`), Down and Up SHALL move the active option, Enter SHALL select it, Escape SHALL close the list, and a symbol with no match SHALL be offered as a single option "Load SYM". Outside `phone` mode the input SHALL NOT carry the combobox role.

#### Scenario: Enter selects a symbol that is in the Rail
- **WHEN** the user types "tcb" and presses Enter and TCB is a row in the Rail
- **THEN** TCB is selected, no `/load` request is made and the input is empty

#### Scenario: Enter on an unknown symbol loads it, then selects it
- **WHEN** the user types "ZZZ" and presses Enter and ZZZ is not a Rail row
- **THEN** `POST /tickers/ZZZ/load` is called, and when it answers `ok` ZZZ is selected and joins the Rail

#### Scenario: Each failed load has its own message
- **WHEN** a load answers `rate_limited`, then `invalid_symbol`, then `no_data`
- **THEN** three different messages are shown, none selects a ticker, and none is the generic "Something went wrong" message

#### Scenario: Transport failure is not a status
- **WHEN** the load request fails with a non-2xx response that carries no recognised status, and then with a network error
- **THEN** the first shows "Something went wrong loading this ticker — please try again." and the second shows "Network error — could not reach the server."

#### Scenario: No Load button and no second search
- **WHEN** the dashboard renders at any width
- **THEN** there is exactly one search input on the page and no button named "Load"

#### Scenario: Phone combobox semantics
- **WHEN** the viewport is 390 px wide, the user types "V" and presses Down twice
- **THEN** the input has `role="combobox"` with `aria-expanded="true"`, the listbox shows the matching rows, `aria-activedescendant` names the second option, and Enter selects it

#### Scenario: Not a combobox at wider widths
- **WHEN** the viewport is 1440 px wide
- **THEN** the search input has no combobox role and opens no popup

### Requirement: Collapsed Rail and drawer are operable without hover and without trapping focus
In `collapsed` mode a button at the top of the Rail (`aria-expanded`, `aria-controls`) SHALL pin the Rail open as an overlay over the Stage; hovering the Rail or moving keyboard focus into it SHALL also expand it; Escape SHALL close a pinned overlay and return focus to that button; choosing a row SHALL close a pinned overlay. The overlay SHALL NOT be modal: it SHALL NOT trap focus and SHALL NOT make the Stage or the topbar inert. In `drawer` mode the topbar "Tickers" button (`aria-expanded`, `aria-controls`) SHALL open a non-modal drawer (`aria-modal` SHALL NOT be set) so the topbar search stays usable while it is open; typing a non-empty value into the search SHALL open it without moving focus; Escape, choosing a row, or a click outside SHALL close it, and the first two SHALL return focus to the button. Neither the overlay nor the drawer SHALL animate. A row's accessible name SHALL be the same whether the Rail is shown collapsed or expanded.

#### Scenario: Keyboard-only expand and close
- **WHEN** a keyboard user activates the collapsed Rail's toggle, then presses Escape
- **THEN** the overlay opens with `aria-expanded="true"`, then closes with focus back on the toggle

#### Scenario: Hover is not required
- **WHEN** a touch user taps the toggle in `collapsed` mode
- **THEN** the full rows, with their Refresh controls, are shown until a row is chosen or the toggle is activated again

#### Scenario: The drawer does not block the search
- **WHEN** the drawer is open in `drawer` mode
- **THEN** the topbar search input accepts typing and the drawer's rows filter as the user types

#### Scenario: Typing opens the drawer
- **WHEN** the drawer is closed and the user types into the search in `drawer` mode
- **THEN** the drawer opens, focus stays in the input, and the filtered rows are visible

#### Scenario: Selecting from the drawer closes it
- **WHEN** a row is chosen in the open drawer
- **THEN** the ticker is selected, the drawer closes and focus returns to the "Tickers" button

### Requirement: Stage header states the ticker, last close and the data date and age before any debate runs
The Stage header SHALL show the selected ticker in the ticker style (the page's `h1`), the last close from `GET /tickers/{ticker}/history`, and the date of the last session used with its age in sessions, as "As of 2026-10-06 · current" at age 0 and "As of 2026-09-07 · 21 sessions old" otherwise ("1 session old" at age 1), without a debate having run. The date SHALL be the `as_of` of `GET /tickers/{ticker}/range` (else the last history row's date). The age SHALL be `eligibility.age_sessions` of the ticker's catalog entry; for a ticker with no catalog entry the header SHALL show the date without an age and SHALL NOT estimate one. When the ticker's `eligibility.reasons` (or, for a ticker with no catalog entry, `/range`'s `reasons`) contains `stale`, the header SHALL say "Stale" in text beside the date; the dashboard SHALL NOT compare an age with a threshold of its own. A stale or ineligible ticker SHALL still show its chart. With no ticker selected the header SHALL read "No ticker selected" and show placeholders in the same shape. The header SHALL NOT use colour alone and SHALL show no status dot.

#### Scenario: Current data
- **WHEN** the selected ticker's `eligibility.age_sessions` is 0 and `/range` has `as_of` "2026-10-06"
- **THEN** the header reads "As of 2026-10-06 · current"

#### Scenario: Stale data
- **WHEN** `eligibility.reasons` contains `stale` and `age_sessions` is 21 with `as_of` "2026-09-07"
- **THEN** the header reads "As of 2026-09-07 · 21 sessions old" with the text "Stale" beside it, and the chart still renders

#### Scenario: Available before any debate
- **WHEN** a ticker is selected and no analysis has been started
- **THEN** the header already shows the last close and the "As of" line, and no `POST /debate` has been issued

#### Scenario: Searched-in ticker has no age
- **WHEN** the selected ticker has no catalog entry
- **THEN** the header shows "As of {date}" with no session count and no invented age

#### Scenario: Header after a refresh
- **WHEN** a Refresh for the selected ticker completes with `status: "ok"`
- **THEN** the catalog, history and range are refetched and the header's date, age and "Stale" text update without a page reload

### Requirement: Chart history control sets the visible window in sessions
Above the chart card the Stage SHALL show a group named "Chart history" of three toggle buttons (`aria-pressed`): **3M** (the last 60 sessions, the opening view), **1Y** (the last 250 sessions) and **All** (every row `/history` served, at most 750). Windows SHALL be counted in sessions (rows), never calendar days (Rule 1: the unit of the horizon is the trading session). Choosing a window SHALL change the visible range only and SHALL NOT issue a request. A button SHALL be disabled when the ticker has fewer rows than the window needs (3M: 60, 1Y: 250); All SHALL be disabled when the ticker has no more rows than 1Y shows (250 or fewer). Reset zoom SHALL restore the active window, auto-scale and the pane split. Selecting another ticker SHALL return to 3M, falling back to the widest enabled window, and to fitting all rows when fewer than 60 exist.

#### Scenario: Opening view is the last 60 sessions
- **WHEN** a ticker with 750 rows is selected
- **THEN** "3M" is pressed and the visible logical range covers the last 60 rows plus the band's right margin

#### Scenario: Changing the window issues no request
- **WHEN** the user presses "1Y" and then "All"
- **THEN** the visible range changes and no request is made

#### Scenario: A short history disables the windows it cannot fill
- **WHEN** the ticker has 200 rows
- **THEN** "1Y" and "All" are disabled and "3M" is enabled

#### Scenario: All never hides stored history
- **WHEN** the ticker has 600 rows
- **THEN** "All" is enabled and shows all 600

#### Scenario: Reset zoom keeps the chosen window
- **WHEN** "1Y" is pressed, the user pans, then activates Reset zoom
- **THEN** the visible range returns to the last 250 sessions and "1Y" stays pressed

### Requirement: Chart panel renders OHLCV, volume and the 5-session range band, with the band label and no derived indicator
The chart panel SHALL render candles from `GET /tickers/{ticker}/history`, and MAY render that response's volume field as a histogram under the candles inside the same card; both are raw OHLCV data, not derived indicators. The chart SHALL NOT render any derived technical indicator overlay (Ichimoku, RSI, MACD, Bollinger, ATR, OBV). The chart MAY render exactly one range band at the t+5 session position, built from `range_5s_pct` in `GET /tickers/{ticker}/range`: an upper bound at `close x (1 + range_5s_pct/100)` and a lower bound at `close x (1 - range_5s_pct/100)`, where `close` is the most recent historical close, drawn as dashed lines in the accent colour with the band-fill area between them, symmetric about the last close, and labelled with the same `±X.XX%` text the Verdict panel shows (Rule 1, Rule 2: five sessions, an unsigned percentage). The band SHALL NOT imply direction: no positive or negative colour, no arrow and no marker at either bound. The chart SHALL NOT render any line, point, envelope or fill between the most recent historical close and the t+5 position, and SHALL NOT render a single predicted price or a projected candle. The chart SHALL NOT animate on a ticker change. The chart's colours SHALL follow the active theme and SHALL be re-applied when the theme changes. The chart section SHALL expose a text alternative stating the last close and the typical move.

#### Scenario: Chart shows candles for the selected ticker
- **WHEN** a ticker is selected in the Rail
- **THEN** the chart panel renders OHLC candles from that ticker's `GET /tickers/{ticker}/history` response

#### Scenario: No derived indicator lines are drawn
- **WHEN** the chart panel renders
- **THEN** no derived technical indicator overlay is drawn on or alongside the candles

#### Scenario: Volume histogram is not a prohibited indicator overlay
- **WHEN** the chart panel renders a volume histogram below the candlesticks
- **THEN** this does not violate the no-derived-indicator constraint, since volume is raw OHLCV data

#### Scenario: Band bounds are computed from the last close
- **WHEN** the last historical close is 11 and `/range` responds with a numeric `range_5s_pct` of 5
- **THEN** the band's upper bound is 11.55 and its lower bound is 10.45 at the t+5 position

#### Scenario: Band is one position, not a path
- **WHEN** the chart panel renders a band
- **THEN** nothing is drawn between the most recent historical close and the t+5 position except empty axis space, and no valued data point is added to any series for the intermediate sessions

#### Scenario: Band is accent-coloured, symmetric and labelled
- **WHEN** the chart panel renders a band for `range_5s_pct` 4.12
- **THEN** both bounds and the fill use the accent and band-fill colours, never the candle up or down colours, the distances above and below the last close are equal, and the label reads "±4.12%"

#### Scenario: No band when the range is unavailable
- **WHEN** `/range` responds with a null `range_5s_pct`, or responds `404` or `5xx`
- **THEN** the chart panel renders candles and volume only, with no band and no label

#### Scenario: Price scale includes the band
- **WHEN** a band's upper or lower bound lies outside the price range of the visible candles
- **THEN** the price scale expands so both bounds are visible

#### Scenario: Theme change re-colours the chart
- **WHEN** the user toggles the theme while a chart is displayed
- **THEN** the chart background, text, grid, candle, volume and band colours change to the new theme's tokens without a reload and without losing the visible window

### Requirement: Verdict panel's range block states the typical 5-session move, its range check and its coverage
The top of the Verdict panel SHALL be the range block, the dashboard's range display, built from `GET /tickers/{ticker}/range`, with the states, reasons and no-sigma, no-direction rules of "Range display distinguishes available, unavailable, not-loaded, and failed states" and "Range display shows no daily sigma, direction, or point forecast". Its available state SHALL show `range_5s_pct` as the display figure, unsigned, with the ± sign and two decimals ("±4.12%"), labelled "Typical 5-session move" (Rule 1, Rule 2); then the **range check**, labelled "Range hit-rate" (Rule 4), worded "N of the last M five-session moves stayed inside it", M being the `n` returned by `/range` and N being `rate x n` rounded; then the nominal coverage derived from `range_coverage` and stated as not a guaranteed interval, e.g. "Nominal coverage: about 2 in 3 — not a guaranteed interval." (Rule 4). When `rate` is null the check SHALL read "Not enough history to check the range" and no ratio or percentage SHALL be shown. When `range_coverage` is null (an uncalibrated ticker) the block SHALL show the band with the words "Not calibrated for this ticker" and SHALL show no range check and no coverage claim, even if `range_hit_rate` is present. The range check is the only place the hit-rate appears; the chart, the Stage header and the Debate matrix SHALL NOT render it. The block SHALL be visible before any debate has run.

#### Scenario: Available range with its check
- **WHEN** `/range` responds with `range_5s_pct` 4.12, `range_coverage` 0.68 and `range_hit_rate` of `{rate: 0.68, n: 50}`
- **THEN** the block shows "±4.12%" labelled "Typical 5-session move", "Range hit-rate" with "34 of the last 50 five-session moves stayed inside it", and the nominal coverage sentence

#### Scenario: Not enough windows
- **WHEN** `range_hit_rate` is `{rate: null, n: 15}`
- **THEN** the block shows "Not enough history to check the range" and no ratio

#### Scenario: Uncalibrated ticker
- **WHEN** `range_coverage` is null and `range_hit_rate` is `{rate: 0.7, n: 50}`
- **THEN** the block shows the band and "Not calibrated for this ticker", and no range check, no coverage sentence and no hit-rate figure

#### Scenario: Shown before the debate
- **WHEN** a ticker with a served band is selected and no analysis has run
- **THEN** the band and the range check are visible and no `POST /debate` has been issued

#### Scenario: Hit-rate appears once
- **WHEN** the dashboard renders a ticker whose `/range` carries a `range_hit_rate`
- **THEN** the hit-rate wording appears in the range block and nowhere in the chart, the Stage header or the Debate matrix

#### Scenario: No ticker selected keeps the block's shape
- **WHEN** no ticker is selected
- **THEN** the block shows its label, an `N/A` in the same type size as a real figure but in a muted colour, an "—" in place of the range check and the nominal-coverage slot, and the disclaimer, so selecting a ticker adds no lines

### Requirement: The theme follows the design tokens in light and dark, with a user toggle
The dashboard's colours, type styles, spacing, radii and layout sizes SHALL come from the design's tokens as CSS custom properties, in a light and a dark theme. The topbar SHALL carry a theme toggle (a button with `aria-pressed`) that switches between them and stores the choice in the browser; with no stored choice the dashboard SHALL follow the operating system's preference, including when it changes. Reading or writing the stored choice SHALL be guarded so the page renders correctly when storage is unavailable. A stored choice SHALL be applied before the first paint. The dashboard SHALL NOT load web fonts from a third-party host; text SHALL use the design's system font stacks. Chips and rows SHALL use the small radius and panels and cards the medium radius; panels SHALL be separated by a 1 px border, not a shadow; the only motion SHALL be a colour change of at most 120 ms, plus the running spinner, which SHALL slow under `prefers-reduced-motion`.

#### Scenario: Toggle switches theme
- **WHEN** the user activates the theme toggle
- **THEN** the root element's `data-theme` changes between `light` and `dark`, `aria-pressed` follows, and the choice is stored

#### Scenario: Follows the OS with no stored choice
- **WHEN** nothing is stored and the operating system prefers dark
- **THEN** the dashboard renders in the dark theme

#### Scenario: Storage unavailable
- **WHEN** reading or writing the stored choice throws
- **THEN** the dashboard renders, the toggle still switches the theme for the session, and no error reaches the user

#### Scenario: No third-party font request
- **WHEN** the dashboard's HTML is loaded
- **THEN** it contains no link to a font host

### Requirement: Token colour pairs meet the contrast the design claims
Every foreground and background pair the design relies on SHALL meet its contrast ratio in both themes, measured on the dashboard's actual stylesheet: 4.5:1 for text (ink and muted ink on each of the three surfaces; accent text on the page and panel surfaces; the on-accent text on the accent fill; up and down ink on the panel surface and on their own tinted backgrounds; the Key tension body text on the warn ink and the Key tension label text on the warn border colour, each on the warn background) and 3:1 for non-text (the strong line on the page and panel surfaces; the candle colours on the panel surface; the focus ring on every surface it appears on). A test SHALL compute these ratios from the stylesheet's token values and fail if any pair falls below its requirement.

#### Scenario: Contrast is computed from the real stylesheet
- **WHEN** the contrast test reads the dashboard's token stylesheet
- **THEN** it resolves both themes' values and asserts each pair against its 3:1 or 4.5:1 requirement

#### Scenario: A token edit that breaks a pair fails the test
- **WHEN** a text token is changed so that its ratio on a surface drops below 4.5:1
- **THEN** the contrast test fails and names the pair and the theme

### Requirement: No Rail, Stage or Verdict element implies direction except stance and verdict marks
The up and down colours, the `↑`, `↓` and `→` glyphs and the words Bullish and Bearish SHALL appear only on stance chips, verdict badges and agent-card headings, always as the glyph together with the word (Rule 6), and the chart's candle and volume marks SHALL use the candle colours, but the OHLCV legend's value text SHALL use the primary ink with a colour swatch in the candle colour, and candle colours SHALL NOT be used as text colour anywhere. Nowhere else SHALL the dashboard show a signed or "predicted" return, a target price, a projected candle or point, a status or freshness dot, `▲` or `▼`, or the word "Confidence" in any case for a vote count or a reliability figure (Rule 4). Error and notice text SHALL carry no up or down colour and SHALL name the failure in words. A test SHALL render every Verdict state and the Rail and fail on any of these.

#### Scenario: Scan finds no forbidden cue
- **WHEN** the scan renders the dashboard with a selected ticker in each Verdict state and a populated Rail
- **THEN** it finds no signed percentage, no `▲` or `▼`, no match of `confiden(ce|t)`, no "predicted" or "forecast", no status-dot element, and no arrow outside stance chips, verdict badges and agent-card headings

#### Scenario: Error text is not coloured as bearish
- **WHEN** a load, range or analysis failure message is shown
- **THEN** its colour is the primary ink and it contains a text description of the failure

### Requirement: Page load and selection issue only the requests the budget allows
On load the dashboard SHALL issue `GET /tickers` and no other request. Selecting a ticker SHALL issue `GET /tickers/{ticker}/history` and `GET /tickers/{ticker}/range` for that ticker, each once however many components read them, and nothing else per ticker; the debate runs only on the user's Analyse action. A Rail row, the topbar search while filtering, the sort control, the layout mode, the theme toggle, the chart history control and the Debate matrix SHALL NOT issue any request of their own. Re-selecting a ticker within the session MAY be served from cache. The catalog request SHALL be answered within 2 seconds on a cold database for the 208-symbol catalog.

#### Scenario: Initial load with no selection
- **WHEN** the dashboard loads and the catalog holds 208 loaded tickers
- **THEN** exactly one API request is made, `GET /tickers`

#### Scenario: Selecting a ticker
- **WHEN** a user selects a ticker
- **THEN** one `/history` request and one `/range` request are made for that ticker, and no request is made for any other ticker

#### Scenario: Interface controls cost nothing
- **WHEN** the user sorts the Rail, types in the search, opens the drawer, switches the history window or the theme, or expands an agent card
- **THEN** no API request is made

#### Scenario: No retired endpoint is requested
- **WHEN** any user flow runs (load, select, search-and-load, refresh, analyse)
- **THEN** no request is made to `/prediction`, `/insight` or `/backtest`

### Requirement: Disclaimer stays visible with the Verdict panel, the Debate matrix and the range block, with no visibility control
Per domain Rule 6, the dashboard SHALL display the disclaimer in force (the text of `docs/DISCLAIMER.md`; its wording is owned by `align-rules-and-disclaimer`) whenever a debate verdict, an Agreement count, a range or the agents' reasoning is displayed: at the foot of the Verdict panel in every state, in the drawer-mode strip, and under the Debate matrix's heading, in each case as the inline text with the full text one step away. The dashboard SHALL NOT provide any control that hides, collapses or otherwise makes the inline disclaimer's visibility optional.

#### Scenario: Disclaimer in every Verdict state and at the matrix
- **WHEN** the Verdict panel is shown ready, running, with a result, with an unavailable agent, with insufficient data or failed, or with no ticker selected
- **THEN** the inline disclaimer is visible in the panel, and the Debate matrix shows it too

#### Scenario: No control can hide the disclaimer
- **WHEN** the dashboard renders
- **THEN** no toggle, setting or other control exists that would hide or collapse the inline disclaimer

### Requirement: Dashboard renders the Verdict panel and the Debate matrix for the selected ticker
The dashboard SHALL render the Verdict panel and the Debate matrix unconditionally, with no environment variable or flag controlling them, and SHALL render no other insight panel. The analysis runs only when the user activates Analyse. The Verdict panel and the Debate matrix SHALL read one analysis run and one kept result per ticker, so both show the same run.

#### Scenario: Panels are shown with no configuration
- **WHEN** the dashboard loads with `VITE_DEBATE_PANEL_ENABLED` unset, `false` or `true`
- **THEN** the Verdict panel and the Debate matrix are rendered and no other insight panel exists in the tree

#### Scenario: No retired panel is reachable
- **WHEN** any user flow runs
- **THEN** no Confidence, Advice or "Backtest this ticker" element is rendered

#### Scenario: Both read the same run
- **WHEN** an analysis finishes for the selected ticker
- **THEN** the Verdict panel and the Debate matrix both show that result, and neither started a second request

### Requirement: Keyboard focus is visible on every control and the dashboard is operable by keyboard
Every interactive element SHALL show a 2 px solid accent outline with a 2 px offset when focused by keyboard. Every function of the dashboard (choosing a ticker, sorting, refreshing, opening the drawer or the collapsed Rail, choosing a history window, resetting the zoom, analysing, expanding an agent card, switching an agent tab, toggling the theme, opening "About this analysis") SHALL be operable with the keyboard alone, and the tab order SHALL follow the reading order in every layout mode.

#### Scenario: Focus ring on a Rail row
- **WHEN** a keyboard user focuses a Rail row's select control
- **THEN** it shows a 2 px accent outline with a 2 px offset

#### Scenario: Keyboard-only walkthrough
- **WHEN** a keyboard user, starting at the topbar, selects a ticker, presses Analyse and expands an agent card
- **THEN** each step is reachable with Tab, Shift+Tab, Enter, Space and the arrow keys, and no step needs a pointer

## MODIFIED Requirements

### Requirement: Chart panel shows an OHLCV legend for the hovered or most recent session
The chart panel SHALL display a fixed-position legend showing that
session's Open, High, Low, Close, and Volume values. The legend SHALL
reflect the session currently under the crosshair; when the crosshair is
not positioned over the chart, the legend SHALL show the most recent
(rightmost) session's values instead of appearing blank. The legend's
five values SHALL render in the primary ink, with a small colour swatch
beside them in the candle colour of that session (Close ≥ Open → up, else
down); the candle colours SHALL NOT be used as text (they reach 3:1 as marks,
not the 4.5:1 text needs); the legend SHALL NOT introduce a different
up/down comparison.

#### Scenario: Legend defaults to the most recent session
- **WHEN** the chart panel renders for a selected ticker and the
  crosshair is not positioned over the chart
- **THEN** the legend shows the most recent session's Open, High, Low,
  Close, and Volume values

#### Scenario: Legend updates to the hovered session
- **WHEN** a user positions the crosshair over a specific candle
- **THEN** the legend shows that candle's Open, High, Low, Close, and
  Volume values, replacing whatever it showed before

#### Scenario: Legend values are inked, with a swatch matching the session's direction
- **WHEN** the legend displays a session whose Close is greater than or
  equal to its Open
- **THEN** the legend's O/H/L/C/Volume values render in the primary ink
  (at least 4.5:1 against the card surface in both themes) beside a swatch
  in the up candle colour, and beside a swatch in the down candle colour
  for a session whose Close is below its Open

#### Scenario: Legend reflects only real historical data
- **WHEN** the chart panel renders a range band (per the "Chart panel
  renders OHLCV, volume and the 5-session range band, with the band label
  and no derived indicator" requirement)
- **THEN** the legend never displays a band bound as if it were a real
  session's OHLCV

## REMOVED Requirements

### Requirement: Ticker panel shows the fixed set plus search for any real ticker
**Reason**: The ticker panel (a wrapping grid of chips above the chart, a separate "Searched tickers" list and a "Load" button) is replaced by the Rail and the one topbar search. The requirement also still said the fixed set was the 9 `TRAINING_TICKERS`, while the shipped list is every loaded catalog entry.
**Migration**: "Rail lists the loaded catalog, sorted by Symbol or Last loaded, and filtered by the topbar search", "One topbar search filters the Rail and selects or loads a symbol" and "Rail rows show the symbol, loaded age, a refresh control and an ineligibility tag, and no direction cue".

### Requirement: Range display shows the typical 5-session move and its measured coverage
**Reason**: The range card becomes the range block at the top of the Verdict panel, with two decimals, the "Range hit-rate" label, a "Not calibrated" case and the wording "Not enough history to check the range".
**Migration**: "Verdict panel's range block states the typical 5-session move, its range check and its coverage".

### Requirement: Dashboard issues no per-ticker requests for tickers that are not selected
**Reason**: It spoke of ticker chips; the Rail row, the topbar search and the new controls replace them, and the budget now also bounds the catalog request's latency.
**Migration**: "Page load and selection issue only the requests the budget allows".

### Requirement: Range display shows explicit placeholders when no ticker is selected
**Reason**: The card it described is now the range block of the Verdict panel, which keeps the same no-ticker shape.
**Migration**: The "No ticker selected keeps the block's shape" scenario of "Verdict panel's range block states the typical 5-session move, its range check and its coverage".

### Requirement: Chart panel renders OHLCV plus a 5-session range band, no derived-indicator overlay
**Reason**: The band is drawn in the accent colour (it was the chart's neutral ink) and labelled with its percentage, and the chart now has a history control and a theme. The shape rule (one position, no path) is kept.
**Migration**: "Chart panel renders OHLCV, volume and the 5-session range band, with the band label and no derived indicator".

### Requirement: Disclaimer stays visible with the debate panel and range card, with no visibility control
**Reason**: The debate panel and the range card no longer exist as separate components; the disclaimer is now required at the Verdict panel and at the Debate matrix.
**Migration**: "Disclaimer stays visible with the Verdict panel, the Debate matrix and the range block, with no visibility control".

### Requirement: Dashboard renders the debate panel for the selected ticker
**Reason**: It named a side-panel region whose layout was "unchanged"; that region is replaced by the Verdict panel and the Debate matrix.
**Migration**: "Dashboard renders the Verdict panel and the Debate matrix for the selected ticker".
