import pytest

from cashpilot.core.config import load_config
from cashpilot.generate.pipeline import generate_baseline


@pytest.fixture(scope="session")
def starter_cfg():
    return load_config("starter")


@pytest.fixture(scope="session")
def baseline(starter_cfg):
    """Clean starter baseline (before anomaly injection), generated once per test session."""
    ds, world = generate_baseline(starter_cfg)
    return ds, world
