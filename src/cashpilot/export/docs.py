"""Render the data dictionary as Markdown (docs/DATA_DICTIONARY.md)."""

from __future__ import annotations

from cashpilot.schema import Schema, Table

TEMPORAL_COLUMNS = (
    "effective_from", "effective_to", "opened_on", "opening_balance_date", "closed_on",
    "active_from", "rate_date", "cutoff_date", "knowledge_cutoff_ts", "recorded_at",
)

LAYER_NOTES = {
    "reference": "Reference data and configuration (currencies, users, counterparties, FX, scenarios).",
    "master": "Master data created first: legal entities and bank accounts.",
    "transaction": "Business documents and cash movements that reference master data.",
    "event": "Append-only state-change history; current status is derived from it.",
    "bridge": "Bridge tables resolving many-to-many relationships.",
    "history": "Forecast versions and their input lineage, kept immutable.",
    "derived": "Values CashPilot computes from source records (never sampled).",
    "output": "Exceptions, workflow and audit records produced by CashPilot.",
    "ground_truth": "Labels for injected anomalies, stored outside the dataset.",
}


def _esc(text) -> str:
    return "" if text is None else str(text).replace("|", "\\|")


def _allowed(col) -> str:
    parts = []
    if col.allowed:
        parts.append(", ".join(f"`{a}`" for a in col.allowed))
    if col.pattern:
        parts.append(f"pattern `{col.pattern}`")
    if col.minimum is not None:
        parts.append(f"≥ {col.minimum:g}")
    return "<br>".join(parts)


def _type(col) -> str:
    if col.type == "money":
        return f"money ({col.currency or 'in ' + col.currency_field})"
    return col.type


def _cardinality(table: Table, col) -> str:
    unique = col.unique or (table.primary_key == (col.name,))
    return "1:1" if unique else "N:1"


def render_data_dictionary(schema: Schema) -> str:
    out: list[str] = []
    out.append("# Data dictionary\n")
    out.append(
        "Generated from `src/cashpilot/schema/dictionary.yaml`, the single source of truth that also "
        "produces `sql/schema.sql` and drives the structural validators. Do not edit by hand.\n"
    )
    out.append(
        "**Conventions.** Dates are `YYYY-MM-DD`; timestamps are UTC `YYYY-MM-DDTHH:MM:SSZ`. Money is a "
        "fixed-decimal string in the stated currency, with ISO 4217 decimals (JPY has none); internally it "
        "is held as integer minor units. Rates are USD per one unit of the base currency, 8 decimals. "
        "`status_at_end` columns are derived from the matching event table as of the end of the actuals "
        "period; the event tables are the authoritative history.\n"
    )

    out.append("## Tables\n")
    out.append("| Table | Layer | Grain | Primary key |")
    out.append("|---|---|---|---|")
    for t in schema.tables.values():
        out.append(f"| [`{t.name}`](#{t.name}) | {t.layer} | {_esc(t.grain)} | `{', '.join(t.primary_key)}` |")
    out.append("")
    out.append("Layers: " + " ".join(f"**{k}** — {v}" for k, v in LAYER_NOTES.items()) + "\n")

    out.append("## Relationships\n")
    out.append("Every foreign key, with cardinality (child : parent) and whether the child must have a parent.\n")
    out.append("| Child column | Parent | Cardinality | Optional |")
    out.append("|---|---|---|---|")
    for t, c in schema.foreign_keys():
        out.append(f"| `{t.name}.{c.name}` | `{c.fk}` | {_cardinality(t, c)} | {'no' if c.required else 'yes'} |")
    out.append("")
    out.append("**Many-to-many relationships** are resolved by bridge tables:\n")
    for t in schema.tables.values():
        if t.bridge:
            out.append(f"- `{t.name}`: {t.bridge}")
    out.append("")

    out.append("## Effective dates and lifecycles\n")
    out.append("Columns that make records time-aware:\n")
    for t in schema.tables.values():
        cols = [c.name for c in t.columns if c.name in TEMPORAL_COLUMNS]
        if cols and t.layer not in ("ground_truth",):
            out.append(f"- `{t.name}`: " + ", ".join(f"`{c}`" for c in cols))
    out.append("")
    out.append("State machines enforced by the validator (an event must start from the current state):\n")
    for lc in schema.lifecycles.values():
        out.append(f"### {lc.entity} (history in `{lc.event_table}`)\n")
        out.append("| Event | From | To |")
        out.append("|---|---|---|")
        for event, src, dst in lc.transitions:
            out.append(f"| `{event}` | {('`' + src + '`') if src else '(new)'} | `{dst}` |")
        initial = f" Items start as `{lc.initial}`." if lc.initial else ""
        out.append(f"\nTerminal states: {', '.join(f'`{s}`' for s in lc.terminal)}.{initial}\n")

    out.append("## Columns\n")
    for t in schema.tables.values():
        out.append(f"### {t.name}\n")
        out.append(f"{_esc(t.description)}\n")
        extras = [f"Layer: **{t.layer}**", f"Grain: {t.grain}", f"Primary key: `{', '.join(t.primary_key)}`"]
        if t.unique_together:
            extras.append("Unique: " + "; ".join(f"`({', '.join(u)})`" for u in t.unique_together))
        out.append(" · ".join(extras) + "\n")
        out.append("| Column | Type | Required | Allowed values / format | Units | Unique | References | Validation rule | Description |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for c in t.columns:
            unique = "yes" if (c.unique or t.primary_key == (c.name,)) else ""
            out.append(
                f"| `{c.name}` | {_type(c)} | {'yes' if c.required else 'no'} | {_esc(_allowed(c))} | "
                f"{_esc(c.units)} | {unique} | {('`' + c.fk + '`') if c.fk else ''} | {_esc(c.rule)} | {_esc(c.description)} |"
            )
        out.append("")
    return "\n".join(out)
