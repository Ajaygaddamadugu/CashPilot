"""Scale profiles (starter / full) loaded from YAML."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


@dataclass(frozen=True)
class Config:
    raw: dict

    @property
    def profile(self) -> str:
        return self.raw["profile"]

    @property
    def seed(self) -> int:
        return int(self.raw["seed"])

    @property
    def cycle_year(self) -> int:
        return int(self.raw["calendar"]["cycle_year"])

    @property
    def start_date(self) -> date:
        return self.raw["calendar"]["start_date"]

    @property
    def actuals_end(self) -> date:
        return self.raw["calendar"]["actuals_end"]

    @property
    def schedule_end(self) -> date:
        return self.raw["calendar"]["schedule_end"]

    @property
    def lookback_days(self) -> int:
        return int(self.raw["calendar"]["history_lookback_days"])

    @property
    def reporting_currency(self) -> str:
        return self.raw["reporting_currency"]

    @property
    def currencies(self) -> list[str]:
        return list(self.raw["currencies"])

    @property
    def foreign_currencies(self) -> list[str]:
        return [c for c in self.currencies if c != self.reporting_currency]

    @property
    def volumes(self) -> dict:
        return self.raw["volumes"]

    @property
    def entity_mix(self) -> dict:
        return self.raw["entity_mix"]

    @property
    def lifecycle(self) -> dict:
        return self.raw["lifecycle"]

    @property
    def forecast(self) -> dict:
        return self.raw["forecast"]

    @property
    def policy(self) -> dict:
        return self.raw["policy"]

    @property
    def anomalies(self) -> dict:
        return self.raw["anomalies"]

    def config_hash(self) -> str:
        canonical = json.dumps(self.raw, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_config(profile: str = "starter", seed: int | None = None) -> Config:
    """Load a profile by name (``starter``/``full``) or by path to a YAML file."""
    path = Path(profile)
    if path.suffix not in (".yaml", ".yml"):
        path = PROFILES_DIR / f"{profile}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if seed is not None:
        raw["seed"] = int(seed)
    cfg = Config(raw)
    _check(cfg)
    return cfg


def _check(cfg: Config) -> None:
    v = cfg.volumes
    if sum(cfg.entity_mix.values()) != v["legal_entities"]:
        raise ValueError("entity_mix must sum to volumes.legal_entities")
    if cfg.entity_mix.get(cfg.reporting_currency, 0) < 1:
        raise ValueError("at least one entity (the holding) must use the reporting currency")
    if set(cfg.entity_mix) - set(cfg.currencies):
        raise ValueError("entity_mix uses a currency that is not in `currencies`")
    if v["bank_accounts"] < 2 * v["legal_entities"]:
        raise ValueError("need at least two bank accounts per entity")
    if not cfg.start_date < cfg.actuals_end < cfg.schedule_end:
        raise ValueError("calendar must satisfy start_date < actuals_end < schedule_end")
