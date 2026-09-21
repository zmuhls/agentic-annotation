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
        with pytest.raises(RuntimeError, match="claude exited 1: boom"):
            poll.call_sonnet("prompt", attempts=1)

    def test_reports_the_stdout_envelope_when_stderr_is_empty(self, monkeypatch):
        # the CLI's real failure shape: exit 1, empty stderr, reason in stdout
        envelope = json.dumps([{"type": "result", "is_error": True,
                                "result": "Overloaded"}])
        monkeypatch.setattr(poll.subprocess, "run",
                            lambda *a, **k: FakeProc(returncode=1, stdout=envelope))
        monkeypatch.setattr(poll.time, "sleep", lambda *a: None)
        with pytest.raises(RuntimeError, match="Overloaded"):
            poll.call_sonnet("prompt", attempts=1)

    def test_auth_failure_fails_fast_without_retrying(self, monkeypatch):
        envelope = json.dumps({"type": "result", "is_error": True,
                               "result": "Failed to authenticate: OAuth session expired"})
        calls = []

        def run(*a, **k):
            calls.append(1)
            return FakeProc(returncode=1, stdout=envelope)

        monkeypatch.setattr(poll.subprocess, "run", run)
        monkeypatch.setattr(poll.time, "sleep",
                            lambda *a: pytest.fail("must not sleep on an auth failure"))
        with pytest.raises(RuntimeError, match="not authenticated"):
            poll.call_sonnet("prompt", attempts=3)
        assert len(calls) == 1

    def test_error_text_without_any_output(self, monkeypatch):
        monkeypatch.setattr(poll.subprocess, "run",
                            lambda *a, **k: FakeProc(returncode=1))
        monkeypatch.setattr(poll.time, "sleep", lambda *a: None)
        with pytest.raises(RuntimeError, match="no output"):
            poll.call_sonnet("prompt", attempts=1)

    def test_raises_when_no_json(self, monkeypatch):
        monkeypatch.setattr(poll.subprocess, "run",
                            lambda *a, **k: FakeProc(stdout=_wrap("no json here")))
        with pytest.raises(ValueError, match="no JSON"):
            poll.call_sonnet("prompt")


@pytest.mark.usefixtures("routing")
class TestProcess:
    def _ann(self, **over):
        base = {
            "id": "test1", "uri": "https://mysite.example/x",
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


class TestSearchRetries:
    """The network is never mocked away by accident here: every test replaces
    `urlopen`, so no test can reach api.hypothes.is."""

    def _urlopen(self, monkeypatch, outcomes):
        """Serve `outcomes` in order; an Exception instance is raised."""
        calls = []

        def fake(req, timeout=None):
            calls.append(req)
            outcome = outcomes[len(calls) - 1]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(poll.urllib.request, "urlopen", fake)
        monkeypatch.setattr(poll.time, "sleep", lambda *a: None)  # no real backoff
        return calls

    class _Resp:
        def __init__(self, payload):
            self._payload = json.dumps(payload).encode()

        def read(self):
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def test_retries_transient_oserror_then_succeeds(self, monkeypatch):
        calls = self._urlopen(monkeypatch, [
            ConnectionResetError(54, "Connection reset by peer"),
            self._Resp({"rows": [{"id": "a"}]}),
        ])
        assert poll.search({})["rows"] == [{"id": "a"}]
        assert len(calls) == 2

    def test_raises_after_exhausting_attempts(self, monkeypatch):
        err = poll.urllib.error.URLError("no route to host")
        calls = self._urlopen(monkeypatch, [err, err, err])
        with pytest.raises(OSError):
            poll.search({}, attempts=3)
        assert len(calls) == 3

    def test_retries_rate_limit_but_not_unauthorized(self, monkeypatch):
        http = poll.urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        calls = self._urlopen(monkeypatch, [http, self._Resp({"rows": []})])
        assert poll.search({})["rows"] == []
        assert len(calls) == 2

        unauth = poll.urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        calls = self._urlopen(monkeypatch, [unauth, self._Resp({"rows": []})])
        with pytest.raises(poll.urllib.error.HTTPError):
            poll.search({})
        assert len(calls) == 1  # no retry on a real fault


class TestNetworkFailureNotice:
    def test_logs_once_per_outage_and_clears_on_recovery(self):
        msg = "hypothesis api unreachable (dns); retrying next run"
        poll.note_network_failure(msg)
        poll.note_network_failure(msg)  # same outage — must not log again
        assert poll.LOG_FILE.read_text().count("unreachable") == 1

        poll.note_network_failure("hypothesis api returned 503 x; retrying next run")
        assert "503" in poll.LOG_FILE.read_text()

        poll.clear_network_failure()
        assert not poll.NETFAIL_FILE.exists()
        assert "reachable again" in poll.LOG_FILE.read_text()

    def test_clear_is_a_noop_when_no_outage(self):
        poll.clear_network_failure()
        assert not poll.LOG_FILE.exists()


class TestLoadConfig:
    def test_returns_dict(self):
        # config.json or config.example.json is present in-repo
        assert isinstance(poll.load_config(), dict)


class TestTrimLog:
    def test_leaves_a_small_log_alone(self, tmp_path):
        path = tmp_path / "small.log"
        path.write_text("line one\nline two\n")
        assert poll.trim_log(path, max_bytes=1000, keep_bytes=100) is False
        assert path.read_text() == "line one\nline two\n"

    def test_keeps_the_tail_and_drops_the_partial_line(self, tmp_path):
        path = tmp_path / "big.log"
        path.write_text("".join(f"entry {i:05d}\n" for i in range(2000)))
        assert poll.trim_log(path, max_bytes=1000, keep_bytes=500) is True

        text = path.read_text()
        assert path.stat().st_size < 1000
        assert "entry 01999" in text            # newest entries survive
        assert "entry 00000" not in text        # oldest are gone
        assert "trimmed" in text.splitlines()[0]
        body = text.split("\n", 1)[1]
        assert all(line.startswith("entry ") for line in body.splitlines())

    def test_rewrites_the_same_inode(self, tmp_path):
        """The scheduler holds an append fd on launchd.log; renaming would orphan it."""
        path = tmp_path / "inode.log"
        path.write_text("".join(f"entry {i:05d}\n" for i in range(2000)))
        before = path.stat().st_ino
        poll.trim_log(path, max_bytes=1000, keep_bytes=500)
        assert path.stat().st_ino == before

    def test_missing_log_is_not_an_error(self, tmp_path):
        assert poll.trim_log(tmp_path / "nope.log") is False


class TestHeartbeat:
    """Every completed poll leaves a timestamp behind.

    Without one, a watcher that never starts (a scheduler unit naming a deleted
    interpreter) is indistinguishable from a quiet week: both write nothing.
    """

    def _health(self):
        return json.loads(poll.HEALTH_FILE.read_text())

    def test_clean_run_with_nothing_new_still_stamps(self, monkeypatch):
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: [])
        poll.main()
        health = self._health()
        assert health["status"] == "ok"
        assert health["processed"] == 0
        assert health["last_run"].startswith("20")

    def test_records_an_unreachable_api(self, monkeypatch):
        def boom(cursor):
            raise OSError("dns went away")
        monkeypatch.setattr(poll, "fetch_new", boom)
        poll.main()
        health = self._health()
        assert health["status"] == "api-unreachable"
        assert "dns went away" in health["detail"]

    def test_records_an_api_error_status(self, monkeypatch):
        def boom(cursor):
            raise poll.urllib.error.HTTPError(
                "http://x", 401, "Unauthorized", {}, None)
        monkeypatch.setattr(poll, "fetch_new", boom)
        poll.main()
        assert self._health()["status"] == "api-error"

    def test_counts_annotations_that_took_the_rules_fallback(self, monkeypatch):
        rows = [{"id": "a1", "updated": "2026-09-20T00:00:00+00:00"},
                {"id": "a2", "updated": "2026-09-20T00:01:00+00:00"}]
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: rows)
        monkeypatch.setattr(poll, "process", lambda ann, dry_run=False: {
            "id": ann["id"],
            "classified_by": "rules-fallback" if ann["id"] == "a2" else poll.MODEL,
        })
        poll.main()
        health = self._health()
        assert health["processed"] == 2
        assert health["fallbacks"] == 1

    def test_dry_run_leaves_no_heartbeat(self, monkeypatch):
        monkeypatch.setattr(poll.sys, "argv", ["poll.py", "--dry-run"])
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: [])
        poll.main()
        assert not poll.HEALTH_FILE.exists()

    def test_a_poll_that_could_not_take_the_lock_does_not_stamp(self, monkeypatch):
        monkeypatch.setattr(poll, "fetch_new",
                            lambda cursor: pytest.fail("must not poll"))
        held = poll.LOCK_FILE.open("w")
        poll.fcntl.flock(held, poll.fcntl.LOCK_EX | poll.fcntl.LOCK_NB)
        try:
            poll.main()
        finally:
            held.close()
        assert not poll.HEALTH_FILE.exists()
