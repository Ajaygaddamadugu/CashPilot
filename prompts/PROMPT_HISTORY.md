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

