# How AI Was Used

## Purpose and transparency

This document explains how AI-assisted tools were used during the CashPilot challenge, what work they accelerated, the decisions and direction provided by the candidate, and what still needs to be independently reviewed. The complete prompt history is available in [`prompts/PROMPT_HISTORY.md`](prompts/PROMPT_HISTORY.md). AI-assisted commits include a `Co-Authored-By: Claude` trailer.

## Tool used

- **Claude Code (Anthropic)** was used inside VS Code on Windows, with access to the project folder, terminal, and Git.
- The work primarily used Claude Opus 5.5; Claude Sonnet 5.5 was used during the later review and dashboard phase. The relevant commit trailers record the model where available.
- Only Claude was used: no other AI assistant or LLM tool helped with the code, the documentation or this disclosure. GitHub was used to host and push the repository.

## Candidate direction and engineering workflow

The candidate set the project goal, supplied the assessment brief and submission guidance, created the public GitHub repository, reviewed the proposed plan, and directed the work toward the challenge requirements. The candidate also reviewed the running UI through screenshots, asked questions about the financial concepts and user experience, identified areas that needed to be easier to understand, and requested targeted improvements rather than an unnecessary rewrite.

The work was organized in stages:

1. **Plan before implementation:** convert the brief into a requirements breakdown, data model, edge-case strategy, validation plan, and 72-hour build order.
2. **Build in layers:** establish the package and core helpers, generate synthetic data, implement the financial engine and scenarios, add anomaly detection and validation, and then add CLI, exports, evaluation, and reproducibility.
3. **Review and harden:** inspect the existing implementation, add targeted financial and CLI tests, address assessment-file naming, and verify reproducibility.
4. **Add a read-only web interface:** build a Streamlit UI on top of the existing engine instead of duplicating financial calculations. The interface covers cash overview, accounts and currencies, entities and transactions, forecasts, cash-flow drivers, exceptions, actual-versus-forecast, and audit/exports.
5. **Record decisions and evidence:** document design choices in [`docs/DECISION_LOG.md`](docs/DECISION_LOG.md), keep the prompt history, and capture screenshots of the running dashboard.
6. **Make the full-scale data reviewable:** commit the full dataset's CSV files (30 entities, 150 accounts, 100,000 ledger entries, 20,000 forecast items) after checking every checksum against the manifest. The JSON and SQL renderings stay out of git because GitHub rejects files over 100 MB; decision D-046 explains this.

## Where AI accelerated the work

AI assistance was used to draft and implement substantial parts of:

- The requirements traceability structure and data model, including the 34-table data dictionary.
- Synthetic-data generators and the Markdown/SQL data-dictionary outputs.
- Core financial calculations, workflow logic, anomaly detectors, validation, exporters, CLI commands, and tests.
- Performance investigation and optimization at full dataset scale.
- Documentation, reproducibility checks, and the read-only dashboard.
- UI review iterations focused on financial clarity, labels, technical details, and traceability from summary values to underlying records.

The candidate provided direction, reviewed outputs, asked follow-up questions, and requested changes when the result did not sufficiently explain the financial information or the assessment requirements.

## Extent of AI assistance

AI generated a substantial portion of the code, tests, and documentation under the candidate's direction. This was an AI-assisted engineering project, not a claim that every line was written manually. The candidate's role included setting scope, approving the staged approach, creating and maintaining the repository workflow, reviewing the product through the running UI, identifying usability and explanation gaps, and directing follow-up work. The design rationale and limitations are documented so reviewers can inspect the implementation rather than relying on unsupported claims.

## Issues found and addressed during development

The following issues were identified during implementation or review. The fixes and their supporting evidence are referenced in the project history and tests where applicable.

| Issue identified | How it was identified | Response |
|---|---|---|
| Some bulk receipts were posted twice | Generation-run failure and data inspection | Track posted entries explicitly. |
| Artificial fee entries were being used to reach the 100,000-row ledger target | Review of entry-type distribution | Use fixed-point iteration to reach the required volume without padding the ledger with artificial fees. |
| Starter-profile group cash fell sharply | Position-calculation smoke test | Recalibrate one-off flow sizes. |
| Some account-days breached overdraft limits | Dedicated overdraft validation | Add same-day pre-funding and overdraft protection logic. |
| Duplicate already-paid items could pass the data-quality gate | Review of gate logic | Match against all items known at the cutoff, not only open items. |
| Too few cross-currency invoices were available for mixed-currency cases | Anomaly injection could not create the intended cases | Increase the foreign-customer share to support the intended test cases. |
| An injected item's revisions retained the previous currency | Validator failure | Ensure revisions follow the item's currency. |
| The starter bundle was larger than intended | Size check before commit | Reduce the frequency of starter-profile runs. |
| Documentation overstated full-dataset size | Compare README with generated manifest | Correct the documented row and storage estimates. |
| A reproducibility run encountered a OneDrive folder-lock issue | Background cleanup failed after generation | Improve retry/cleanup handling and rerun the reproducibility check. |
| Missing FX rates could understate an entity total and distort an accuracy metric | Targeted FX audit | Mark totals incomplete, skip incomplete actuals in the accuracy metric, and count them separately. |
| Invalid CLI inputs produced raw tracebacks | CLI test development | Return a clear error message and exit code 2. |
| A dashboard display change caused tab failures | Review of rendered screenshots and app tests | Fix the date-column handling, rerun app tests, and recapture screenshots. |
| A group-level forecast message obscured entity-level buffer breaches | Screenshot review | Explain that a healthy group total can hide an individual entity shortfall. |
| Some required data and workflow areas were not obvious in the UI | Compare screenshots with the assessment brief | Add the Start here and Entities & transactions tabs. |
| Technical labels and long tables were difficult to read | UI screenshot review | Improve wording and table presentation, and use clearer defaults. |
| A test used an assertion that did not actually verify behavior | Test-file review | Replace it with a real assertion. |
| Technical identifiers and raw chart/table details were too prominent | Review of running dashboard screenshots | Improve labels, chart presentation, and grouping of technical details while retaining traceability. |
| A chart helper name collided with a real data column | Dashboard test failure | Use distinct internal column names. |
| Waterfall labels overlapped and the worked FX example was not illustrative | Review of rendered screenshots | Improve label layout and choose a foreign-currency account for the example. |
| A cleanup command could match its own process | Command behavior during test-server cleanup | Replace it with a narrower process-targeting script. |
| In Edge the number cards showed `40,265,...` instead of the full figure | The candidate sent a screenshot; the AI measured it in a real browser: the card was narrower than the 2.25 rem number at the window's real width | The value font now follows the card width and labels wrap (CSS only, no number changed); tabs wrap instead of hiding behind arrows; a browser check finds 0 clipped items at six widths, down from 80 |
| The first version of that browser check reported no clipped numbers at all, although they were clipped | Comparing it with the candidate's screenshot and inspecting the page structure | The clip was on the number's container, not on the text element it looked at; the check now looks at the container |
| A layout test would not start the dashboard | The test failed with no output | The dashboard's start-up message printed a folder path containing Japanese characters, which fails when output is redirected; the test now uses a relative path (the command itself was left unchanged, and real use in a terminal works) |
| A commit was pushed while one test was failing (the test's assertion about the page title was wrong), because running the tests and committing were chained in one command | The CI run for that commit was red | The assertion was fixed in the next commit; later commands only commit when the tests pass. |
| A broad process-stop command risked affecting unrelated Python processes | Permission system blocked the command | Narrow the target so it only addresses the AI's own test process. |

## Second phase: financial hardening and dashboard

After the initial implementation, the candidate requested a codebase review, followed by a broader pass to check financial correctness, close assessment gaps, and add a web interface using the existing engine. That phase included:

1. **Baseline review:** inspect the repository, existing tests, and FX handling.
2. **Financial correctness:** add hand-calculated tests for FX, balances, forecast timing, scenarios, and metrics, along with CLI tests.
3. **Assessment completeness:** add the requested `ground_truth.csv` and `ground_truth.json` names while retaining the existing anomaly files, and verify generated bundles and reproducibility.
4. **Dashboard:** test Streamlit as an optional dependency, keep financial calculations in the existing engine, test the dashboard data layer against engine outputs, and capture screenshots from the running app.
5. **Verification:** run the test suite and relevant generation/reproducibility checks, and use CI results where available.

The dashboard is intentionally read-only. It presents financial results and audit information; it does not add fake approval or save actions or replace the permission-checked CLI workflow.

## What the candidate reviewed, changed or validated

This lists only what the prompt history and the repository evidence. Nothing is ticked that they do not.

- [x] Supplied the assessment brief and the submission guidelines and asked for a complete plan before any implementation.
- [x] Created the public GitHub repository and approved the push workflow (small, meaningful commits).
- [x] Questioned why an unfamiliar git author name (`Finpark`) appeared and whether the AI had accessed GitHub (it had not: the name came from the local git configuration).
- [x] Asked that the work stay limited to this project rather than changing other projects or global settings.
- [x] Ran `pytest` and `cashpilot all --profile starter` locally and checked the output (the candidate pasted the terminal logs and asked whether every test had passed).
- [x] Ran `cashpilot dashboard` in their own browser, went through the tabs and sent screenshots. This led to the *Start here* and *Entities & transactions* tabs, plain-language wording, removal of technical names, codes and the Deploy button, input-calculation-result explanations with clearer charts, the name moved to the top-left corner and larger tab names.
- [x] Asked whether receivables and payables use expected dates, and asked for a checklist of every requirement and every submission guideline before submitting.
- [x] Asked for the full-scale 30-entity dataset to be pushed so reviewers can see it; the AI explained why only its CSV files can be (D-046).
- [x] Reviewed this disclosure and asked for it to be accurate before submission.

Not claimed here, because the prompt history has no evidence of them: a line-by-line reading of [`docs/DESIGN.md`](docs/DESIGN.md), [`docs/RULES.md`](docs/RULES.md) and [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md); comparing dashboard values with the CSV files by hand; spot-checking generated tables against the rules. [`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md) is the script for explaining the solution.

## Independent verification

Results when this file was last updated (2026-10-27):

- Full test suite: 172 passed and 1 skipped. The skipped test is the opt-in real-browser layout check (`CASHPILOT_LAYOUT_TEST=1`), which was run separately and passed.
- CI on commit `b2ab659`: success on Ubuntu and Windows.
- Fresh clone of the public repository: all 34 full-dataset CSV files match their checksums in `data/full/manifest.json`, and the dashboard loads the 30-entity dataset.

Anyone can repeat the checks from the project environment:

```bash
pytest
cashpilot all --profile starter --out out/me   # compare out/me/manifest.json with data/starter/manifest.json
cashpilot repro-check --profile starter        # two fresh runs, every checksum compared
cashpilot dashboard
```

A successful command is evidence for that check only; it does not by itself prove every assessment requirement is satisfied.

## Limitations and ownership

CashPilot uses synthetic financial data; it is not connected to real bank accounts. The reporting currency is currently USD. The dashboard is a read-only interface over the existing engine. Any remaining limitations should be reviewed in [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) and described accurately in the submission.

This disclosure is meant to be transparent about AI assistance while documenting the candidate's direction and review activities.
