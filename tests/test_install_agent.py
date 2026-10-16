"""Tests for the scheduler unit generator.

Nothing here installs anything: every case renders to a string or writes into a
tmp dir, so the maintainer's real LaunchAgents directory is never touched.
"""

import plistlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import install_agent  # noqa: E402

ROOT = install_agent.ROOT


class TestLaunchd:
    def _plist(self, **kw):
        args = {"label": "local.test-watcher", "python": "/usr/bin/python3", "interval": 300, **kw}
        return plistlib.loads(install_agent.launchd_plist(**args).encode())

    def test_paths_come_from_the_checkout_not_a_literal(self):
        plist = self._plist()
        assert plist["ProgramArguments"] == ["/usr/bin/python3", str(ROOT / "scripts" / "poll.py")]
        assert plist["WorkingDirectory"] == str(ROOT)
        assert plist["StandardOutPath"] == str(ROOT / "logs" / "launchd.log")

    def test_label_and_interval_are_configurable(self):
        plist = self._plist(label="com.example.watcher", interval=600)
        assert plist["Label"] == "com.example.watcher"
        assert plist["StartInterval"] == 600

    def test_path_env_leads_with_the_chosen_interpreters_dir(self):
        # launchd agents inherit almost no environment; poll.py shells out to `claude`
        entries = self._plist(python="/opt/py/bin/python3")["EnvironmentVariables"]["PATH"]
        assert entries.split(":")[0] == "/opt/py/bin"
        assert str(Path.home() / ".local" / "bin") in entries

    def test_no_duplicate_path_entries(self):
        entries = self._plist(python="/usr/bin/python3")["EnvironmentVariables"]["PATH"]
        assert len(entries.split(":")) == len(set(entries.split(":")))


class TestSystemd:
    def test_emits_a_service_and_a_timer_bound_to_it(self):
        units = install_agent.systemd_units("watcher", "/usr/bin/python3", 300)
        assert set(units) == {"watcher.service", "watcher.timer"}
        assert (
            f"ExecStart=/usr/bin/python3 {ROOT / 'scripts' / 'poll.py'}" in units["watcher.service"]
        )
        assert "Unit=watcher.service" in units["watcher.timer"]
        assert "OnUnitActiveSec=300s" in units["watcher.timer"]


class TestCron:
    def test_minute_step_matches_the_interval(self):
        assert install_agent.cron_line("/usr/bin/python3", 300).startswith("*/5 * * * *")
        assert install_agent.cron_line("/usr/bin/python3", 600).startswith("*/10 * * * *")

    def test_runs_from_the_checkout(self):
        assert f"cd {ROOT} && /usr/bin/python3 scripts/poll.py" in install_agent.cron_line(
            "/usr/bin/python3", 300
        )


class TestWrite:
    def test_refuses_to_clobber_without_force(self, tmp_path):
        path = tmp_path / "unit.plist"
        path.write_text("existing")
        with pytest.raises(SystemExit):
            install_agent.write_file(path, "new", force=False)
        assert path.read_text() == "existing"
        install_agent.write_file(path, "new", force=True)
        assert path.read_text() == "new"


class TestCli:
    def test_dry_run_prints_and_installs_nothing(self, capsys, monkeypatch):
        monkeypatch.setattr(
            install_agent, "write_file", lambda *a, **k: pytest.fail("must not write")
        )
        assert install_agent.main(["--target", "launchd"]) == 0
        assert "<key>Label</key>" in capsys.readouterr().out


class TestInterpreterPreflight:
    """A unit naming an interpreter that is not there fails silently later.

    launchd answers `last exit code = 78: EX_CONFIG` and writes nothing to the
    log, which is how this watcher lost four days after an anaconda uninstall.
    Catch it at install time, where there is someone to read the message.
    """

    def test_write_refuses_a_missing_interpreter(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            install_agent, "write_file", lambda *a, **k: pytest.fail("must not write")
        )
        with pytest.raises(SystemExit, match="/opt/gone/bin/python3"):
            install_agent.main(
                ["--target", "launchd", "--write", "--python", "/opt/gone/bin/python3"]
            )

    def test_the_override_is_for_generating_units_for_another_machine(self, tmp_path, monkeypatch):
        written = {}
        monkeypatch.setattr(
            install_agent, "write_file", lambda path, text, force: written.setdefault(path, text)
        )
        assert (
            install_agent.main(
                [
                    "--target",
                    "systemd",
                    "--write",
                    "--allow-missing-python",
                    "--python",
                    "/opt/gone/bin/python3",
                ]
            )
            == 0
        )
        assert written

    def test_printing_a_unit_only_warns(self, capsys):
        assert install_agent.main(["--target", "launchd", "--python", "/opt/gone/bin/python3"]) == 0
        captured = capsys.readouterr()
        assert "<key>Label</key>" in captured.out
        assert "does not exist" in captured.err

    def test_a_real_interpreter_passes_quietly(self, capsys):
        assert install_agent.main(["--target", "launchd", "--python", sys.executable]) == 0
        assert "does not exist" not in capsys.readouterr().err
