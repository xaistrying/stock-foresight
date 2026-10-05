## Why

`multi-agent-debate-analyst` (archived 2026-10-05) shipped the debate with its specs. Reading two real debate reports (VPB, SAB) and re-deriving their figures afterwards found three behaviours the archived specs get wrong or leave unspecified. The code was corrected the same day, after the archive, so the main specs now lag the code:

- the export prints **"Split (0 of 3 agents)"** for a three-way split, which reads as if nobody agreed;
- the Macro agent's **market-wide foreign-flow vote is not stable**: the same market read −9.2% of foreign turnover at 13:35, −18.4% at 14:48 and −24.5% from 15:12 (Vietnam time), and crossing the provisional ±10% threshold flipped VPB's verdict between SPLIT and OBSERVE depending on when the debate was run;
- **sector tagging admitted look-alike stories** (foreign banks being hacked, one lender's asset sale tagged as food-and-beverage news, any capital-raising story as banking news), which took slots from relevant headlines.

## What Changes

- **Export**: the Agreement line for a `split` verdict reads `Split (3 different positions)`; `majority` and `unanimous` keep `(N of 3 agents)`. Matches the panel's existing wording.
- **Macro agent**: the market-wide foreign-flow signal is still shown to the LLM, but only **casts a vote once the board has settled after the close** (Mon–Fri, from 15:15 Vietnam time). Before then it is labelled provisional and not counted. The clock is read before the fetch, the prompts tell the model not to infer a direction from a provisional signal, and Round 2 must not let provisional data move a stance.
- **News agent sector tags**:
  - banking drops the bare keywords `ngân hàng` and `huy động`; it uses phrases, full peer-bank brand names (not short tickers such as ACB/VIB/MSB, which also appear in stock lists) and a "bank + earnings/capital" pattern, and excludes headlines about foreign banks;
  - for non-financial sectors a headline whose subject is a bank is not tagged `[sector]`, except World Bank, ADB, State Bank and central-bank stories.
- No breaking changes. No API, schema or dependency changes.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `debate-report-export`: the Agreement line of the Summary section for a three-way split (template and a new scenario).
- `macro-agent`: the foreign-flow signal votes only once settled and is provisional before that; the prompts must not draw a direction from a provisional signal.
- `news-agent`: new sector-tag precision requirement (what does and does not count as sector news).

## Impact

- **Code**: `backend/app/services/debate/export.py`, `macro.py`, `news_feeds.py`; tests in `backend/tests/` (`test_debate_export_api.py`, `test_macro_signals.py`, `test_debate_agents.py`, `test_news_feeds.py`). Already implemented; backend suite 396 passing.
- **Frontend**: none (the panel already says "3 different positions").
- **Domain rules**: Rule 5 (News Context label, no "Market Sentiment") and Rule 6 (disclaimer last, unconditional) are honored unchanged; Rules 1–4 are not touched. No sign-off needed.
- **Archived record**: `changes/archive/2026-10-05-multi-agent-debate-analyst/` is left as written; its Decision 7 paragraph on foreign flow is superseded by this change's design.
