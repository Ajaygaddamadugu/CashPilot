# How AI was used

The submission guidelines allow LLM tools and ask for transparency. This file says plainly what
the AI did, where it accelerated or carried the work, and what the candidate reviewed. The full
prompt history is in [prompts/PROMPT_HISTORY.md](prompts/PROMPT_HISTORY.md); every AI-assisted
commit carries a `Co-Authored-By: Claude` trailer.

## Tool

* **Claude Code** (Anthropic's coding agent) inside VS Code on Windows, with access to the project
  folder, a terminal and git. Most of the work used model Claude Opus 5.5; the model was switched to
  Claude Sonnet 5.5 (via `/model`) near the end, and the later commits carry that model in their
  `Co-Authored-By` trailer.
* No other LLM tools were used. No data was sent to external services other than the model and
  GitHub (`git push`).

## How the work was organised

1. **Plan first.** The candidate pasted the brief and the submission guidelines and asked for a
   plan covering every requirement *before* any code. The AI produced a requirements breakdown,
   design decisions, data model, edge-case strategy, validation and test plan, and a 72-hour
   build order. Implementation started only after the candidate created the GitHub repository and
   sent its link.
2. **Build in layers, each tested, committed and pushed:** skeleton → data dictionary and core
   helpers → generator → engine → anomaly injection and history → detection and workflow →
   validation → CLI, export, evaluation and reproducibility → data bundles → CI and docs.
3. **Decisions recorded as they were made** in [docs/DECISION_LOG.md](docs/DECISION_LOG.md).

## Where AI accelerated the work

* Turning the brief into a requirements traceability matrix and a data model with 34 tables.
* Writing the data dictionary, its generators (Markdown, SQL DDL) and the structural validators.
* Generator, engine, workflow, detectors, validation suite, exporters, CLI and tests.
* Profiling and optimising (account lookups 73 s → 10 s at full scale; projection arrays).
* Documentation drafts.

## Where the work relied heavily on AI

Honestly: almost all code, tests and documentation in this repository were written by the AI,
under the candidate's direction (scope, plan approval, repository setup, go-ahead). The
reasoning behind each design choice is written down in `docs/` so that it can be inspected and
defended rather than taken on trust.

## Problems the AI found in its own work and fixed (verified by tests or checks)

| Problem found | How it was caught | Fix | Where |
|---|---|---|---|
| Bulk receipts posted twice | traceback during the first generation run | track posted entries explicitly | commit "feat(generate): master data…" |
| ~400 artificial "fees" padding the ledger to 100,000 rows | inspecting the entry-type mix | fixed-point iteration for the exact volume (D-016) | same commit |
| Group cash drained from $80M to $5M in the starter profile | positions smoke test | one-off sizes recalibrated | "feat(engine): daily positions…" |
| 552 account-days below overdraft limits | dedicated overdraft check | same-day pre-funding (a Friday pre-funding was swept back before Monday payroll), overdraft protection (D-021) | same commit |
| Duplicates of already-paid items slipped through the data-quality gate | design review of the gate | match against all items known at the cutoff, not only open ones | same commit |
| Too few cross-currency invoices to inject mixed-currency cases | injection failed loudly | foreign-customer share 15% → 25% | "feat(generate): labelled edge cases…" |
| Revisions of an injected item kept the old currency | validator check `I-JOIN-revision-currency` FAILED | the item's own revisions follow its currency | same commit |
| Committed starter bundle 79 MB | size check before committing | fortnightly runs in the starter profile | data commit |
| Docs overstated the full dataset (~1.4 M rows, ~0.5 GB) | cross-checking README figures against the generated manifest | corrected to ~1.2 M rows, ~0.6 GB | commit d75d9d7 |
| First full reproducibility run crashed deleting a folder locked by OneDrive | background task failed after generation had succeeded | retrying cleanup in `repro-check`, then re-ran: 82/82 files identical | commit d75d9d7 |
| A missing FX rate leaves an entity total understated (flagged INCOMPLETE) and could have skewed the balance-accuracy metric | targeted audit of FX handling at the start of the second phase | metric now skips incomplete actuals and counts them; hand-calculated tests; no committed number changed | `test+fix:` commit |
| Bad input produced raw Python tracebacks (missing dataset folder, malformed date) | writing the CLI tests | clean `error:` messages and exit code 2 | `test+fix:` commit |
| Dashboard crashed on every tab after a display tweak (pandas rejects `datetime64[us]` in `select_dtypes`) | looking at the captured screenshot (file sizes had looked plausible); the app tests had not been re-run after that edit | fixed; the 8 app tests re-run and pass; screenshots retaken and inspected one by one | `feat(dashboard)` commit |
| Forecast tab said "no projected day is below the buffer" for the group while two entities did breach | reviewing the screenshot | the message now says a group total can hide an entity shortfall | `feat(dashboard)` commit |

## Second phase: hardening and the web dashboard

After the first delivery the candidate asked for an inspection of the code base (prompt 11 in the prompt history) and then
for a broader pass (prompt 12): verify financial correctness, close assessment gaps and add a web interface that consumes the
existing engine. This phase used Claude Sonnet 5.5 and followed the staged plan in that prompt:

1. **Baseline audit** - working tree clean, 49 tests passing, FX handling traced (finding above).
2. **Core correctness** - hand-calculated fixtures for FX, positions, forecast timing and metrics; CLI tests.
3. **Assessment completeness** - `ground_truth.csv|json` names with aliases, required-file test, regenerated starter and full bundles with fresh reproducibility proofs.
4. **Dashboard** - Streamlit extra chosen after an isolated install test under the pinned versions; a Streamlit-free data layer reconciled with the engine in tests; the running app was driven headlessly and screenshots were captured from it with a small script and each one was looked at.
5. **Verification** - full suite, fresh clone, CI (reported in the final message of that session, not here, because the results are only known after the push).

What the AI did **not** do: it did not claim the dashboard works without running it, it did not change expected results to make a test pass,
and it left the "what the candidate reviewed" section below for the candidate to complete.

## What the candidate reviewed, changed or validated

> **To be completed by the candidate before submission** - only you can state this. Keep what
> is true, delete what is not, add your own observations.

Visible in the prompt history:

- [x] Required a complete plan covering every point of the brief before any implementation.
- [x] Questioned why an unfamiliar git author name (`Finpark`) appeared and whether the AI had
      accessed GitHub (it had not: the name came from the local git configuration).
- [x] Restricted the work to this project only (no other folders, projects or global settings).
- [x] Created the public GitHub repository with the recommended empty settings and approved the
      push workflow (small, meaningful commits).

To confirm yourself (suggested):

- [ ] Ran `pytest` and `cashpilot all --profile starter` locally and saw them pass.
- [ ] Walked through [docs/WALKTHROUGH.md](docs/WALKTHROUGH.md) and can explain each step.
- [ ] Read [docs/DESIGN.md](docs/DESIGN.md), [docs/RULES.md](docs/RULES.md) and
      [docs/LIMITATIONS.md](docs/LIMITATIONS.md) and agree with the decisions, or noted where not.
- [ ] Ran `cashpilot dashboard` and looked at each tab, comparing a few numbers with the CSV files.
- [ ] Opened a few generated tables (e.g. `data/starter/csv/ledger_entry.csv`,
      `ground_truth/ground_truth.csv`) and spot-checked records against the rules.
- [ ] Any changes you made yourself: …

## How to check the AI's claims independently

```bash
pytest                                        # 130 tests, incl. the four acceptance criteria
cashpilot all --profile starter --out out/me  # regenerate; compare out/me/manifest.json with data/starter/manifest.json
cashpilot repro-check --profile starter       # two fresh runs, every checksum compared
```
