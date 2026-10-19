"""Tests for the classify/parse path in poll.py.

The `claude` subprocess is always mocked — these tests never shell out to the
CLI and never spend real API money.
"""

import io
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
        monkeypatch.setattr(
            poll.subprocess, "run", lambda *a, **k: FakeProc(stdout=_wrap(json.dumps(payload)))
        )
        assert poll.call_sonnet("prompt") == payload

    def test_strips_prose_around_json(self, monkeypatch):
        text = 'Sure!\n{"node": "inbox", "actions": []}\nHope that helps.'
        monkeypatch.setattr(poll.subprocess, "run", lambda *a, **k: FakeProc(stdout=_wrap(text)))
        assert poll.call_sonnet("prompt")["node"] == "inbox"

    def test_handles_list_envelope(self, monkeypatch):
        # some CLI versions emit a list of message objects
        envelope = json.dumps(
            [
                {"type": "system"},
                {"type": "result", "result": '{"node": "reading/general", "actions": []}'},
            ]
        )
        monkeypatch.setattr(poll.subprocess, "run", lambda *a, **k: FakeProc(stdout=envelope))
        assert poll.call_sonnet("prompt")["node"] == "reading/general"

    def test_raises_on_nonzero_exit(self, monkeypatch):
        monkeypatch.setattr(
            poll.subprocess, "run", lambda *a, **k: FakeProc(returncode=1, stderr="boom")
        )
        monkeypatch.setattr(poll.time, "sleep", lambda *a: None)  # no real wait
        with pytest.raises(RuntimeError, match="claude exited 1: boom"):
            poll.call_sonnet("prompt", attempts=1)

    def test_reports_the_stdout_envelope_when_stderr_is_empty(self, monkeypatch):
        # the CLI's real failure shape: exit 1, empty stderr, reason in stdout
        envelope = json.dumps([{"type": "result", "is_error": True, "result": "Overloaded"}])
        monkeypatch.setattr(
            poll.subprocess, "run", lambda *a, **k: FakeProc(returncode=1, stdout=envelope)
        )
        monkeypatch.setattr(poll.time, "sleep", lambda *a: None)
        with pytest.raises(RuntimeError, match="Overloaded"):
            poll.call_sonnet("prompt", attempts=1)

    def test_auth_failure_fails_fast_without_retrying(self, monkeypatch):
        envelope = json.dumps(
            {
                "type": "result",
                "is_error": True,
                "result": "Failed to authenticate: OAuth session expired",
            }
        )
        calls = []

        def run(*a, **k):
            calls.append(1)
            return FakeProc(returncode=1, stdout=envelope)

        monkeypatch.setattr(poll.subprocess, "run", run)
        monkeypatch.setattr(
            poll.time, "sleep", lambda *a: pytest.fail("must not sleep on an auth failure")
        )
        with pytest.raises(poll.ClaudeAuthError, match="not authenticated"):
            poll.call_sonnet("prompt", attempts=3)
        assert len(calls) == 1

    def test_a_cli_with_no_login_at_all_is_an_auth_failure(self, monkeypatch):
        # the shape a launchd run logged on 2026-10-16
        envelope = json.dumps(
            {"type": "result", "is_error": True, "result": "Not logged in · Please run /login"}
        )
        monkeypatch.setattr(
            poll.subprocess, "run", lambda *a, **k: FakeProc(returncode=1, stdout=envelope)
        )
        with pytest.raises(poll.ClaudeAuthError, match="Not logged in"):
            poll.call_sonnet("prompt")

    def test_a_missing_cli_fails_fast_and_names_the_fixes(self, tmp_path, monkeypatch):
        # a real subprocess.run on a path with nothing there: no claude is ever run
        absent = tmp_path / "claude"
        monkeypatch.setitem(poll.CONFIG, "claude_bin", str(absent))
        monkeypatch.setattr(
            poll.time, "sleep", lambda *a: pytest.fail("must not sleep on a missing cli")
        )
        with pytest.raises(poll.ClaudeMissingError) as err:
            poll.call_sonnet("prompt", attempts=3)
        assert str(absent) in str(err.value)
        assert "claude_bin" in str(err.value)
        assert '"model": "rules"' in str(err.value)

    def test_a_missing_cli_and_a_dead_login_hold_the_queue_alike(self):
        assert issubclass(poll.ClaudeMissingError, poll.ClaudeUnavailableError)
        assert issubclass(poll.ClaudeAuthError, poll.ClaudeUnavailableError)

    def test_error_text_without_any_output(self, monkeypatch):
        monkeypatch.setattr(poll.subprocess, "run", lambda *a, **k: FakeProc(returncode=1))
        monkeypatch.setattr(poll.time, "sleep", lambda *a: None)
        with pytest.raises(RuntimeError, match="no output"):
            poll.call_sonnet("prompt", attempts=1)

    def test_raises_when_no_json(self, monkeypatch):
        monkeypatch.setattr(
            poll.subprocess, "run", lambda *a, **k: FakeProc(stdout=_wrap("no json here"))
        )
        with pytest.raises(ValueError, match="no JSON"):
            poll.call_sonnet("prompt")


def sample_annotation(**over):
    """One annotation in the shape /api/search returns, for process() tests."""
    base = {
        "id": "test1",
        "uri": "https://mysite.example/x",
        "document": {"title": ["T"]},
        "tags": ["revision"],
        "target": [{"selector": [{"type": "TextQuoteSelector", "exact": "quoted bit"}]}],
        "created": "2026-07-15T00:00:00+00:00",
        "updated": "2026-07-15T00:00:00+00:00",
        "group": "__world__",
        "links": {"incontext": "https://hyp.is/x"},
    }
    base.update(over)
    return base


@pytest.mark.usefixtures("routing")
class TestProcess:
    _ann = staticmethod(sample_annotation)

    def test_dry_run_uses_model_result(self, monkeypatch):
        monkeypatch.setattr(
            poll,
            "call_sonnet",
            lambda p, **kw: {
                "node": "artifacts/personal-site",
                "role": "does a thing",
                "actions": [{"type": "revision", "instructions": "do it"}],
            },
        )
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
        rec = poll.process(self._ann(document=[], target=[], tags=[]), dry_run=True)
        assert rec["classified_by"] == "rules-fallback"
        assert rec["title"] == ""

    def test_a_dead_login_is_not_filed_as_a_rules_fallback(self, monkeypatch):
        # Every annotation fails the same way until someone signs in. Filing them
        # under the rules marked them seen, so they never got a model pass.
        def signed_out(_, **kw):
            raise poll.ClaudeAuthError("claude cli is not authenticated (Not logged in)")

        monkeypatch.setattr(poll, "call_sonnet", signed_out)
        with pytest.raises(poll.ClaudeAuthError):
            poll.process(self._ann())
        assert not poll.MAP_FILE.exists()
        assert not poll.ACTIONS_DIR.exists()

    def test_a_missing_cli_is_not_filed_as_a_rules_fallback(self, tmp_path, monkeypatch):
        # a moved or uninstalled binary fails every annotation alike, as a dead login does
        monkeypatch.setitem(poll.CONFIG, "claude_bin", str(tmp_path / "absent"))
        with pytest.raises(poll.ClaudeMissingError):
            poll.process(self._ann())
        assert not poll.MAP_FILE.exists()
        assert not poll.ACTIONS_DIR.exists()

    def test_rules_mode_places_by_the_rules_without_the_cli(self, monkeypatch):
        monkeypatch.setattr(poll, "MODEL", "rules")
        monkeypatch.setattr(
            poll, "call_sonnet", lambda *a, **k: pytest.fail("rules mode must not call the cli")
        )
        rec = poll.process(self._ann())
        assert rec["classified_by"] == "rules"  # not "rules-fallback": nothing failed
        assert rec["node"] == "artifacts/personal-site"
        assert len(list(poll.ACTIONS_DIR.iterdir())) == 1  # the revision tag still files

    def test_the_first_classification_after_a_lapse_says_so(self, monkeypatch):
        poll.AUTHFAIL_FILE.write_text("claude cli is not authenticated (Not logged in)")
        monkeypatch.setattr(poll, "call_sonnet", lambda p, **kw: {"node": "inbox", "actions": []})
        poll.process(self._ann(tags=[]))
        assert not poll.AUTHFAIL_FILE.exists()
        # the same marker covers a reinstalled binary, so the line cannot say "signed in"
        assert "claude cli answering again" in poll.LOG_FILE.read_text()

    def test_a_dry_run_leaves_the_lapse_marker_alone(self, monkeypatch):
        poll.AUTHFAIL_FILE.write_text("claude cli is not authenticated (Not logged in)")
        monkeypatch.setattr(poll, "call_sonnet", lambda p, **kw: {"node": "inbox", "actions": []})
        poll.process(self._ann(tags=[]), dry_run=True)
        assert poll.AUTHFAIL_FILE.exists()


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
        calls = self._urlopen(
            monkeypatch,
            [
                ConnectionResetError(54, "Connection reset by peer"),
                self._Resp({"rows": [{"id": "a"}]}),
            ],
        )
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


# The body /api/search sent back for search_after=garbage (probed live), line
# breaks and leading ": " included.
REJECTED_BODY = json.dumps(
    {
        "status": "failure",
        "reason": ": search_after must be a parsable date in the form\n"
        "                    yyyy-MM-dd'T'HH:mm:ss.SSX\n"
        "                    or time in miliseconds since the epoch.",
    }
).encode()


def _http_error(code, msg, body=None):
    fp = io.BytesIO(body) if body is not None else None
    return poll.urllib.error.HTTPError("u", code, msg, {}, fp)


class TestApiReason:
    def test_reads_the_reason_the_api_gives(self):
        reason = poll.api_reason(_http_error(400, "Bad Request", REJECTED_BODY))
        assert reason == (
            "400 Bad Request: search_after must be a parsable date in the "
            "form yyyy-MM-dd'T'HH:mm:ss.SSX or time in miliseconds since "
            "the epoch."
        )

    def test_a_body_that_is_not_json_falls_back_to_the_status(self):
        assert poll.api_reason(_http_error(502, "Bad Gateway", b"<html>")) == "502 Bad Gateway"

    def test_no_body_falls_back_to_the_status(self):
        assert poll.api_reason(_http_error(401, "Unauthorized")) == "401 Unauthorized"


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
        assert "entry 01999" in text  # newest entries survive
        assert "entry 00000" not in text  # oldest are gone
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
            raise poll.urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, None)

        monkeypatch.setattr(poll, "fetch_new", boom)
        poll.main()
        assert self._health()["status"] == "api-error"

    def test_a_rejected_request_records_the_apis_own_reason(self, monkeypatch):
        # a bare "400 Bad Request" sends an adopter guessing; the body names the field
        def rejected(cursor):
            raise _http_error(400, "Bad Request", REJECTED_BODY)

        monkeypatch.setattr(poll, "fetch_new", rejected)
        poll.main()
        assert "search_after must be a parsable date" in self._health()["detail"]
        assert "search_after must be a parsable date" in poll.LOG_FILE.read_text()

    def test_a_rejected_request_points_at_config_not_a_retry(self, monkeypatch):
        # a 4xx fails every run the same way until config.json changes;
        # "retrying next run" sent adopters waiting for a self-heal
        def unauthorized(cursor):
            raise _http_error(401, "Unauthorized")

        monkeypatch.setattr(poll, "fetch_new", unauthorized)
        poll.main()
        log = poll.LOG_FILE.read_text()
        assert "401 Unauthorized" in log
        assert "retrying next run" not in log
        assert "config.json" in log

    def test_a_server_error_that_outlasts_the_retries_still_says_retrying(self, monkeypatch):
        def unavailable(cursor):
            raise _http_error(503, "Service Unavailable")

        monkeypatch.setattr(poll, "fetch_new", unavailable)
        poll.main()
        log = poll.LOG_FILE.read_text()
        assert "503 Service Unavailable" in log
        assert "retrying next run" in log
        assert self._health()["status"] == "api-error"

    def test_counts_annotations_that_took_the_rules_fallback(self, monkeypatch):
        rows = [
            {"id": "a1", "updated": "2026-09-20T00:00:00+00:00"},
            {"id": "a2", "updated": "2026-09-20T00:01:00+00:00"},
        ]
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: rows)
        monkeypatch.setattr(
            poll,
            "process",
            lambda ann, dry_run=False: {
                "id": ann["id"],
                "classified_by": "rules-fallback" if ann["id"] == "a2" else poll.MODEL,
            },
        )
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
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: pytest.fail("must not poll"))
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
        monkeypatch.setattr(poll, "poll_once", lambda dry_run: 1 // 0)
        with pytest.raises(SystemExit):
            poll.main()
        text = poll.LOG_FILE.read_text()
        assert "poll failed: ZeroDivisionError" in text
        assert "Traceback" in text

    def test_a_crashing_dry_run_leaves_no_heartbeat(self, monkeypatch):
        monkeypatch.setattr(poll.sys, "argv", ["poll.py", "--dry-run"])
        monkeypatch.setattr(poll, "poll_once", lambda dry_run: 1 // 0)
        with pytest.raises(SystemExit):
            poll.main()
        assert not poll.HEALTH_FILE.exists()

    def test_a_real_run_registers_both_handlers(self, monkeypatch):
        installed = []
        monkeypatch.setattr(poll.signal, "signal", lambda sig, handler: installed.append(sig))
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
        envelope = json.dumps(
            {"type": "result", "result": '{"node": "inbox"}', "total_cost_usd": 0.0937}
        )
        monkeypatch.setattr(poll.subprocess, "run", lambda *a, **k: FakeProc(stdout=envelope))
        meta = {}
        assert poll.call_sonnet("prompt", meta=meta)["node"] == "inbox"
        assert meta["cost_usd"] == 0.0937

    def test_meta_is_filled_from_the_list_envelope(self, monkeypatch):
        envelope = json.dumps(
            [
                {"type": "system"},
                {"type": "result", "result": '{"node": "inbox"}', "total_cost_usd": 0.12},
            ]
        )
        monkeypatch.setattr(poll.subprocess, "run", lambda *a, **k: FakeProc(stdout=envelope))
        meta = {}
        poll.call_sonnet("prompt", meta=meta)
        assert meta["cost_usd"] == 0.12

    def test_a_cli_that_reports_no_cost_is_not_an_error(self, monkeypatch):
        monkeypatch.setattr(
            poll.subprocess, "run", lambda *a, **k: FakeProc(stdout=_wrap('{"node": "inbox"}'))
        )
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

    def test_a_shared_timestamp_is_cut_like_any_other(self):
        # safe because the next fetch re-reads the cursor's millisecond
        rows = _rows("t1", "t2", "t2", "t3")
        kept, deferred = poll.cap_batch(rows, 2)
        assert [r["id"] for r in kept] == ["a0", "a1"]
        assert deferred == 2

    def test_the_cursor_stops_at_the_last_processed_row(self, monkeypatch):
        rows = _rows(
            "2026-09-20T00:00:00+00:00", "2026-09-20T00:01:00+00:00", "2026-09-20T00:02:00+00:00"
        )
        monkeypatch.setattr(poll, "MAX_PER_RUN", 2)
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: rows)
        monkeypatch.setattr(
            poll,
            "process",
            lambda ann, dry_run=False: {"id": ann["id"], "classified_by": poll.MODEL},
        )
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

    ROWS = ["2026-09-20T00:00:00+00:00", "2026-09-20T00:01:00+00:00", "2026-09-20T00:02:00+00:00"]

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
        poll.HEALTH_FILE.write_text(
            json.dumps({"cost_day": "2000-01-01", "cost_usd_today": 9.0, "cost_usd_total": 9.0})
        )
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

    def test_a_shared_timestamp_does_not_overshoot_the_ceiling(self, monkeypatch):
        # a1 waits for the next run, which re-reads the cursor's millisecond
        stamps = [self.ROWS[0], self.ROWS[0], self.ROWS[1]]
        calls, _ = self._run(monkeypatch, stamps, 0.10)
        assert calls == ["a0"]

    def test_a_spent_day_classifies_nothing_and_logs_nothing(self, monkeypatch):
        poll.record_health("ok", cost_usd=1.00)
        calls, health = self._run(monkeypatch, self.ROWS, 1.00)
        assert calls == []
        assert health["status"] == "budget"
        assert "3 waiting" in health["detail"]
        assert not poll.CURSOR_FILE.exists()
        assert not poll.LOG_FILE.exists() or "processing" not in poll.LOG_FILE.read_text()


class TestLoginLapse:
    """A dead claude login holds the queue, like the daily ceiling, instead of
    filing every waiting annotation under the rules for good."""

    ROWS = ["2026-10-16T23:57:28+00:00", "2026-10-16T23:58:07+00:00", "2026-10-16T23:58:25+00:00"]

    def _run(self, monkeypatch, signed_out_from):
        """One poll in which every call from row `signed_out_from` on finds no login."""
        rows = _rows(*self.ROWS)
        monkeypatch.setattr(poll, "MAX_PER_RUN", 0)
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: rows)
        calls = []

        def process(ann, dry_run=False):
            calls.append(ann["id"])
            if len(calls) > signed_out_from:
                raise poll.ClaudeAuthError("claude cli is not authenticated (Not logged in)")
            return {"id": ann["id"], "classified_by": poll.MODEL}

        monkeypatch.setattr(poll, "process", process)
        poll.main()
        return calls, json.loads(poll.HEALTH_FILE.read_text())

    def test_holds_the_cursor_at_the_last_classified_row(self, monkeypatch):
        calls, health = self._run(monkeypatch, signed_out_from=1)
        assert calls == ["a0", "a1"]  # a2 is not even tried
        assert json.loads(poll.CURSOR_FILE.read_text())["search_after"] == self.ROWS[0]
        assert set(json.loads(poll.SEEN_FILE.read_text())) == {"a0"}
        assert health["status"] == "auth"
        assert health["processed"] == 1
        assert "2 waiting" in health["detail"]
        assert "sign in" in health["detail"]
        assert "daily spend ceiling" not in poll.LOG_FILE.read_text()

    def test_a_standing_lapse_is_logged_once_not_every_poll(self, monkeypatch):
        self._run(monkeypatch, signed_out_from=0)
        _, health = self._run(monkeypatch, signed_out_from=0)
        text = poll.LOG_FILE.read_text()
        assert text.count("not authenticated") == 1
        assert text.count("processing") == 1  # the retrying poll stays quiet
        assert health["status"] == "auth"
        assert "3 waiting" in health["detail"]
        assert not poll.CURSOR_FILE.exists()

    def test_a_dry_run_reports_the_lapse_without_marking_it(self, monkeypatch):
        rows = _rows(*self.ROWS)
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: rows)

        def signed_out(ann, dry_run=False):
            raise poll.ClaudeAuthError("claude cli is not authenticated (Not logged in)")

        monkeypatch.setattr(poll, "process", signed_out)
        monkeypatch.setattr(poll.sys, "argv", ["poll.py", "--dry-run"])
        poll.main()
        assert "not authenticated" in poll.LOG_FILE.read_text()
        assert not poll.AUTHFAIL_FILE.exists()
        assert not poll.HEALTH_FILE.exists()


@pytest.mark.usefixtures("routing")
class TestMissingCli:
    """A claude binary that is gone holds the queue like a dead login, rather
    than filing every annotation under the rules for good."""

    def test_holds_the_queue_and_says_what_to_fix(self, tmp_path, monkeypatch):
        rows = [
            sample_annotation(id="a0", updated="2026-10-18T10:00:00+00:00"),
            sample_annotation(id="a1", updated="2026-10-18T10:01:00+00:00"),
        ]
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: rows)
        monkeypatch.setitem(poll.CONFIG, "claude_bin", str(tmp_path / "absent"))
        monkeypatch.setitem(poll.CONFIG, "since", "2026-10-18T00:00:00+00:00")  # no cursor write
        poll.main()
        health = json.loads(poll.HEALTH_FILE.read_text())
        assert health["status"] == "no-cli"
        assert "2 waiting" in health["detail"]
        assert "claude_bin" in health["detail"]
        assert not poll.CURSOR_FILE.exists()
        assert not poll.SEEN_FILE.exists()
        log = poll.LOG_FILE.read_text()
        assert "could not start" in log
        assert "rules-fallback" not in log and "falling back" not in log

    def test_switching_to_rules_mode_ends_the_hold(self, monkeypatch):
        # the lapse marker mutes the "processing" line; with no CLI to wait
        # on, a marker left from before the switch would mute it for good
        poll.AUTHFAIL_FILE.write_text("claude cli could not start (…)")
        rows = [sample_annotation(id="a0", updated="2026-10-18T10:00:00+00:00", tags=[])]
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: rows)
        monkeypatch.setattr(poll, "MODEL", "rules")
        poll.main()
        assert not poll.AUTHFAIL_FILE.exists()
        assert "processing 1" in poll.LOG_FILE.read_text()
        assert json.loads(poll.HEALTH_FILE.read_text())["status"] == "ok"


class TestDryRunLog:
    def test_a_dry_run_says_so_in_the_watcher_log(self, monkeypatch):
        # A maintainer's dry run on 2026-10-06 left a bare "processing 1" line
        # that a later health review read as a real run that never finished.
        rows = _rows("2026-10-06T12:00:00+00:00")
        monkeypatch.setattr(poll, "fetch_new", lambda cursor: rows)
        monkeypatch.setattr(
            poll, "process", lambda ann, dry_run=False: {"id": ann["id"], "classified_by": "x"}
        )
        monkeypatch.setattr(poll.sys, "argv", ["poll.py", "--dry-run"])
        poll.main()
        assert "(dry run)" in poll.LOG_FILE.read_text()


class _FakeSearch:
    """/api/search as probed live: `updated` and `created` carry microseconds,
    but the sort and `search_after` both work on the stamp truncated to
    milliseconds, and a page holds only rows strictly after it. Ties keep
    insertion order."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    @staticmethod
    def _ms(stamp):
        return stamp[:23]  # YYYY-MM-DDTHH:MM:SS.mmm

    def __call__(self, params, **kw):
        self.calls += 1
        key, after = params["sort"], self._ms(params["search_after"])
        hits = sorted(
            (r for r in self.rows if self._ms(r[key]) > after), key=lambda r: self._ms(r[key])
        )
        return {"rows": hits[: params["limit"]]}


class TestMillisecondCursor:
    """A cut inside one millisecond must not strand the rest of that millisecond."""

    STAMPS = [
        "2026-09-20T00:00:00.100000+00:00",
        "2026-09-20T00:00:01.500100+00:00",  # these two share a millisecond
        "2026-09-20T00:00:01.500900+00:00",
        "2026-09-20T00:00:02.000000+00:00",
    ]

    def test_ms_before_steps_back_one_millisecond_from_the_truncated_stamp(self):
        assert (
            poll.ms_before("2026-09-20T00:00:01.500900+00:00") == "2026-09-20T00:00:01.499000+00:00"
        )

    def test_ms_before_crosses_a_second_boundary(self):
        assert (
            poll.ms_before("2026-09-20T00:00:00.000500+00:00") == "2026-09-19T23:59:59.999000+00:00"
        )

    def test_ms_before_passes_an_unparseable_cursor_through(self):
        assert poll.ms_before(None) is None
        assert poll.ms_before("not-a-stamp") == "not-a-stamp"

    def test_a_page_boundary_inside_one_millisecond_loses_nothing(self, monkeypatch):
        monkeypatch.setattr(poll, "search", _FakeSearch(_rows(*self.STAMPS)))
        rows = poll.fetch_new("2026-09-19T00:00:00.000000+00:00", page_size=2)
        assert [r["id"] for r in rows] == ["a0", "a1", "a2", "a3"]

    def test_a_batch_cut_inside_one_millisecond_is_picked_up_next_run(self, monkeypatch):
        monkeypatch.setattr(poll, "search", _FakeSearch(_rows(*self.STAMPS)))
        monkeypatch.setattr(
            poll, "CONFIG", {**poll.CONFIG, "since": "2026-09-19T00:00:00.000000+00:00"}
        )
        monkeypatch.setattr(poll, "MAX_PER_RUN", 2)
        monkeypatch.setattr(poll, "MAX_DAILY_USD", 0)
        done = []
        monkeypatch.setattr(
            poll,
            "process",
            lambda ann, dry_run=False: (
                done.append(ann["id"]) or {"id": ann["id"], "classified_by": poll.MODEL}
            ),
        )
        for _ in range(3):
            poll.main()
        assert done == ["a0", "a1", "a2", "a3"]

    def test_an_idle_poll_asks_once_and_reclassifies_nothing(self, monkeypatch):
        fake = _FakeSearch(_rows(*self.STAMPS))
        monkeypatch.setattr(poll, "search", fake)
        poll.CURSOR_FILE.write_text(json.dumps({"search_after": self.STAMPS[3]}))
        poll.SEEN_FILE.write_text(json.dumps({"a3": self.STAMPS[3]}))
        monkeypatch.setattr(poll, "process", lambda ann, dry_run=False: pytest.fail(ann["id"]))
        poll.main()
        assert fake.calls == 1  # the re-read cursor row is a short page
        assert json.loads(poll.HEALTH_FILE.read_text())["status"] == "ok"

    def test_a_millisecond_fuller_than_a_page_still_ends(self, monkeypatch):
        # the API offers no tiebreaker, so past page_size rows in one
        # millisecond only the strict cursor moves on (a2 is the known cost)
        same = "2026-09-20T00:00:01.500"
        rows = _rows(
            same + "100+00:00",
            same + "200+00:00",
            same + "300+00:00",
            "2026-09-20T00:00:02.000000+00:00",
        )
        monkeypatch.setattr(poll, "search", _FakeSearch(rows))
        got = poll.fetch_new("2026-09-19T00:00:00.000000+00:00", page_size=2)
        assert [r["id"] for r in got] == ["a0", "a1", "a3"]


class TestFirstRunCursor:
    """With no saved cursor and no `since`, the api would be asked for
    search_after=None, which it rejects (400) on every run."""

    @pytest.fixture
    def asked(self, monkeypatch):
        params = []
        monkeypatch.setattr(poll, "search", lambda p, **kw: params.append(p) or {"rows": []})
        monkeypatch.setattr(poll, "CONFIG", {k: v for k, v in poll.CONFIG.items() if k != "since"})
        return params

    def test_no_since_watches_from_the_first_run_and_saves_that_moment(self, asked):
        before = poll.datetime.now(poll.timezone.utc).isoformat(timespec="microseconds")
        poll.main()
        saved = json.loads(poll.CURSOR_FILE.read_text())["search_after"]
        assert saved >= before
        assert asked[0]["search_after"] == poll.ms_before(saved)
        poll.main()  # an idle second run starts where the first did, not at its own now
        assert asked[1]["search_after"] == poll.ms_before(saved)

    def test_a_dry_run_saves_no_cursor(self, asked):
        poll.poll_once(dry_run=True)
        assert asked[0]["search_after"] is not None
        assert not poll.CURSOR_FILE.exists()

    def test_since_still_wins_when_set(self, asked, monkeypatch):
        monkeypatch.setattr(
            poll, "CONFIG", {**poll.CONFIG, "since": "2026-09-19T00:00:00.000000+00:00"}
        )
        poll.main()
        assert asked[0]["search_after"] == poll.ms_before("2026-09-19T00:00:00.000000+00:00")
        assert not poll.CURSOR_FILE.exists()  # nothing processed, so nothing to save


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
        prompt = self._prompt(
            monkeypatch, tmp_path, "### garden — plants\n\n- `garden/roses` — roses\n"
        )
        assert '(e.g. "garden/roses/<child>")' in prompt
        assert "platform-studies" not in prompt

    def test_a_taxonomy_without_children_gets_a_neutral_example(self, monkeypatch, tmp_path):
        prompt = self._prompt(monkeypatch, tmp_path, "### garden — plants\n")
        assert '(e.g. "<existing-node>/<child>")' in prompt
        assert "architecture/map.jsonl/<child>" not in prompt  # the tail is not a node
