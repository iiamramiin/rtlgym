import os
import shutil

import pytest

TOOLS = ("iverilog", "verilator", "yosys")


def pytest_collection_modifyitems(config, items):
    missing = [t for t in TOOLS if shutil.which(t) is None]
    if not missing:
        return
    skip = pytest.mark.skip(reason=f"EDA tools not installed: {', '.join(missing)}")
    for item in items:
        if "needs_tools" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Each test gets its own result cache so tests never see stale grades."""
    from rtlgym import evaluator
    monkeypatch.setattr(evaluator, "CACHE_DIR", tmp_path / "cache")
    os.environ.setdefault("PYTHONHASHSEED", "0")
