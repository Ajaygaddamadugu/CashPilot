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


@pytest.fixture(scope="session")
def pipeline(starter_cfg):
    """Full starter pipeline: (generated dataset with ground truth, clean baseline, processed dataset)."""
    from cashpilot.engine.process import process
    from cashpilot.generate.pipeline import generate_dataset

    generated, clean, _ = generate_dataset(starter_cfg)
    return generated, clean, process(generated, starter_cfg)
