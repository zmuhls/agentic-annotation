#!/usr/bin/env python3
"""Answer one question: is the watcher still actually running?

Written after it stopped for four days without a word. The scheduler unit named
an interpreter (`/opt/anaconda3/bin/python3`) that was later uninstalled, so
launchd could not spawn the process at all — no run, no traceback, no log line.
A quiet `watcher.log` is also what a quiet week looks like, so the daily review
had nothing to catch it with.

So check the things whose absence is otherwise invisible: a scheduler unit for
*this* checkout whose interpreter still exists, a heartbeat young enough that a
poll must have happened, the `claude` binary, and the config keys poll.py needs.

    python3 scripts/doctor.py

Exits non-zero if anything is broken, so it can run from a cron/CI check.
"""

import argparse
import json
import plistlib
import shutil
import sys
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from appconfig import load_config  # noqa: E402

POLL_SCRIPT = ROOT / "scripts" / "poll.py"
HEALTH_FILE = ROOT / "data" / "health.json"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
DEFAULT_INTERVAL = 300
# three missed polls: one laptop sleep is normal, three in a row is not
MISSED_POLLS_ALLOWED = 3

Unit = namedtuple("Unit", "path interpreter interval")
Check = namedtuple("Check", "level name detail")  # level: ok | warn | fail

MARKS = {"ok": "ok  ", "warn": "warn", "fail": "FAIL"}


def find_units(launch_agents=LAUNCH_AGENTS, systemd_dir=SYSTEMD_DIR,
               poll_script=POLL_SCRIPT):
    """Scheduler units that run *this* checkout's poll.py.

    A cron install cannot be found this way; that is what the "no unit" warning
    in check_units is for.
    """
    units, script = [], str(poll_script)
    for path in sorted(Path(launch_agents).glob("*.plist")) if Path(launch_agents).is_dir() else []:
        try:
            plist = plistlib.loads(path.read_bytes())
        except Exception:
            continue  # someone else's malformed plist is not our problem
        args = plist.get("ProgramArguments") or []
        if script in args and args:
            units.append(Unit(path, args[0], plist.get("StartInterval")))
    for path in sorted(Path(systemd_dir).glob("*.service")) if Path(systemd_dir).is_dir() else []:
        for line in path.read_text().splitlines():
            if line.startswith("ExecStart=") and script in line:
                units.append(Unit(path, line.split("=", 1)[1].split()[0], None))
    return units


def check_units(units):
    if not units:
        return [Check("warn", "scheduler", "no launchd/systemd unit found for this "
                      "checkout — see INSTALL.md (a crontab install is not detectable)")]
    checks = []
    for unit in units:
        if Path(unit.interpreter).exists():
            checks.append(Check("ok", "scheduler",
                                f"{unit.path.name} runs {unit.interpreter}"))
        else:
            checks.append(Check(
                "fail", "scheduler",
                f"{unit.path.name} names {unit.interpreter}, which no longer exists — "
                "the job cannot start; re-run scripts/install_agent.py --write --force "
                "with a present interpreter, then reload the unit"))
    return checks


def interval_for(units):
    for unit in units:
        if unit.interval:
            return unit.interval
    return DEFAULT_INTERVAL


def load_health(path=HEALTH_FILE):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _age_phrase(delta):
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min ago"
    if minutes < 60 * 24:
        return f"{minutes // 60} hours ago"
    return f"{minutes // (60 * 24)} days ago"


def check_heartbeat(health, now, max_age_seconds):
    """poll.py stamps data/health.json on every completed run."""
    if health is None:
        return Check("warn", "heartbeat",
                     "no data/health.json yet — has poll.py ever run here?")
    try:
        last = datetime.fromisoformat(health.get("last_run", ""))
    except (TypeError, ValueError):
        return Check("fail", "heartbeat",
                     f"unreadable last_run: {health.get('last_run')!r}")
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = now - last
    when = _age_phrase(age)
    if age.total_seconds() > max_age_seconds:
        return Check("fail", "heartbeat",
                     f"last poll {when} — the watcher is not running")
    status = health.get("status", "ok")
    fallbacks = health.get("fallbacks") or 0
    if status != "ok":
        return Check("warn", "heartbeat",
                     f"last poll {when} ended {status}: {health.get('detail', '')}"[:160])
    if fallbacks:
        return Check("warn", "heartbeat",
                     f"last poll {when}, but {fallbacks} annotation(s) took the "
                     "rules fallback — check the classifier (run `claude` and sign in)")
    spend = health.get("cost_usd_total") or 0
    spend_note = f", ${spend:.2f} spent on classification to date" if spend else ""
    return Check("ok", "heartbeat",
                 f"last poll {when}, {health.get('processed', 0)} processed{spend_note}")


def check_config(config):
    missing = [key for key in ("api_token", "user") if not config.get(key)]
    if missing:
        return Check("fail", "config",
                     f"config.json is missing {', '.join(missing)} — copy "
                     "config.example.json and fill it in")
    return Check("ok", "config", f"watching {config['user']}")  # never print the token


def check_claude(config):
    binary = config.get("claude_bin") or shutil.which("claude")
    if binary and Path(binary).exists():
        return Check("ok", "claude cli", str(binary))
    return Check("fail", "claude cli",
                 "not on PATH — classification would fall back to rules")


def run_checks(now=None, config=None, launch_agents=LAUNCH_AGENTS,
               systemd_dir=SYSTEMD_DIR, health_file=HEALTH_FILE):
    now = now or datetime.now(timezone.utc)
    config = load_config() if config is None else config
    units = find_units(launch_agents, systemd_dir)
    max_age = interval_for(units) * MISSED_POLLS_ALLOWED
    return [check_config(config), check_claude(config), *check_units(units),
            check_heartbeat(load_health(health_file), now, max_age)]


def exit_code(checks):
    return 1 if any(c.level == "fail" for c in checks) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args(argv)
    checks = run_checks()
    if args.json:
        print(json.dumps([c._asdict() for c in checks], indent=2))
    else:
        for check in checks:
            print(f"{MARKS[check.level]} {check.name}: {check.detail}")
    return exit_code(checks)


if __name__ == "__main__":
    raise SystemExit(main())
