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


def sample_annotation(**over):
    """One annotation in the shape /api/search returns, for process() tests."""
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


@pytest.mark.usefixtures("routing")
class TestProcess:
    _ann = staticmethod(sample_annotation)

    def test_dry_run_uses_model_result(self, monkeypatch):
        monkeypatch.setattr(poll, "call_sonnet", lambda p, **kw: {
            "node": "artifacts/personal-site", "role": "does a thing",
            "actions": [{"type": "revision", "instructions": "do it"}],
        })
        rec = poll.process(self._ann(), dry_run=True)
        assert rec["node"] == "artifacts/personal-site"
        assert rec["role"] == "does a thing"
        assert rec["classified_by"] == poll.MODEL

    def test_falls_back_to_rules_on_model_error(self, monkeypatch):
        def boom(_, **kw):
            raise RuntimeError("api down")
        monkeypatch.setattr(poll, "call_sonnet", boom)
        rec = poll.process(self._ann(), dry_run=True)
        assert rec["classified_by"] == "rules-fallback"
        assert rec["node"] == "artifacts/personal-site"  # rule-based baseline

    def test_freshly_created_annotation_does_not_crash(self, monkeypatch):
        # document=[] mid-creation shape + model error → must still return a record
        def boom(_, **kw):
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


class TestInterruptedAndFailedRuns:
    """A run that is killed or crashes has to leave evidence.

    Both failures previously looked identical to a quiet week: the scheduler
    log kept a stale block-buffered tail and data/health.json still read "ok"
    from the previous run.
    """

    def _health(self):
        return json.loads(poll.HEALTH_FILE.read_text())

    def test_sigterm_stamps_an_interrupted_heartbeat(self):
        handler = poll._interrupt_handler(dry_run=False)
        with pytest.raises(SystemExit) as exc:
            handler(poll.signal.SIGTERM, None)
        assert exc.value.code == 128 + int(poll.signal.SIGTERM)
        health = self._health()
        assert health["status"] == "interrupted"
        assert "SIGTERM" in health["detail"]

    def test_sigterm_says_the_next_run_resumes(self):
        with pytest.raises(SystemExit):
            poll._interrupt_handler(dry_run=False)(poll.signal.SIGINT, None)
        assert "picks up from the same cursor" in poll.LOG_FILE.read_text()

    def test_a_dry_run_interrupt_leaves_no_heartbeat(self):
        with pytest.raises(SystemExit):
            poll._interrupt_handler(dry_run=True)(poll.signal.SIGTERM, None)
        assert not poll.HEALTH_FILE.exists()

    def test_an_unhandled_crash_is_recorded_not_swallowed(self, monkeypatch):
        def boom(dry_run):
            raise RuntimeError("map.jsonl is truncated")
        monkeypatch.setattr(poll, "poll_once", boom)
        with pytest.raises(SystemExit) as exc:
            poll.main()
        assert exc.value.code == 1
        health = self._health()
        assert health["status"] == "error"
        assert "map.jsonl is truncated" in health["detail"]

    def test_a_crash_logs_the_traceback(self, monkeypatch):
        monkeypatch.setattr(poll, "poll_once",
                            lambda dry_run: 1 // 0)
        with pytest.raises(SystemExit):
            poll.main()
        text = poll.LOG_FILE.read_text()
        assert "poll failed: ZeroDivisionError" in text
        assert "Traceback" in text

    def test_a_crashing_dry_run_leaves_no_heartbeat(self, monkeypatch):
        monkeypatch.setattr(poll.sys, "argv", ["poll.py", "--dry-run"])
        monkeypatch.setattr(poll, "poll_once",
                            lambda dry_run: 1 // 0)
        with pytest.raises(SystemExit):
            poll.main()
        assert not poll.HEALTH_FILE.exists()

    def test_a_real_run_registers_both_handlers(self, monkeypatch):
        installed = []
        monkeypatch.setattr(poll.signal, "signal",
                            lambda sig, handler: installed.append(sig))
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: [])
        poll.main()
        assert set(installed) == {poll.signal.SIGTERM, poll.signal.SIGINT}


@pytest.mark.usefixtures("routing")
class TestCostVisibility:
    """Each classification is a real ~$0.10 call; the run should say so.

    The CLI reports `total_cost_usd` in its own result envelope, so nothing
    here estimates or prices tokens — it only carries the number the CLI
    already handed back.
    """

    def _health(self):
        return json.loads(poll.HEALTH_FILE.read_text())

    def test_meta_is_filled_from_the_dict_envelope(self, monkeypatch):
        envelope = json.dumps({"type": "result", "result": '{"node": "inbox"}',
                               "total_cost_usd": 0.0937})
        monkeypatch.setattr(poll.subprocess, "run",
                            lambda *a, **k: FakeProc(stdout=envelope))
        meta = {}
        assert poll.call_sonnet("prompt", meta=meta)["node"] == "inbox"
        assert meta["cost_usd"] == 0.0937

    def test_meta_is_filled_from_the_list_envelope(self, monkeypatch):
        envelope = json.dumps([
            {"type": "system"},
            {"type": "result", "result": '{"node": "inbox"}', "total_cost_usd": 0.12},
        ])
        monkeypatch.setattr(poll.subprocess, "run",
                            lambda *a, **k: FakeProc(stdout=envelope))
        meta = {}
        poll.call_sonnet("prompt", meta=meta)
        assert meta["cost_usd"] == 0.12

    def test_a_cli_that_reports_no_cost_is_not_an_error(self, monkeypatch):
        monkeypatch.setattr(poll.subprocess, "run",
                            lambda *a, **k: FakeProc(stdout=_wrap('{"node": "inbox"}')))
        meta = {}
        poll.call_sonnet("prompt", meta=meta)
        assert meta["cost_usd"] is None

    def test_the_cost_lands_on_the_record(self, monkeypatch):
        def priced(prompt, meta=None, **kw):
            meta["cost_usd"] = 0.0821
            return {"node": "inbox", "role": "r", "actions": []}
        monkeypatch.setattr(poll, "call_sonnet", priced)
        rec = poll.process(sample_annotation(), dry_run=True)
        assert rec["cost_usd"] == 0.0821

    def test_a_rules_fallback_carries_no_cost(self, monkeypatch):
        def boom(prompt, meta=None, **kw):
            raise RuntimeError("api down")
        monkeypatch.setattr(poll, "call_sonnet", boom)
        rec = poll.process(sample_annotation(), dry_run=True)
        assert "cost_usd" not in rec

    def test_health_totals_the_run_and_the_lifetime(self):
        poll.record_health("ok", processed=1, cost_usd=0.10)
        poll.record_health("ok", processed=2, cost_usd=0.05)
        health = self._health()
        assert health["cost_usd"] == 0.05
        assert health["cost_usd_total"] == 0.15

    def test_a_corrupt_stamp_restarts_the_tally_instead_of_failing(self):
        poll.HEALTH_FILE.write_text("{not json")
        poll.record_health("ok", cost_usd=0.02)
        assert self._health()["cost_usd_total"] == 0.02


def _rows(*stamps):
    return [{"id": f"a{i}", "updated": s} for i, s in enumerate(stamps)]


class TestBatchCap:
    """A backlog is paced across runs instead of billed in one sitting."""

    def test_under_the_cap_is_untouched(self):
        rows = _rows("t1", "t2")
        assert poll.cap_batch(rows, 5) == (rows, 0)

    def test_zero_disables_the_cap(self):
        rows = _rows(*[f"t{i}" for i in range(40)])
        assert poll.cap_batch(rows, 0) == (rows, 0)

    def test_cuts_at_the_limit_and_counts_the_rest(self):
        rows = _rows("t1", "t2", "t3", "t4")
        kept, deferred = poll.cap_batch(rows, 2)
        assert [r["id"] for r in kept] == ["a0", "a1"]
        assert deferred == 2

    def test_never_splits_a_shared_timestamp(self):
        # the cursor would land on t2 and the next search starts after it
        rows = _rows("t1", "t2", "t2", "t3")
        kept, deferred = poll.cap_batch(rows, 2)
        assert [r["id"] for r in kept] == ["a0", "a1", "a2"]
        assert deferred == 1

    def test_the_cursor_stops_at_the_last_processed_row(self, monkeypatch):
        rows = _rows("2026-09-20T00:00:00+00:00", "2026-09-20T00:01:00+00:00",
                     "2026-09-20T00:02:00+00:00")
        monkeypatch.setattr(poll, "MAX_PER_RUN", 2)
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: rows)
        monkeypatch.setattr(poll, "process", lambda ann, dry_run=False: {
            "id": ann["id"], "classified_by": poll.MODEL})
        poll.main()
        cursor = json.loads(poll.CURSOR_FILE.read_text())["search_after"]
        assert cursor == "2026-09-20T00:01:00+00:00"
        assert set(json.loads(poll.SEEN_FILE.read_text())) == {"a0", "a1"}
        health = json.loads(poll.HEALTH_FILE.read_text())
        assert health["processed"] == 2
        assert health["detail"] == "1 deferred to next run"
        assert "1 deferred to the next run" in poll.LOG_FILE.read_text()


class TestDailyCeiling:
    """A dollar ceiling per UTC day, on top of the per-run count cap."""

    ROWS = ["2026-09-20T00:00:00+00:00", "2026-09-20T00:01:00+00:00",
            "2026-09-20T00:02:00+00:00"]

    def _run(self, monkeypatch, stamps, ceiling, price=0.10):
        rows = _rows(*stamps)
        monkeypatch.setattr(poll, "MAX_PER_RUN", 0)
        monkeypatch.setattr(poll, "MAX_DAILY_USD", ceiling)
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: rows)
        calls = []

        def priced(ann, dry_run=False):
            calls.append(ann["id"])
            return {"id": ann["id"], "classified_by": poll.MODEL, "cost_usd": price}
        monkeypatch.setattr(poll, "process", priced)
        poll.main()
        return calls, json.loads(poll.HEALTH_FILE.read_text())

    def test_today_starts_at_zero_and_accumulates(self):
        assert poll.spent_today() == 0.0
        poll.record_health("ok", cost_usd=0.10)
        poll.record_health("ok", cost_usd=0.05)
        assert poll.spent_today() == 0.15

    def test_an_earlier_day_does_not_count(self):
        poll.HEALTH_FILE.write_text(json.dumps(
            {"cost_day": "2000-01-01", "cost_usd_today": 9.0, "cost_usd_total": 9.0}))
        assert poll.spent_today() == 0.0
        poll.record_health("ok", cost_usd=0.02)
        health = json.loads(poll.HEALTH_FILE.read_text())
        assert health["cost_usd_today"] == 0.02
        assert health["cost_usd_total"] == 9.02

    def test_zero_disables_the_ceiling(self, monkeypatch):
        calls, health = self._run(monkeypatch, self.ROWS, 0)
        assert len(calls) == 3
        assert health["status"] == "ok"

    def test_stops_once_the_day_is_spent_and_holds_the_cursor(self, monkeypatch):
        calls, health = self._run(monkeypatch, self.ROWS, 0.15)
        assert calls == ["a0", "a1"]  # a1 starts under the ceiling, a2 would not
        assert health["status"] == "budget"
        assert health["processed"] == 2
        assert "1 waiting" in health["detail"]
        cursor = json.loads(poll.CURSOR_FILE.read_text())["search_after"]
        assert cursor == self.ROWS[1]
        assert "daily spend ceiling reached" in poll.LOG_FILE.read_text()

    def test_never_splits_a_shared_timestamp(self, monkeypatch):
        # a0 spends the day, but a1 shares its timestamp and the cursor lands on it
        stamps = [self.ROWS[0], self.ROWS[0], self.ROWS[1]]
        calls, _ = self._run(monkeypatch, stamps, 0.10)
        assert calls == ["a0", "a1"]

    def test_a_spent_day_classifies_nothing_and_logs_nothing(self, monkeypatch):
        poll.record_health("ok", cost_usd=1.00)
        calls, health = self._run(monkeypatch, self.ROWS, 1.00)
        assert calls == []
        assert health["status"] == "budget"
        assert "3 waiting" in health["detail"]
        assert not poll.CURSOR_FILE.exists()
        assert not poll.LOG_FILE.exists() or "processing" not in poll.LOG_FILE.read_text()


@pytest.mark.usefixtures("routing")
class TestClassifyPrompt:
    """The prompt is read on every call, so it may only speak in the reader's own nodes."""

    TAIL = "## Action vocabulary\n\n- `architecture/map.jsonl` — not a node\n"

    def _prompt(self, monkeypatch, tmp_path, nodes):
        ia = tmp_path / "ia.md"
        ia.write_text(f"# IA\n\n## Nodes\n\n{nodes}\n{self.TAIL}")
        monkeypatch.setattr(poll, "IA_FILE", ia)
        return poll.classify_prompt(sample_annotation())

    def test_new_node_example_is_drawn_from_the_live_taxonomy(self, monkeypatch, tmp_path):
        prompt = self._prompt(monkeypatch, tmp_path,
                              "### garden — plants\n\n- `garden/roses` — roses\n")
        assert '(e.g. "garden/roses/<child>")' in prompt
        assert "platform-studies" not in prompt

    def test_a_taxonomy_without_children_gets_a_neutral_example(self, monkeypatch, tmp_path):
        prompt = self._prompt(monkeypatch, tmp_path, "### garden — plants\n")
        assert '(e.g. "<existing-node>/<child>")' in prompt
        assert "architecture/map.jsonl/<child>" not in prompt  # the tail is not a node
