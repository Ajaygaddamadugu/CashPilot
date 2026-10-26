# Requirements traceability

Every requirement in the brief, broken into checkable items, with the planned implementation and
the evidence that will prove it. This file is written first and updated as the build lands.

**Status legend:** Planned → Built → Verified (has an automated check).

## A. Business problem and scope

| ID | Requirement | Planned implementation | Evidence | Status |
|---|---|---|---|---|
| A1 | Consolidate account balances | Daily position per account from ledger; entity and group totals in USD | Reconciliation checks | Planned |
| A2 | Consolidate expected cash flows | As-of snapshot of forecast items, balances and FX per forecast run | Forecast tests | Planned |
| A3 | Forecast short-term liquidity under scenarios | 13-week daily projection per entity for base, delayed-receipt and stress | Scenario tests | Planned |
| A4 | Expose key decisions and exceptions | Rule catalogue with IDs; every exception carries a rule and a decision; lineage records each item's treatment | Exception table, rule docs | Planned |
| A5 | Preserve traceability | Immutable IDs, run lineage tables, input/result hashes, dataset manifest | Re-run reproduces stored hashes | Planned |
| A6 | Measurable outputs | Detection precision/recall/F1, forecast WAPE and bias, variance drivers, liquidity metrics | Evaluation report | Planned |
| A7 | Medium complexity: related entities, conditional rules, ≥1 exception path, evaluation metrics | 30+ related tables, conditional rules, exception workflow, metrics | Docs and tests | Planned |

## B. Actors

| ID | Requirement | Planned implementation | Status |
|---|---|---|---|
| B1 | Customer/account holder | Entity treasurer role: sees only its own entity, submits manual forecast items | Planned |
| B2 | Operations analyst | Runs reconciliation and forecasts, triages exceptions, triggers re-runs | Planned |
| B3 | Risk/compliance reviewer | Approves/rejects runs (four-eyes), waives HIGH exceptions with justification, freezes accounts | Planned |
| B4 | System administrator | Loads FX, publishes scenario versions, manages users, opens/closes accounts | Planned |

## C. Business workflow rules

| ID | Rule | Planned implementation | Status |
|---|---|---|---|
| C1 | Master data first | Generation order: reference → entities → accounts → counterparties → FX → documents → forecast items → ledger | Planned |
| C2 | Dependent records use valid parent IDs | Children are built from parent frames; FK checks on every relationship | Planned |
| C3 | Business logic: entities/accounts; opening balances and ledger; scheduled receivables/payables with expected dates; FX rates; daily cash positions; base/delayed/stress scenarios; forecast versions; actual-vs-forecast | One generator/engine module per step | Planned |
| C4 | State changes persisted as events; history never overwritten | Event tables per lifecycle; derived current status; append-only triggers in SQL | Planned |
| C5 | Outcomes and labels from documented rules, not random assignment | Payment delays from counterparty risk tier; statuses derived from events; labels from injection rules | Planned |

## D. Entities and relationships

| ID | Requirement | Planned implementation | Status |
|---|---|---|---|
| D1 | Core entities: LegalEntity, BankAccount, LedgerEntry, CashFlowForecast, Receivable, Payable, CurrencyRate, LiquidityScenario, ForecastRun | One table each, plus supporting tables | Planned |
| D2 | PK for every entity, FK for every relationship | Declared in the data dictionary; enforced by validator and SQL DDL | Planned |
| D3 | Cardinality, optional relationships, effective dates, lifecycle states | Documented per relationship in the data dictionary and ERD | Planned |
| D4 | Bridge tables for N:M | Settlement allocation, scenario↔assumption, run↔scenario, run↔forecast item | Planned |
| D5 | Event history for state changes | Account, receivable, payable, forecast item, forecast run, exception events | Planned |
| D6 | Validate all joins | Join-consistency checks (e.g. ledger entity = account entity) | Planned |
| D7 | Anomalies labelled, unrelated rows untouched | Ground-truth file keyed by record ID; injection touches only targeted rows | Planned |

## E. ID conventions

| ID | Convention | Status |
|---|---|---|
| E1 | `ENT-000001`, `BANKACC-<entity-id>-001`, `LED-2026-00000001`, `CF-2026-000001`, `FCAST-2026-01-01-001` | Planned |
| E2 | Zero-padded counters, immutable IDs, referenced IDs identical across files | Planned |

## F. Synthetic data generation steps

| ID | Step | Planned implementation | Status |
|---|---|---|---|
| F1 | Data dictionary: type, required, allowed values, units, uniqueness, validation rule per field | YAML dictionary → Markdown + SQL DDL | Planned |
| F2 | Parent tables first, then child and event tables | Pipeline order | Planned |
| F3 | Deterministic IDs and naming | ID helpers; sorted assignment | Planned |
| F4 | 30 entities, 150 accounts, 100,000 ledger entries, 20,000 forecast items, 5 currencies; delayed receivables, FX movement, large one-offs; fixed seed; scale parameter | `full` and `starter` profiles of one generator; exact counts | Planned |
| F5 | Valid baseline first, then labelled edge cases | Baseline validation before injection | Planned |
| F6 | Derived values calculated from source records | Statements, positions, statuses, totals computed, never sampled | Planned |
| F7 | Separate ground truth, never leaked into inputs | `ground_truth/` folder; tests prove detection does not read it | Planned |
| F8 | Validation: PK, FK, enums, date ordering, arithmetic reconciliation, lifecycle transitions, duplicates | `validate` command → validation summary | Planned |
| F9 | Export CSV/JSON/SQL + README, dictionary, generator command, seed, source manifest, validation summary | `export` step | Planned |
| F10 | Regenerate twice with the same seed and compare counts/checksums | `repro-check` command and test | Planned |

## G. Edge cases

| ID | Edge case | Planned injection | Planned detection |
|---|---|---|---|
| G1 | Opening balance + ledger ≠ closing balance | Bank-only fee or bank-rejected payment on a statement day | Statement movement vs ledger, per account-day |
| G2 | FX rate missing | Delete specific business-day rates (short and long gaps) | Rate calendar completeness; staleness rule |
| G3 | Cash flow counted twice | Manual forecast item duplicating a subledger item | Same reference, or fuzzy key within tolerance |
| G4 | Forecast uses actual after cutoff | Historical runs built from a post-cutoff snapshot | Lineage timestamps vs knowledge cutoff |
| G5 | Currency mixed without conversion | Forecast item with foreign amount and no conversion | Currency vs account; amount vs source document |

## H. Acceptance criteria

| ID | Criterion | Planned automated proof |
|---|---|---|
| H1 | Daily balances reconcile | Roll-forward per account-day; statement vs ledger; account → entity → group totals |
| H2 | Scenarios differ only by documented assumptions | Assumptions removed ⇒ identical to base; each changed item matches an assumption filter |
| H3 | Forecasts are reproducible | Same seed ⇒ same checksums; re-running a stored run ⇒ same result hash |
| H4 | Actual-versus-forecast variance is explainable | Variance split into drivers with zero residual, drillable to record IDs |

## I. Evaluation focus

| ID | Focus | Planned evidence |
|---|---|---|
| I1 | Realistic distributions and meaningful variation | Data profile report |
| I2 | Consistent IDs and valid joins | ID pattern, embedded-ID and FK checks |
| I3 | Dependency/lifecycle consistency | State-machine checks on every event table |
| I4 | Correct derived values and reconciliation | Arithmetic checks |
| I5 | Normal, boundary, failure and exception coverage | Coverage matrix in docs; negative controls in ground truth |
| I6 | Separate ground truth | `ground_truth/` folder + leakage tests |
| I7 | Fixed-seed reproducibility, documentation, lawful provenance | Repro report, docs, provenance statement |

## J. Submission guidelines

| ID | Guideline | Planned evidence |
|---|---|---|
| J1 | Working, executable code with install/configure/run/verify steps | README quick start; CI on Windows and Ubuntu |
| J2 | Public repo; evolution visible through meaningful commits | Small commits per layer, pushed as they land |
| J3 | LLM use disclosed with prompt history | `AI_USAGE.md`, `prompts/PROMPT_HISTORY.md` |
| J4 | Reasoning visible: assumptions, decisions, trade-offs, testing, limitations | `docs/` |
