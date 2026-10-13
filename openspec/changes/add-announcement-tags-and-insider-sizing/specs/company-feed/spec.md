## MODIFIED Requirements

### Requirement: The company feed makes no model call and shows nothing
The company feed SHALL make no language-model call and SHALL NOT itself display, export or return any stored text to a user. The stored values that reach a user are event dates and numbers (ex-date, record date, payout date, per-share amount, exercise ratio, publication date), an issue class (an enumeration derived inside the weekly brief's one adapter from keywords in the stored title, so that only the enumeration value leaves the adapter for an event), and, from the announcements change, announcement titles and the counterparty names parsed from event titles, shown by the weekly brief as third-party text that is labelled by provenance, sanitised, length-capped and in its original language. No stored snippet, source name, source link, author or body text SHALL be displayed, carried out of the adapter or exported until a later change shows them, and Rules 1 to 6 are neither engaged nor changed by the feed itself. Whatever displays these titles SHALL label them by provenance (Rule 5), show the disclaimer (Rule 6) and fence them in any prompt, and whatever displays the dates and numbers SHALL label them by their source and state when the feed was last fetched.

#### Scenario: No model client is used
- **WHEN** a snapshot run is traced
- **THEN** no `LLMClient` or provider SDK is constructed or called

#### Scenario: No route exposes the log
- **WHEN** the application's routes are listed
- **THEN** none reads `company_feed_log.db`

#### Scenario: No stored text reaches the brief
- **WHEN** the brief's adapter builds an event from a stored row
- **THEN** the event carries no title, snippet or other string from the row except the event code; for an issue event it carries the issue class enumeration derived from the title, and the title itself is not kept

#### Scenario: A title reaches the brief only as sanitised third-party text
- **WHEN** the brief's adapter builds an announcement from a stored row
- **THEN** the announcement carries the stored title and the dates and event fields the brief names, and carries no source name, source link, author or snippet, and the brief displays the title only through the sanitiser, inside labelled quotes

#### Scenario: The adapter still reads through the helpers only
- **WHEN** the adapter reads news items and events for a ticker
- **THEN** it does so through `latest_items` and `last_fetch` of the store module, and no helper is added to the company feed package for it
