from __future__ import annotations

import pytest

from feagent import config, store


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DUCKDB_PATH", str(tmp_path / "test.duckdb"))
    store.reset()
    yield
    store.reset()
