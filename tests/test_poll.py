"""Tests for the classify/parse path in poll.py.

The `claude` subprocess is always mocked — these tests never shell out to the
CLI and never spend real API money.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import poll  # noqa: E402


class FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _wrap(result_text):
    """Mimic `claude -p --output-format json` envelope."""
    return json.dumps({"type": "result", "result": result_text})


class TestCallSonnet:
    def test_parses_clean_json_object(self, monkeypatch):
        payload = {"node": "inbox", "new_node": False, "role": "r", "actions": []}
        monkeypatch.setattr(poll.subprocess, "run",
                            lambda *a, **k: FakeProc(stdout=_wrap(json.dumps(payload))))
        assert poll.call_sonnet("prompt") == payload

    def test_strips_prose_around_json(self, monkeypatch):
        text = 'Sure!\n{"node": "inbox", "actions": []}\nHope that helps.'
        monkeypatch.setattr(poll.subprocess, "run",
                            lambda *a, **k: FakeProc(stdout=_wrap(text)))
        assert poll.call_sonnet("prompt")["node"] == "inbox"

    def test_handles_list_envelope(self, monkeypatch):
        # some CLI versions emit a list of message objects
        envelope = json.dumps([
            {"type": "system"},
            {"type": "result", "result": '{"node": "reading/general", "actions": []}'},
        ])
        monkeypatch.setattr(poll.subprocess, "run",
                            lambda *a, **k: FakeProc(stdout=envelope))
        assert poll.call_sonnet("prompt")["node"] == "reading/general"

    def test_raises_on_nonzero_exit(self, monkeypatch):
        monkeypatch.setattr(poll.subprocess, "run",
                            lambda *a, **k: FakeProc(returncode=1, stderr="boom"))
        monkeypatch.setattr(poll.time, "sleep", lambda *a: None)  # no real wait
        with pytest.raises(RuntimeError, match="claude exited 1"):
            poll.call_sonnet("prompt", attempts=1)

    def test_raises_when_no_json(self, monkeypatch):
        monkeypatch.setattr(poll.subprocess, "run",
                            lambda *a, **k: FakeProc(stdout=_wrap("no json here")))
        with pytest.raises(ValueError, match="no JSON"):
            poll.call_sonnet("prompt")


class TestProcess:
    def _ann(self, **over):
        base = {
            "id": "test1", "uri": "https://zmuhls.github.io/x",
            "document": {"title": ["T"]}, "tags": ["revision"],
            "target": [{"selector": [
                {"type": "TextQuoteSelector", "exact": "quoted bit"}]}],
            "created": "2026-07-15T00:00:00+00:00",
            "updated": "2026-07-15T00:00:00+00:00",
            "group": "__world__", "links": {"incontext": "https://hyp.is/x"},
        }
        base.update(over)
        return base

    def test_dry_run_uses_model_result(self, monkeypatch):
        monkeypatch.setattr(poll, "call_sonnet", lambda p: {
            "node": "artifacts/personal-site", "role": "does a thing",
            "actions": [{"type": "revision", "instructions": "do it"}],
        })
        rec = poll.process(self._ann(), dry_run=True)
        assert rec["node"] == "artifacts/personal-site"
        assert rec["role"] == "does a thing"
        assert rec["classified_by"] == poll.MODEL

    def test_falls_back_to_rules_on_model_error(self, monkeypatch):
        def boom(_):
            raise RuntimeError("api down")
        monkeypatch.setattr(poll, "call_sonnet", boom)
        rec = poll.process(self._ann(), dry_run=True)
        assert rec["classified_by"] == "rules-fallback"
        assert rec["node"] == "artifacts/personal-site"  # rule-based baseline

    def test_freshly_created_annotation_does_not_crash(self, monkeypatch):
        # document=[] mid-creation shape + model error → must still return a record
        def boom(_):
            raise RuntimeError("api down")
        monkeypatch.setattr(poll, "call_sonnet", boom)
        rec = poll.process(self._ann(document=[], target=[], tags=[]),
                          dry_run=True)
        assert rec["classified_by"] == "rules-fallback"
        assert rec["title"] == ""


class TestLoadConfig:
    def test_returns_dict(self):
        # config.json or config.example.json is present in-repo
        assert isinstance(poll.load_config(), dict)
