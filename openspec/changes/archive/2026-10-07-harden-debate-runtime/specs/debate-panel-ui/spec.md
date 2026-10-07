## ADDED Requirements

### Requirement: DebatePanel shows the running stage and elapsed time
While an analysis for the selected ticker is running, the panel SHALL show the stage reported by `GET /tickers/{ticker}/debate/progress` using the labels "Running agents…" (`round1`), "Comparing positions…" (`round2`) and "Synthesising…" (`synthesis`), and the elapsed seconds since the request was submitted, updated at least once per second. The label SHALL come from the server, not from a timer. A failed progress poll SHALL keep the last label and show no error. The disclaimer SHALL remain visible.

#### Scenario: Stage follows the server
- **WHEN** the progress endpoint reports `round2` while the request is pending
- **THEN** the panel shows "Comparing positions…" and an elapsed time

#### Scenario: Elapsed time keeps counting
- **WHEN** 12 seconds have passed since the request was submitted
- **THEN** the panel shows an elapsed time of 12 seconds

#### Scenario: Progress poll fails
- **WHEN** a progress request fails while the analysis is running
- **THEN** the previous label stays and no error message appears

### Requirement: DebatePanel keeps the last result per ticker for the session
The panel SHALL keep the last successful result for each ticker in memory until the page reloads or that ticker is analysed again, and SHALL show it with the time it was produced. Switching tickers SHALL NOT cancel an in-flight request or discard a result; when the user returns to a ticker whose analysis finished or is still running, the panel SHALL show that result or that running state. A failed run SHALL NOT remove a kept result: the error is shown above it.

#### Scenario: Switch away and back
- **WHEN** an analysis for VCB is running, the user selects FPT, and the VCB analysis finishes
- **THEN** selecting VCB again shows the finished VCB result without a new request

#### Scenario: Result is labelled with its time
- **WHEN** a kept result is displayed
- **THEN** the panel shows when it was produced (for example "Analysed 14:32")

#### Scenario: Failed re-run keeps the old result
- **WHEN** the user re-analyses a ticker that has a kept result and the run fails
- **THEN** the error is shown and the earlier result remains visible

#### Scenario: Other ticker has no result
- **WHEN** the user selects a ticker that has never been analysed this session
- **THEN** the panel shows the not-run state

### Requirement: DebatePanel stops waiting after a client time limit
The analysis request SHALL be aborted by the client after 200 seconds (the server run budget of 180 s plus 20 s). The panel SHALL then say that no answer arrived in that time, that the server may still be working, and that analysing again rejoins it. It SHALL NOT show the network-error message for this case.

#### Scenario: No response within the limit
- **WHEN** the request has had no response when the client limit is reached
- **THEN** the panel shows the time-limit message and an "Analyse again" action, not "could not reach the server"

### Requirement: DebatePanel names the reason an analysis could not run
The panel SHALL show a distinct message for each of: the ticker is not loaded (404); another analysis limit reached (429 `debate_busy`: "Another analysis is already running; try again shortly"); the service is not configured (503 `debate_not_configured`, showing the server's message); the server run timed out (504 `debate_timeout`); the client time limit. Any other failure SHALL show a generic message together with the server's `detail` when one exists. The disclaimer SHALL remain visible in each of these states.

#### Scenario: Busy
- **WHEN** the response is HTTP 429 with `code` "debate_busy"
- **THEN** the panel shows the busy message and offers a retry

#### Scenario: Not configured
- **WHEN** the response is HTTP 503 with `code` "debate_not_configured" and a message
- **THEN** the panel shows that message

#### Scenario: Server timeout
- **WHEN** the response is HTTP 504 with `code` "debate_timeout"
- **THEN** the panel says the analysis timed out on the server

#### Scenario: Disclaimer in failure states
- **WHEN** any of the failure messages is shown
- **THEN** the disclaimer is visible

### Requirement: DebatePanel shows the report-saved line only when the report was saved
Level 3 SHALL show "Report saved to reports/<report_file>" only when the result has `report_saved` true, using the `report_file` value from the response. When `report_saved` is false or absent the panel SHALL NOT claim a saved report.

#### Scenario: Report saved
- **WHEN** the result has `report_saved` true and `report_file` "2026-10-05_VPB.md"
- **THEN** Level 3 shows "Report saved to reports/2026-10-05_VPB.md"

#### Scenario: Export failed
- **WHEN** the result has `report_saved` false
- **THEN** Level 3 contains no "Report saved" text

### Requirement: DebatePanel marks an unavailable key tension
When `synthesis.key_tension` is null the Level 2 Key Tension block SHALL say "Key tension unavailable" and SHALL NOT present any text as the key tension.

#### Scenario: Null key tension
- **WHEN** the result's `synthesis.key_tension` is null
- **THEN** Level 2 shows "Key tension unavailable" under the Key Tension heading
