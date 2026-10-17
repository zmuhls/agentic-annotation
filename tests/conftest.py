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

import build_ia  # noqa: E402
import poll  # noqa: E402

# module-level path attributes on `poll` that any test run may write to
_WRITE_PATHS = (
    "LOG_FILE",
    "STDOUT_LOG",
    "MAP_FILE",
    "SEEN_FILE",
    "CURSOR_FILE",
    "ACTIONS_DIR",
    "EMERGENT_FILE",
    "LOCK_FILE",
    "NETFAIL_FILE",
    "AUTHFAIL_FILE",
    "HEALTH_FILE",
)


@pytest.fixture(autouse=True)
def isolate_poll_paths(tmp_path, monkeypatch):
    for attr in _WRITE_PATHS:
        original = getattr(poll, attr)
        monkeypatch.setattr(poll, attr, tmp_path / original.name)


@pytest.fixture(autouse=True)
def no_real_signal_handlers(monkeypatch):
    """Keep `poll.main()` from rebinding SIGTERM/SIGINT in the pytest process.

    The real handler calls sys.exit, so leaving it installed would turn a
    Ctrl-C during a test run into a half-swallowed exit. Stubbing registration
    rather than `install_interrupt_handlers` keeps that function itself under
    test; monkeypatch restores the real `signal.signal` afterwards.
    """
    monkeypatch.setattr(poll.signal, "signal", lambda sig, handler: None)


# Fictional stand-ins for the real placement tables, which live in the
# gitignored routing.json. Tests assert against these so the suite passes on a
# fresh clone, keeps personal group ids out of this public repo, and does not
# change meaning when the maintainer re-maps a group.
_ROUTING = {
    "GROUP_NAMES": {"__world__": "Public", "DISS01": "diss"},
    "ARTIFACT_DOMAINS": {"mysite.example": "artifacts/personal-site"},
    "GROUP_DOMAIN_OVERRIDES": [
        {"group": "DISS01", "domain_contains": "forum.example", "node": "dissertation/corpus"},
    ],
    "GROUP_NODES": {"DISS01": "dissertation/sources", "TEACH1": "teaching/writing-courses"},
    "DOMAIN_CONTAINS": {"forum.example": "dissertation/corpus"},
    "DOMAIN_NODES": {"papers.example": "reading/ai-ml"},
    "GENERAL_GROUPS": frozenset({"__world__", "MISC01"}),
    "GENERAL_NODE": "reading/general",
    "DEFAULT_NODE": "inbox",
}


@pytest.fixture
def routing(monkeypatch):
    for name, value in _ROUTING.items():
        monkeypatch.setattr(build_ia, name, value)
