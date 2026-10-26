"""Typed access to the data dictionary (``dictionary.yaml``)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

DICTIONARY_PATH = Path(__file__).resolve().parent / "dictionary.yaml"

# Layers that hold source data. Derived/output tables are produced by CashPilot itself,
# and ground truth is kept apart from everything else.
INPUT_LAYERS = ("reference", "master", "transaction", "event", "bridge", "history")


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    required: bool
    description: str
    allowed: tuple | None = None
    pattern: str | None = None
    fk: str | None = None
    unique: bool = False
    units: str | None = None
    currency_field: str | None = None
    currency: str | None = None
    rule: str | None = None
    minimum: float | None = None

    @property
    def fk_table(self) -> str | None:
        return self.fk.split(".")[0] if self.fk else None

    @property
    def fk_column(self) -> str | None:
        return self.fk.split(".")[1] if self.fk else None


@dataclass(frozen=True)
class Table:
    name: str
    layer: str
    description: str
    grain: str
    primary_key: tuple[str, ...]
    columns: tuple[Column, ...]
    unique_together: tuple[tuple[str, ...], ...] = ()
    bridge: str | None = None
    event_of: str | None = None

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def column(self, name: str) -> Column:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(f"{self.name}.{name}")

    @property
    def is_input(self) -> bool:
        return self.layer in INPUT_LAYERS


@dataclass(frozen=True)
class Lifecycle:
    entity: str
    event_table: str
    key: str
    transitions: tuple[tuple[str, str | None, str], ...]  # (event, from, to)
    terminal: tuple[str, ...]
    status_column: str | None = None
    event_column: str = "event_type"
    order_column: str | None = None
    initial: str | None = None


@dataclass(frozen=True)
class Schema:
    tables: dict[str, Table]
    lifecycles: dict[str, Lifecycle]

    def table(self, name: str) -> Table:
        return self.tables[name]

    @property
    def dataset_tables(self) -> list[str]:
        """Every table that belongs to the dataset (ground truth excluded)."""
        return [n for n, t in self.tables.items() if t.layer != "ground_truth"]

    def foreign_keys(self) -> list[tuple[Table, Column]]:
        return [(t, c) for t in self.tables.values() for c in t.columns if c.fk]

    def topological_order(self, names: list[str] | None = None) -> list[str]:
        """Parents before children (self-references ignored); ties keep dictionary order."""
        names = list(names or self.dataset_tables)
        wanted = set(names)
        deps = {
            n: {c.fk_table for c in self.tables[n].columns if c.fk and c.fk_table != n and c.fk_table in wanted}
            for n in names
        }
        order: list[str] = []
        while len(order) < len(names):
            progressed = False
            for n in names:
                if n not in order and deps[n] <= set(order):
                    order.append(n)
                    progressed = True
            if not progressed:
                raise ValueError(f"Foreign-key cycle among: {sorted(set(names) - set(order))}")
        return order


def _column(spec: dict) -> Column:
    return Column(
        name=spec["name"],
        type=spec["type"],
        required=bool(spec.get("required", False)),
        description=spec.get("description", ""),
        allowed=tuple(spec["allowed"]) if "allowed" in spec else None,
        pattern=spec.get("pattern"),
        fk=spec.get("fk"),
        unique=bool(spec.get("unique", False)),
        units=spec.get("units"),
        currency_field=spec.get("currency_field"),
        currency=spec.get("currency"),
        rule=spec.get("rule"),
        minimum=spec.get("minimum"),
    )


@lru_cache(maxsize=1)
def load_schema() -> Schema:
    raw = yaml.safe_load(DICTIONARY_PATH.read_text(encoding="utf-8"))
    tables = {}
    for name, spec in raw["tables"].items():
        tables[name] = Table(
            name=name,
            layer=spec["layer"],
            description=spec["description"],
            grain=spec["grain"],
            primary_key=tuple(spec["primary_key"]),
            columns=tuple(_column(c) for c in spec["columns"]),
            unique_together=tuple(tuple(u) for u in spec.get("unique_together", [])),
            bridge=spec.get("bridge"),
            event_of=spec.get("event_of"),
        )
    lifecycles = {}
    for entity, spec in raw.get("lifecycles", {}).items():
        lifecycles[entity] = Lifecycle(
            entity=entity,
            event_table=spec["event_table"],
            key=spec["key"],
            transitions=tuple((t["event"], t["from"], t["to"]) for t in spec["transitions"]),
            terminal=tuple(spec["terminal"]),
            status_column=spec.get("status_column"),
            event_column=spec.get("event_column", "event_type"),
            order_column=spec.get("order_column"),
            initial=spec.get("initial"),
        )
    return Schema(tables=tables, lifecycles=lifecycles)
