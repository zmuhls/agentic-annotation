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

import doctor  # noqa: E402

POLL = doctor.POLL_SCRIPT


def _plist(tmp_path, name, interpreter, script=POLL, interval=300):
    path = tmp_path / f"{name}.plist"
    path.write_bytes(plistlib.dumps({
        "Label": name,
        "ProgramArguments": [interpreter, str(script)],
        "StartInterval": interval,
    }))
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
        _plist(agents, "com.other.thing", "/usr/bin/python3",
               script=Path("/somewhere/else/poll.py"))
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
        assert [u.interpreter for u in doctor.find_units(agents, systemd)] \
            == ["/usr/bin/python3"]

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
            self._health(2, processed=1, cost_usd_total=4.3079), self._now(), 900)
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
    @pytest.mark.parametrize("since", [
        "2024-07-15T00:00:00.000000+00:00",  # config.example.json's form
        "2024-07-15T00:00:00Z",              # Z, which Python 3.9 cannot parse alone
        "2024-07-15",
        "1721001600000",                     # epoch milliseconds, which the api allows
        1721001600000,
    ])
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


class TestExitCode:
    def test_nonzero_when_any_check_fails(self):
        checks = [doctor.Check("ok", "a", ""), doctor.Check("fail", "b", "")]
        assert doctor.exit_code(checks) == 1

    def test_warnings_alone_still_exit_zero(self):
        assert doctor.exit_code([doctor.Check("warn", "a", "")]) == 0
