# Prompt history

Chronological record of the candidate's prompts to the AI assistant (Claude Code, model Claude
Opus 5.5) in the session that produced this repository, verbatim, each followed by a short
summary of what the AI did in response. The assistant's full answers, tool calls and
intermediate outputs are in the session transcript, which Claude Code stores locally; it is not
committed because it contains local file-system paths and environment details.

See [AI_USAGE.md](../AI_USAGE.md) for what the AI did and what the candidate reviewed.

---

## 1. The brief, and "plan before code"

The candidate pasted the problem statement and the submission guidelines (full text below), then wrote:

> donot implement anything just brain storm and understand every requirements and come up with a plan what will u do but it has to satisfy every requirement then ill give github link

<details>
<summary>Pasted problem statement</summary>

```text
Problem statement
Read it carefully. Your build should cover every point below.

Business Context / Problem
Consolidate account balances and expected cash flows to forecast short-term liquidity under scenarios.

Objective and Scope
Build a working solution for this end-to-end workflow: Consolidate account balances and expected cash flows to forecast short-term liquidity under scenarios. The solution should expose key decisions and exceptions, preserve traceability, and produce measurable outputs. Medium complexity means multiple related entities, conditional rules, at least one exception path and meaningful evaluation metrics.

Primary Actors / Systems
Customer/account holder, operations analyst, risk/compliance reviewer and system administrator

Business Workflow and Rules
1. Generate/reference master data first: LegalEntity, BankAccount, LedgerEntry, CashFlowForecast, Receivable.
2. Generate dependent transaction/event records using valid parent IDs.
3. Apply business logic: Create entities and bank accounts; generate opening balances and ledger entries; add scheduled receivables/payables with expected dates; create FX rates; calculate daily cash positions; define base, delayed-receipt and stress scenarios; store forecast versions and actual-versus-forecast comparisons.
4. Persist state changes as explicit records/events where relevant; do not overwrite history.
5. Generate outcomes and ground-truth labels from documented rules, not independent random assignment.

Entities and Relationships
Core entities: LegalEntity, BankAccount, LedgerEntry, CashFlowForecast, Receivable, Payable, CurrencyRate, LiquidityScenario, ForecastRun. Define a primary key for every entity and foreign keys for every relationship. Document cardinality (1:1, 1:N, N:M), optional relationships, effective dates and lifecycle states. Use bridge tables for many-to-many relationships; retain event history for state changes; validate all joins. For deliberate anomaly cases, keep an issue_type/ground_truth label rather than silently corrupting unrelated rows.

ID / Nomenclature Conventions
ENT-000001; BANKACC-<entity-id>-001; LED-2026-00000001; CF-2026-000001; FCAST-2026-01-01-001.

Synthetic Data Generation Instructions (Granular)
Step 1 — Write a data dictionary for: LegalEntity, BankAccount, LedgerEntry, CashFlowForecast, Receivable, Payable, CurrencyRate, LiquidityScenario, ForecastRun. For each field specify type, required/optional, allowed values, units, uniqueness and validation rule.
Step 2 — Create parent/master tables first, then child and event tables. Apply this domain-specific generation logic: Create entities and bank accounts; generate opening balances and ledger entries; add scheduled receivables/payables with expected dates; create FX rates; calculate daily cash positions; define base, delayed-receipt and stress scenarios; store forecast versions and actual-versus-forecast comparisons.
Step 3 — Apply deterministic IDs and naming: ENT-000001; BANKACC-<entity-id>-001; LED-2026-00000001; CF-2026-000001; FCAST-2026-01-01-001. Keep counters zero-padded, IDs immutable, and referenced IDs exactly consistent across files.
Step 4 — Generate the baseline volume: Generate 30 entities, 150 bank accounts, 100,000 ledger entries and 20,000 forecast items across 5 currencies. Include delayed receivables, FX movement and large one-off payments. Use a fixed seed (e.g. 20261022) and parameterize scale so starter and full datasets use the same generator.
Step 5 — Generate valid baseline records first, then inject labelled edge cases: Opening balance plus ledger does not equal closing balance; FX rate missing; cash flow counted twice; forecast uses actual after cutoff; currency is mixed without conversion.
Step 6 — Calculate derived values (totals, balances, scores, statuses and dates) from source records rather than generating them independently.
Step 7 — Produce a separate ground_truth.csv/json for known anomalies, expected decisions or labels; never leak it into input features.
Step 8 — Run validation: primary-key uniqueness, foreign-key integrity, allowed enums, date ordering, arithmetic reconciliation, lifecycle transitions and duplicate checks.
Step 9 — Export CSV/JSON/SQL seed data plus README, schema/data dictionary, generator command, fixed seed, source manifest and validation summary.
Step 10 — Regenerate twice with the same seed and compare row counts/checksums to demonstrate reproducibility.

Suggested Volume and Coverage
Generate 30 entities, 150 bank accounts, 100,000 ledger entries and 20,000 forecast items across 5 currencies. Include delayed receivables, FX movement and large one-off payments.

Required Edge Cases / Negative Scenarios
Opening balance plus ledger does not equal closing balance; FX rate missing; cash flow counted twice; forecast uses actual after cutoff; currency is mixed without conversion.

Validation Rules / Acceptance Criteria
Daily balances reconcile; scenarios differ only by documented assumptions; forecasts are reproducible; actual-versus-forecast variance is explainable.

Evaluation Focus for Generated Data
Review: (a) realistic distributions and meaningful variation; (b) consistent IDs and valid joins; (c) dependency/lifecycle consistency across entities; (d) correct derived values and reconciliation; (e) normal, boundary, failure and exception coverage; (f) separate ground truth; (g) fixed-seed reproducibility, documentation and lawful provenance.

Public Data Guidance / Lawful Use
External data is optional. If used, record source URL, dataset/version, retrieval date, license/terms, attribution, transformations and fields discarded. Use only data you are legally permitted to access and redistribute; do not bypass access controls or collect confidential/personal information. If licensing or suitability is unclear, use synthetic data and cite public reference data only for schema inspiration.
Before you submit, make sure you have
Pushed your code to a public GitHub repository
Added a README explaining how to run it
Included any tests the problem asks for
```

</details>

<details>
<summary>Pasted submission guidelines</summary>

```text
YottaFlex AI
RECRUITMENT DRIVE
Candidate Project
Submission Guidelines
Show us how you think, build, validate, and work with AI.
YOUR CHALLENGE WINDOW
72 HOURS Your submission window is 72 hours.
Artifact timestamps will be used to verify the window.
01 MAKE IT RUN
Submit working, executable code. Include clear steps so another person can
install dependencies, configure the project, run it, and verify key behavior.
EXECUTABLE
02 SHOW YOUR WORK
Use a public GitHub repository. Make the evolution of your work understandable
through the code, meaningful commits, and supporting context.
PUBLIC REPOSITORY
03 USE LLMs TRANSPARENTLY
LLM tools are allowed. Submit your prompt history and explain where AI accelerated
your work, where you relied heavily on it, and what you personally reviewed,
changed, or validated.
PROMPT HISTORY REQUIRED
04 MAKE YOUR REASONING VISIBLE
Help reviewers understand the problem, assumptions, key decisions, trade-offs,
testing approach, limitations, and how you know the solution works.
EXPLAIN THE WHY
BE READY TO WALK US THROUGH YOUR SOLUTION.
We value sound judgment, working software, honest AI disclosure, and clear communication.
```

</details>

**AI response.** Inspected the (empty) project folder and the environment without changing
anything; noticed that the home folder was itself a git repository and recommended a separate
repository for this project. Produced a plan covering every requirement: interpretation of the
problem, key decisions with reasons, a 34-table data model with bridges and event tables, the
generation pipeline mapped to Steps 1-10, injection/detection/expected-decision for each edge
case, scenario definitions, actors and the exception path, validation and acceptance-criteria
proofs, evaluation metrics, repository layout, tests, how each submission guideline would be
met, a 72-hour build order and open questions.

## 2. Where did "Finpark" come from?

> Commits will be authored as Finpark with the email in your global git config. That email has to belong to the GitHub account you submit with, or the commits won't show under your profile.  why finpark word is came to this project did you fetch my  github repo's?

**AI response.** Explained that nothing was fetched from GitHub: the name comes from the local
global git configuration file, which it showed with `git config --global --show-origin
user.name`; offered a project-only identity and GitHub's no-reply address for privacy.

## 3. Scope

> no need to involve the other related projects just we need to build that i have sent the requirements right? cashpoilt project only we need to build

**AI response.** Confirmed the scope is only this project and the two pasted documents; no other
folders, projects or global settings would be touched (a separate `git init` inside the project
folder only isolates it from the parent repository).

## 4. Repository and commit workflow

> now do i need to create the github repo ? if yes , after can we connect with this and then one by one we will push the code with clean meaningful commits ?is that right process?

**AI response.** Confirmed the process and gave step-by-step instructions to create an empty public
repository (no README, .gitignore or licence) and the commit discipline: every commit works and
is tested, push often so GitHub's timestamps document the 72-hour window, never rewrite history.

## 5. Repository settings check

> *(screenshot of GitHub's "Create a new repository" page: owner Ajaygaddamadugu, name CashPilot, a description, Public, README off, no .gitignore, no licence)*
> can i click the create repo or do we need to make any change?

**AI response.** Confirmed the settings were correct and asked for the repository link.

## 6. Go

> https://github.com/Ajaygaddamadugu/CashPilot.git

**AI response.** Implemented the plan in layers, each tested, committed and pushed: project
skeleton and planning docs; data dictionary and core helpers; generator; engine; anomaly
injection and legacy history; detection and workflow; validation suite; CLI, export, evaluation
and reproducibility; data bundles; CI and documentation. See `git log` for the sequence and the
decision log for the reasoning.

## 7. Resume

After a long autonomous stretch (the AI wrote the generator, engine, validation, export, CLI, docs and committed the starter dataset), the candidate wrote:

> hey continue the work where you stopped

**AI response.** Found that the full-scale background run had failed only in its reproducibility step
(a Windows/OneDrive file lock while deleting a folder), made the cleanup retry, re-ran the check
(82/82 files identical), cross-checked the README figures against the generated manifest and
corrected two overstated numbers, committed the full-scale artifacts, then verified the result
from a fresh clone of the public repository (49 tests pass; regenerated starter data is
byte-identical to the committed bundle) and confirmed GitHub Actions is green on Ubuntu and Windows.

## 8. Model switch

The candidate ran Claude Code's `/model sonnet` command, switching the session from Claude Opus 5.5 to
Claude Sonnet 5.5. This is a local command, not a prompt; it is recorded here because the
`Co-Authored-By` trailer of later commits names the new model.

## 9. Commands to run it

> hey if completed the full project give the commands to run this project or give the link i will run and check once and if any changes or any api optimisations i will tell you under my supervisor

**AI response.** Gave the repository link and the install, test and run commands, explained what to look at first, and pointed
out that the project has no web API (it is a command-line tool plus datasets), asking whether the supervisor wanted a dashboard or an API.

## 10. Terminal log and "how to run it?"

The candidate pasted the output of `pytest` (49 passed) and `cashpilot all --profile starter` (validation PASS, all five edge cases detected) and wrote:

> this is the terminal logs so i think we have passed all test cases ? if yes pls tell me how to run this project

**AI response.** Confirmed the log shows all tests passing and validation PASS, explained that "running" the project means running `cashpilot all` and reading its outputs, and gave the exploration commands (exceptions, explain, forecast, four-eyes approval, access denial, reproducibility check).

## 11. Inspect the code base before building a dashboard

<details>
<summary>Prompt (verbatim)</summary>

```text
I understand that CashPilot currently runs as a CLI tool. Before making any changes, inspect the actual codebase and answer these questions:

1. What are the current modules, entry points, and main components?
2. Are the financial calculations, data generation, scenario forecasting, anomaly detection, and evaluation implemented as reusable functions, or are they tightly coupled to CLI commands?
3. Is there already an API or frontend anywhere in the repository?
4. Can we add a web dashboard without rewriting or breaking the existing CLI functionality?
5. Recommend the smallest safe implementation plan for a browser-based CashPilot dashboard that uses the existing financial engine and displays:
   - Consolidated cash balances in the reporting currency
   - Daily and 13-week liquidity forecasts
   - Base, delayed-receipt, and stress scenario comparisons
   - FX rates and currency exposure
   - Detected exceptions with explanations and traceability
   - Forecast-versus-actual evaluation metrics
6. Explain how the dashboard would be started locally and demonstrated to a reviewer.
7. Identify any missing assessment requirements and distinguish implemented features from planned features.

Do not modify files or start implementation yet. Base your response on the actual repository, not assumptions.
```

</details>

**AI response.** Read-only inspection (module sizes, function signatures, a search for web frameworks, dependency pins, dataset sizes, load times, test coverage). Reported that the engine was reusable and the CLI thin, that no API or frontend existed, that `evaluate/` and `cli.py` had no direct tests, that the ground-truth files were named `anomalies.*` instead of the brief's `ground_truth.*`, and that the commit history was batched. Recommended an optional read-only Streamlit dashboard and asked two questions.

## 12. End-to-end hardening, assessment gaps and the dashboard

<details>
<summary>Prompt (verbatim; long)</summary>

```text
# CashPilot — End-to-End Financial Liquidity Management System

## Your Role

Act as a senior financial systems engineer, quantitative developer, backend engineer, and full-stack developer. Help me bring my existing **CashPilot** project to a reliable, assessment-ready state within my 72-hour Associate AI Forward Deployed Engineer challenge.

CashPilot is a synthetic-data-driven financial liquidity management system. It should help businesses understand their current cash positions, manage multiple currencies and bank accounts, forecast future liquidity, evaluate financial risks, detect data anomalies, and compare forecasted results with actual outcomes.

**This is not merely a dashboard project.** The financial processing engine, data integrity, forecasting logic, explainability, reproducibility, testing, and financial decision support are the core product. A web dashboard is one interface for using those capabilities.

## 1. Start by Understanding the Existing Repository

Before changing anything:

- Inspect the current repository, README, assessment requirements, architecture, configuration, dependency files, tests, generated datasets, reports, Git history, and AI usage documentation.
- Identify what is implemented, what is only partially implemented, what is missing, and what has not been independently verified.
- Trace the existing execution flow from synthetic-data generation through validation, financial calculations, forecasting, anomaly detection, evaluation, and exports.
- Identify the existing financial calculation conventions, reporting currency, FX-rate handling, data schemas, scenario definitions, and forecast versioning.
- Read the existing code before creating replacements.

**Preserve existing working features.** Do not rewrite the project, replace the financial engine, remove existing functionality, regenerate large datasets unnecessarily, or introduce breaking schema changes just to simplify implementation.

Before modifications, inspect the Git working tree and preserve any uncommitted user work. Do not reset, clean, overwrite, or discard existing changes.

## 2. Strengthen the Core Financial System

Prioritize correct, traceable financial calculations over visual presentation.

### A. Entities, bank accounts, and ledger

Ensure the system correctly handles:

- Multiple business entities and bank accounts.
- Account currencies, opening balances, ledger transactions, inflows, and outflows.
- Receivables, expected customer receipts, payables, and supplier payments.
- Restricted versus available cash where supported by the existing model.
- Daily opening and closing balances.
- Bank-statement versus book-balance reconciliation.
- Transaction identifiers, timestamps, and appropriate data relationships.

Validate the mathematical relationship between opening balance, inflows, outflows, and closing balance. Respect the existing accounting sign conventions and transaction semantics.

### B. Multi-currency and foreign exchange

Treat foreign exchange as a core financial capability, not just a currency dropdown.

Verify that the system correctly handles the currencies already specified in the assessment, including INR, USD, EUR, GBP, and JPY if those are the configured five currencies.

Check:

- FX-rate records, effective dates, source and target currencies, and rate direction.
- Conversion into the configured reporting currency.
- Missing, stale, invalid, or inconsistent FX rates.
- Correct currency-specific decimal precision and rounding.
- Currency exposure by entity, bank account, and currency.
- Whether FX movements or changed rates affect consolidated cash positions and forecasts correctly.
- Whether conversion and aggregation preserve traceability back to the original currency amounts.

Do not assume USD or INR must be the reporting currency. Inspect the existing configuration and assessment requirements, retain the current behavior where appropriate, and make the reporting currency configurable only if this can be done safely.

Add tests for known FX conversions, inverse-rate handling where supported, missing-rate behavior, and rounding. Never silently add amounts denominated in different currencies together.

### C. Receivables, payables, and expected cash flows

Verify that forecast items are incorporated correctly into future cash positions.

A delayed customer receipt should affect the appropriate future dates, rather than simply disappearing. Supplier payments should reduce cash at their expected payment dates. Ensure that changes in payment timing affect the forecast, liquidity headroom, and cash-shortfall warnings.

Prevent duplicate or inconsistent application of the same cash flow.

### D. Cash positions and forecasting

Verify:

- Daily account-level cash positions.
- Entity-level and consolidated cash positions.
- Daily and 13-week liquidity forecasts where required.
- Baseline, delayed-receipt, and stress scenarios.
- Minimum cash buffers and liquidity headroom.
- Forecast versions and reproducible forecast runs.
- The separation of historical actuals, forecast assumptions, and future projections.

Use a consistent financial date convention and explain any assumptions. Test calculations against small, manually verifiable examples.

### E. Financial anomaly detection

Review the existing detection system and required assessment anomalies. Preserve and verify all required cases, including reconciliation breaks, missing FX rates, duplicate flows, mixed-currency issues, and lookahead-related problems where applicable.

Ensure that:

- Detection rules do not accidentally use hidden ground-truth labels as model features.
- Ground truth remains separate from operational inputs and detection outputs.
- Each detected exception includes a useful reason and relevant identifiers.
- Clean baseline data passes the appropriate validation checks.
- Deliberately corrupted cases produce expected findings.
- Evaluation metrics measure detections against ground truth without leaking labels into detection logic.

## 3. Close Assessment and Engineering Gaps

Use the actual assessment specification as the source of truth. Build a requirements-to-evidence checklist.

Verify the required baseline dataset scale, including the specified entities, bank accounts, ledger entries, forecast items, and currencies. Preserve fixed-seed generation and reproducibility.

Review and test:

- Financial calculation correctness.
- Data validation and integrity.
- Evaluation metrics and forecast accuracy.
- Anomaly detection quality.
- CLI commands and failure behavior.
- Forecast-versus-actual comparisons.
- Scenario behavior.
- Ground-truth exports and required filenames.
- CSV, JSON, and SQL exports.
- Reproducibility checks.
- Documentation and cross-platform behavior where practical.

If the assessment requires `ground_truth.csv` and `ground_truth.json` while the current project provides `ground_truth/anomalies.csv` and `ground_truth/anomalies.json`, determine the safest compatibility solution. Preserve existing paths and consumers rather than breaking them.

Add tests that assert meaningful expected results, not merely that functions execute without exceptions. Use small deterministic fixtures for financial calculations and evaluation metrics so failures are easy to diagnose.

Do not change expected results just to make tests pass. If a calculation is incorrect, identify the defect, explain it, fix it, and demonstrate the correction.

## 4. Build CashPilot as a Complete Financial Product

After protecting and validating the existing core, improve the user-facing experience.

The product should provide useful financial workflows, not just a collection of charts.

### Financial workflows

Users should be able to explore the available data and understand:

1. Which business entities and bank accounts are included.
2. How much cash is held in each currency.
3. How local-currency balances become consolidated reporting-currency balances.
4. Which receipts and payments drive future cash positions.
5. When liquidity could fall below required cash buffers.
6. How delayed receipts and stress assumptions change the forecast.
7. Which data-quality or reconciliation exceptions need attention.
8. How actual cash positions compare with previous forecasts.
9. Why a forecast changed and which transactions, FX rates, or assumptions contributed to the change.
10. How to export results and reproduce a particular run.

Where the existing data supports it, provide drill-down from consolidated results to entity, bank account, transaction, forecast item, and exception records.

Do not invent financial facts or display misleading results when data is missing.

## 5. Add a Web Interface Without Replacing the Engine

A web interface is desirable, but it must consume the existing financial engine and data-loading functions instead of duplicating business logic.

First evaluate a lightweight framework such as Streamlit against the repository's Python version, pinned dependencies, dataset size, and assessment constraints. Choose it only if compatibility and reproducibility can be maintained.

If it requires dependency changes, test them in an isolated environment first. Do not casually upgrade or replace NumPy, pandas, PyYAML, or other existing dependencies.

The interface should cover these financial areas:

- **Cash overview:** consolidated cash, available and restricted balances where supported, liquidity headroom, and cash-buffer status.
- **Accounts and currencies:** balances by entity, bank account, and currency, with reporting-currency conversions and FX-rate details.
- **Forecasts:** daily and 13-week projected cash positions, with baseline, delayed-receipt, and stress scenarios.
- **Cash-flow drivers:** upcoming receipts, payables, timing changes, and the factors responsible for liquidity changes.
- **Exceptions and reconciliation:** detected anomalies, reconciliation differences, missing FX rates, and traceable exception details.
- **Actual versus forecast:** forecast accuracy, balance variances, error metrics, and explanations of significant differences.
- **Audit and exports:** forecast-run history, relevant event history, validation results, and CSV/JSON/SQL exports where supported.

Use meaningful filters such as entity, account, currency, date, scenario, and forecast run wherever the underlying data supports them.

The interface must distinguish actual data, forecast outputs, scenario assumptions, and ground-truth evaluation results.

Keep the initial interface read-only unless a write operation is already safely supported and genuinely necessary. Do not add simulated buttons that claim to save, reconcile, approve, or update financial records without actually doing so.

Keep the financial calculations in reusable backend modules. The interface should call those modules.

If the existing framework or dependencies make the proposed interface unsafe or too time-consuming, explain the trade-off and recommend the smallest reliable implementation. Do not sacrifice financial correctness or the assessment requirements to make the UI look impressive.

## 6. Explainability and Financial Decision Support

CashPilot should help users understand what a number means and why it changed.

Where supported by the data, explain:

- The source of a balance.
- Which receipts and payments contributed to a projected position.
- Which FX rates were used.
- Which assumptions changed between scenarios.
- Why a liquidity threshold is breached.
- Which factors explain forecast-versus-actual differences.
- Why an anomaly was flagged.
- Which forecast version and data snapshot produced a result.

Prefer transparent calculations and deterministic explanations over unsupported AI-generated financial conclusions. If an explanation is approximate, label it accordingly.

Do not introduce an LLM or paid external API unless there is a compelling requirement and the dependency is explicitly approved.

## 7. Architecture and Data Integrity

Maintain clear separation between:

- Synthetic-data generation.
- Data schemas and validation.
- Financial calculations.
- FX conversion.
- Forecasting and scenarios.
- Anomaly detection.
- Evaluation and ground-truth labels.
- Exports and reporting.
- User interface.

Use the existing architecture whenever possible. Avoid unnecessary abstractions, duplicate implementations, oversized modules, hidden global state, and expensive repeated processing of the full dataset.

Use efficient loading, filtering, aggregation, and caching where appropriate. Caching must not return stale results after the dataset, scenario, or forecast run changes.

Do not load the full dataset repeatedly for each UI component if a shared, read-only data layer can avoid that cost.

## 8. Testing and Verification

Run the existing test suite before and after significant changes.

Add focused tests for:

- Balance arithmetic and reconciliation.
- Multi-currency conversions and missing FX rates.
- Receipt and payment timing.
- Scenario differences.
- Forecast versioning and actual-versus-forecast metrics.
- Required anomaly cases and label separation.
- CLI behavior.
- Export schemas and required filenames.
- Web-interface data functions and a lightweight smoke test if practical.
- Reproducibility of deterministic outputs.

For each important change, report the exact command executed and whether it passed. Distinguish between tests actually run, tests not run, and features reviewed but not fully verified.

Use small fixtures for frequent testing and reserve full-scale dataset generation for appropriate validation checkpoints.

## 9. Documentation and Assessment Submission

Keep the documentation consistent with the implementation.

Update the README with:

- The financial problem CashPilot solves.
- Architecture and major workflows.
- Installation and environment setup.
- Commands to generate data, validate it, run forecasts, evaluate results, and launch the web interface.
- Dataset scale and reproducibility instructions.
- Sample outputs and limitations.
- Testing instructions.

Add architecture or workflow documentation as useful. Include clear screenshots of the actual running interface if the web interface is implemented.

Review the assessment's AI-use disclosure and prompt-history requirements. Update them with the prompts and relevant interactions actually used, without inventing conversation history or claiming work was personally reviewed if it was not.

Verify Git identity and public-repository readiness. Preserve existing commits and user changes. Make focused, meaningful commits for completed work rather than one enormous final commit.

## 10. Execution Plan and Reporting

Work in small, verifiable stages:

**Stage 1 — Baseline audit**
Inspect the code, run appropriate existing tests, map assessment requirements to current implementation, and identify the highest-risk gaps.

**Stage 2 — Core correctness**
Fix important financial calculation, FX, validation, and evaluation issues. Add deterministic tests.

**Stage 3 — Assessment completeness**
Verify dataset scale, anomaly cases, ground-truth separation, required exports, reproducibility, and documentation.

**Stage 4 — Product interface**
Implement the web interface using the existing engine, with financial workflows and traceable results.

**Stage 5 — Final verification**
Run tests, verify the main workflows, inspect exports, confirm documentation, and prepare a concise submission checklist.

Do not stop after producing a plan if the next implementation step is clear. Proceed through the stages while preserving existing work. If a major design decision or potentially destructive action is necessary, explain the trade-off and ask me before proceeding.

At the end of each stage, report:
- What you inspected or changed.
- Why it was necessary.
- Files affected.
- Tests and commands actually run.
- Results and remaining limitations.
- The next highest-priority task.

## Final success criteria

CashPilot should be a reproducible, tested, explainable, multi-currency financial liquidity management system with reliable forecasting, scenario analysis, anomaly detection, auditability, and exports. A useful web interface should make those capabilities accessible without replacing or duplicating the financial engine.

**Priority order: financial correctness → assessment completeness → traceability and explainability → usability → visual polish.**

Start by auditing the current repository and establishing a verified baseline. Then fix the most important gaps and implement the next stage. Do not rewrite working components unnecessarily, do not claim unverified success, and do not trade correct financial behavior for superficial features.
```

</details>

**AI response.** Worked through the five stages: a baseline audit and test run, hand-calculated FX / forecast / metric / CLI tests,
the `ground_truth.*` compatibility files, regenerated and re-verified datasets, an isolated Streamlit dependency test, a read-only
dashboard with a tested data layer, headless app tests, screenshots captured from the running app, documentation updates and this file.
See `git log` and [AI_USAGE.md](../AI_USAGE.md).

## 13. Commands to run the project (again)

> give me the commands to run the project

**AI response.** Listed the commands for the existing folder and for a fresh clone (tests, `cashpilot all`, dashboard) and useful extras.

## 14. Review the dashboard against the brief

The candidate sent a screenshot of the dashboard running in their own browser at `localhost:8501` (the first tab, *Cash overview*) and wrote:

> hey see this and inspect all the tabs are all we require and check the strcutre that are given in the problem rquirements . everything should user understandable

**AI response.** Inspected every tab's screenshot against the problem statement and reported what was missing (ledger entries, receivables and payables, entity and account master data, the acceptance criteria, the edge cases, the actors, the scale against the brief) and what a non-programmer would struggle with (raw column names, `None` cells, error rates as decimals, jargon, truncated text, a poor default view). Then added a *Start here* tab and an *Entities & transactions* tab, a plain-language module, friendlier tables and charts, tests, new screenshots and documentation, and fixed the problems the work uncovered (see AI_USAGE.md).

