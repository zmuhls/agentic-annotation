"""Shared test isolation.

`poll` resolves its write targets (the watcher log, map, cursor, seen, actions,
emergent notes) to module-level paths inside the live working tree. Tests that
exercise `process()` reach the `log()` call even under `dry_run`, so without
isolation they append `test1 ... api down` noise to the operational
`logs/watcher.log` the daily health review reads. Redirect every mutable path to
a per-test tmp dir so the suite never touches production state.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import poll  # noqa: E402

# module-level path attributes on `poll` that any test run may write to
_WRITE_PATHS = (
    "LOG_FILE", "MAP_FILE", "SEEN_FILE", "CURSOR_FILE",
    "ACTIONS_DIR", "EMERGENT_FILE", "LOCK_FILE",
)


@pytest.fixture(autouse=True)
def isolate_poll_paths(tmp_path, monkeypatch):
    for attr in _WRITE_PATHS:
        original = getattr(poll, attr)
        monkeypatch.setattr(poll, attr, tmp_path / original.name)
