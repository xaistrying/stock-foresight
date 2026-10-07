## REMOVED Requirements

### Requirement: Feature flag gates the DebatePanel rollout
**Reason**: The flag existed so the old `AIInsightPanel` could be shown instead. That panel and the XGBoost serving path behind it are deleted, so there is nothing to roll back to; the flag defaulted to off, which left a fresh checkout showing the retired model.
**Migration**: The `DebatePanel` renders unconditionally (see the `dashboard-ui` requirement "Dashboard renders the debate panel for the selected ticker"). Remove the `VITE_DEBATE_PANEL_ENABLED` variable from the frontend environment files and from `README.md`; the variable is ignored if left set.
