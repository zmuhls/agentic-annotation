"""Tests for the health checker.

Nothing here reads the maintainer's real LaunchAgents directory or the live
heartbeat: every case builds units and a health file inside a tmp dir.
"""

import json
import plistlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import appconfig  # noqa: E402
import doctor  # noqa: E402

POLL = doctor.POLL_SCRIPT


@pytest.fixture(autouse=True)
def no_real_claude(monkeypatch):
    """Keep check_claude from shelling out to whatever `claude` this machine has.

    An OSError is what a missing binary raises, so the default answer is
    "cannot tell"; tests that need a sign-in state stub `subprocess.run` again.
    """

    def refuse(*a, **k):
        raise OSError("tests never run the real claude cli")

    monkeypatch.setattr(doctor.subprocess, "run", refuse)


class FakeProc:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def _plist(tmp_path, name, interpreter, script=POLL, interval=300):
    path = tmp_path / f"{name}.plist"
    path.write_bytes(
        plistlib.dumps(
            {
                "Label": name,
                "ProgramArguments": [interpreter, str(script)],
                "StartInterval": interval,
            }
        )
    )
    return path


def _service(tmp_path, name, interpreter, script=POLL):
    path = tmp_path / f"{name}.service"
    path.write_text(f"[Service]\nExecStart={interpreter} {script}\n")
    return path


class TestFindUnits:
    def test_finds_the_unit_that_runs_this_checkout(self, tmp_path):
        agents, systemd = tmp_path / "agents", tmp_path / "systemd"
        agents.mkdir(), systemd.mkdir()
        _plist(agents, "local.watcher", "/usr/bin/python3")
        units = doctor.find_units(agents, systemd)
        assert [u.interpreter for u in units] == ["/usr/bin/python3"]
        assert units[0].interval == 300

    def test_ignores_unrelated_units(self, tmp_path):
        agents, systemd = tmp_path / "agents", tmp_path / "systemd"
        agents.mkdir(), systemd.mkdir()
        _plist(
            agents, "com.other.thing", "/usr/bin/python3", script=Path("/somewhere/else/poll.py")
        )
        assert doctor.find_units(agents, systemd) == []

    def test_unreadable_plist_does_not_crash_the_scan(self, tmp_path):
        agents, systemd = tmp_path / "agents", tmp_path / "systemd"
        agents.mkdir(), systemd.mkdir()
        (agents / "broken.plist").write_text("not a plist")
        _plist(agents, "local.watcher", "/usr/bin/python3")
        assert len(doctor.find_units(agents, systemd)) == 1

    def test_finds_systemd_services_too(self, tmp_path):
        agents, systemd = tmp_path / "agents", tmp_path / "systemd"
        agents.mkdir(), systemd.mkdir()
        _service(systemd, "watcher", "/usr/bin/python3")
        assert [u.interpreter for u in doctor.find_units(agents, systemd)] == ["/usr/bin/python3"]

    def test_missing_directories_are_fine(self, tmp_path):
        assert doctor.find_units(tmp_path / "nope", tmp_path / "also-nope") == []


class TestCheckUnits:
    def test_flags_an_interpreter_that_no_longer_exists(self, tmp_path):
        # the failure this whole check exists for: anaconda uninstalled, launchd
        # cannot spawn the job, and nothing is ever written to the log again
        agents, systemd = tmp_path / "agents", tmp_path / "systemd"
        agents.mkdir(), systemd.mkdir()
        _plist(agents, "local.watcher", "/opt/gone/bin/python3")
        check = doctor.check_units(doctor.find_units(agents, systemd))[0]
        assert check.level == "fail"
        assert "/opt/gone/bin/python3" in check.detail

    def test_passes_when_the_interpreter_is_there(self, tmp_path):
        agents, systemd = tmp_path / "agents", tmp_path / "systemd"
        agents.mkdir(), systemd.mkdir()
        _plist(agents, "local.watcher", sys.executable)
        assert doctor.check_units(doctor.find_units(agents, systemd))[0].level == "ok"

    def test_no_unit_at_all_is_a_warning_not_a_failure(self):
        # a cron install is real but not discoverable from a directory scan
        check = doctor.check_units([])[0]
        assert check.level == "warn"


class TestCheckHeartbeat:
    def _now(self):
        return datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

    def _health(self, minutes_ago, **extra):
        stamp = (self._now() - timedelta(minutes=minutes_ago)).isoformat()
        return {"last_run": stamp, "status": "ok", **extra}

    def test_fresh_heartbeat_passes(self):
        assert doctor.check_heartbeat(self._health(2), self._now(), 900).level == "ok"

    def test_stale_heartbeat_fails(self):
        check = doctor.check_heartbeat(self._health(60 * 24 * 4), self._now(), 900)
        assert check.level == "fail"
        assert "4 days" in check.detail or "days" in check.detail

    def test_missing_heartbeat_warns_rather_than_failing(self):
        # a fresh clone has never polled; that is not a broken install
        assert doctor.check_heartbeat(None, self._now(), 900).level == "warn"

    def test_unparseable_timestamp_fails(self):
        check = doctor.check_heartbeat({"last_run": "who knows"}, self._now(), 900)
        assert check.level == "fail"

    def test_last_run_status_is_reported(self):
        health = self._health(2, status="api-unreachable", detail="dns")
        check = doctor.check_heartbeat(health, self._now(), 900)
        assert check.level == "warn"
        assert "api-unreachable" in check.detail

    def test_rules_fallbacks_are_surfaced(self):
        # classification silently degrading to rules is the other silent failure
        check = doctor.check_heartbeat(self._health(2, fallbacks=3), self._now(), 900)
        assert check.level == "warn"
        assert "fallback" in check.detail

    def test_lifetime_spend_is_surfaced_when_there_is_any(self):
        check = doctor.check_heartbeat(
            self._health(2, processed=1, cost_usd_total=4.3079), self._now(), 900
        )
        assert check.level == "ok"
        assert "$4.31 spent" in check.detail

    def test_a_watcher_that_has_spent_nothing_says_nothing_about_money(self):
        check = doctor.check_heartbeat(self._health(2), self._now(), 900)
        assert "spent" not in check.detail

    def test_todays_spend_is_shown_against_the_daily_ceiling(self):
        health = self._health(2, cost_day="2026-09-20", cost_usd_today=1.234)
        check = doctor.check_heartbeat(health, self._now(), 900, max_daily_usd=5)
        assert "$1.23 of $5.00 daily ceiling" in check.detail

    def test_yesterdays_spend_does_not_count_against_today(self):
        health = self._health(2, cost_day="2026-09-19", cost_usd_today=4.9)
        check = doctor.check_heartbeat(health, self._now(), 900, max_daily_usd=5)
        assert "$0.00 of $5.00" in check.detail

    def test_todays_spend_without_a_ceiling_is_shown_plainly(self):
        health = self._health(2, cost_day="2026-09-20", cost_usd_today=0.2)
        check = doctor.check_heartbeat(health, self._now(), 900)
        assert "$0.20 today" in check.detail
        assert "ceiling" not in check.detail


class TestLoadHealth:
    def test_missing_file_is_none(self, tmp_path):
        assert doctor.load_health(tmp_path / "health.json") is None

    def test_corrupt_file_is_none(self, tmp_path):
        path = tmp_path / "health.json"
        path.write_text("{ truncated")
        assert doctor.load_health(path) is None

    def test_reads_what_poll_wrote(self, tmp_path):
        path = tmp_path / "health.json"
        path.write_text(json.dumps({"last_run": "2026-09-20T12:00:00+00:00"}))
        assert doctor.load_health(path)["last_run"] == "2026-09-20T12:00:00+00:00"


class TestCheckSince:
    @pytest.mark.parametrize(
        "since",
        [
            "2024-07-15T00:00:00.000000+00:00",  # config.example.json's form
            "2024-07-15T00:00:00Z",  # Z, which Python 3.9 cannot parse alone
            "2024-07-15",
            "1721001600000",  # epoch milliseconds, which the api allows
            1721001600000,
        ],
    )
    def test_dates_the_api_reads_pass_silently(self, since):
        assert doctor.check_since({"since": since}) == []

    def test_no_since_is_fine(self):
        # without one the watcher starts at its first run (see INSTALL.md)
        assert doctor.check_since({}) == []

    @pytest.mark.parametrize("since", ["garbage", "2024-13-45T00:00:00+00:00"])
    def test_an_unreadable_since_is_flagged(self, since):
        # the api answers 400 to both (probed), on every poll that has no cursor yet
        [check] = doctor.check_since({"since": since})
        assert check.level == "warn"
        assert repr(since) in check.detail


class TestCheckToken:
    """/api/profile is the only endpoint that reports a bad token: /api/search
    answers 200 as an anonymous user instead (probed live), so a wrong or revoked
    token drops private-group annotations with no error anywhere."""

    CONFIG = {"api_token": "6879-secret-token-value", "user": "acct:me@hypothes.is"}

    def test_a_token_the_api_knows_passes(self):
        check = doctor.check_token(
            self.CONFIG, fetch=lambda token: {"userid": "acct:me@hypothes.is"}
        )
        assert check.level == "ok"
        assert "acct:me@hypothes.is" in check.detail

    def test_a_token_the_api_does_not_know_fails(self):
        # the api's reply to a bad token: a 200 with no user on it
        check = doctor.check_token(self.CONFIG, fetch=lambda token: {"userid": None})
        assert check.level == "fail"
        assert "private" in check.detail
        assert "6879-secret" not in check.detail  # never print the token

    def test_a_token_for_a_different_account_warns(self):
        check = doctor.check_token(
            self.CONFIG, fetch=lambda token: {"userid": "acct:other@hypothes.is"}
        )
        assert check.level == "warn"
        assert "acct:other@hypothes.is" in check.detail
        assert "acct:me@hypothes.is" in check.detail

    def test_a_placeholder_token_is_not_sent_anywhere(self):
        calls = []
        config = {"api_token": "YOUR-HYPOTHESIS-DEVELOPER-TOKEN", "user": "acct:me@hypothes.is"}
        check = doctor.check_token(config, fetch=lambda token: calls.append(token))
        assert check.level == "fail"
        assert calls == []

    def test_an_unreachable_api_warns_rather_than_failing(self):
        def down(token):
            raise OSError("dns")

        check = doctor.check_token(self.CONFIG, fetch=down)
        assert check.level == "warn"
        assert "dns" in check.detail

    def test_offline_skips_the_network_entirely(self):
        calls = []
        checks = doctor.run_checks(
            config=self.CONFIG, offline=True, fetch_profile=lambda token: calls.append(token)
        )
        assert calls == []
        assert "token" not in [c.name for c in checks]

    def test_run_checks_includes_the_token_check_by_default(self, tmp_path):
        checks = doctor.run_checks(
            config=self.CONFIG,
            launch_agents=tmp_path,
            systemd_dir=tmp_path,
            health_file=tmp_path / "health.json",
            fetch_profile=lambda token: {"userid": "acct:me@hypothes.is"},
        )
        assert [c.level for c in checks if c.name == "token"] == ["ok"]


class TestCheckClaude:
    """`claude auth status` reads the local login: no model call, no spend.

    The binary being on PATH said nothing about whether it could classify: on
    2026-10-16 the watcher's calls found no login, and a binary on PATH was all
    doctor looked for.
    """

    def _cli(self, tmp_path, monkeypatch, returncode=0, stdout=""):
        binary = tmp_path / "claude"
        binary.write_text("")
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            return FakeProc(returncode, stdout)

        monkeypatch.setattr(doctor.subprocess, "run", run)
        return {"claude_bin": str(binary)}, calls

    def test_a_signed_in_cli_passes(self, tmp_path, monkeypatch):
        status = json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": "me@x.example"})
        config, calls = self._cli(tmp_path, monkeypatch, stdout=status)
        check = doctor.check_claude(config)
        assert check.level == "ok"
        assert "signed in" in check.detail
        assert "me@x.example" not in check.detail  # the account stays private
        assert calls == [[config["claude_bin"], "auth", "status", "--json"]]

    def test_a_signed_out_cli_fails(self, tmp_path, monkeypatch):
        config, _ = self._cli(tmp_path, monkeypatch, 1, json.dumps({"loggedIn": False}))
        check = doctor.check_claude(config)
        assert check.level == "fail"
        assert "sign in" in check.detail

    @pytest.mark.parametrize("stdout", ["", "error: unknown command 'auth'", "[]"])
    def test_a_cli_that_cannot_say_still_passes_on_the_binary(self, tmp_path, monkeypatch, stdout):
        # an older CLI without `auth status` must not turn doctor red
        config, _ = self._cli(tmp_path, monkeypatch, 1, stdout)
        check = doctor.check_claude(config)
        assert check.level == "ok"
        assert "unknown" in check.detail

    def test_a_cli_that_will_not_start_still_passes_on_the_binary(self, tmp_path):
        binary = tmp_path / "claude"
        binary.write_text("")
        check = doctor.check_claude({"claude_bin": str(binary)})  # autouse: OSError
        assert check.level == "ok"
        assert "unknown" in check.detail

    def test_a_missing_binary_is_not_asked_anything(self, tmp_path):
        check = doctor.check_claude({"claude_bin": str(tmp_path / "absent")})
        assert check.level == "fail"
        assert "not found" in check.detail
        assert "holds new annotations" in check.detail  # the watcher no longer files them
        assert '"model": "rules"' in check.detail  # the way to run without one

    def test_rules_mode_needs_no_binary(self, tmp_path):
        check = doctor.check_claude({"model": "rules", "claude_bin": str(tmp_path / "absent")})
        assert check.level == "ok"
        assert "rules" in check.detail

    def test_looks_where_the_watcher_looks_off_path(self, tmp_path, monkeypatch):
        # launchd's PATH is not a login shell's: poll.py falls back to the
        # installer's ~/.local/bin/claude, so doctor must not fail what it finds
        binary = tmp_path / "claude"
        binary.write_text("")
        monkeypatch.setattr(appconfig.shutil, "which", lambda name: None)
        monkeypatch.setattr(appconfig, "DEFAULT_CLAUDE_BIN", binary)
        check = doctor.check_claude({})  # autouse: OSError, so sign-in state unknown
        assert check.level == "ok"
        assert str(binary) in check.detail


class TestExitCode:
    def test_nonzero_when_any_check_fails(self):
        checks = [doctor.Check("ok", "a", ""), doctor.Check("fail", "b", "")]
        assert doctor.exit_code(checks) == 1

    def test_warnings_alone_still_exit_zero(self):
        assert doctor.exit_code([doctor.Check("warn", "a", "")]) == 0
