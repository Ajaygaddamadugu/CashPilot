# Data provenance and lawful use

**All data in this repository is synthetic.** It was produced by the code in `src/cashpilot/generate/`
from a fixed seed (`20261022`). No external dataset, API, web page or personal data was accessed,
copied or transformed, so there are no licences, terms of use or attributions to honour and
nothing was discarded from an external source.

| Item | Source | Notes |
|---|---|---|
| Legal entities, counterparties, banks | Generated from small word lists in `generate/common.py` | Fictional names; any resemblance to real companies is coincidental. Account numbers are masked synthetic digits (`****1234`). |
| Users | Role labels ("Operations Analyst 01") | No personal data |
| Currency codes and decimal places | ISO 4217 (public standard) | Used only as reference data: USD, EUR, GBP, INR, JPY and their minor units |
| FX rates | Correlated geometric random walks (`generate/master.py`) | Starting levels are round illustrative numbers chosen by the author (e.g. EUR 1.085 USD), not copied from any rate source; source is recorded as `SYNTHETIC_GBM` on every row |
| Business behaviour | Documented rules in [RULES.md](RULES.md) | Parameters are judgement-based and stated explicitly |
| Holiday calendar | Weekends + 1 Jan and 25 Dec | Simplification, see [LIMITATIONS.md](LIMITATIONS.md) |

Each dataset bundle carries this statement in `README.md` and in `manifest.json`
(`provenance`, `external_sources: []`), together with the generator version, library versions,
seed, the exact command and SHA-256 checksums of every file.

Retrieval date / version / licence fields of the brief's guidance therefore do not apply. If
external reference data were added later (for example published FX fixings), the manifest's
`external_sources` list is where URL, dataset version, retrieval date, licence, attribution,
transformations and discarded fields would be recorded.
