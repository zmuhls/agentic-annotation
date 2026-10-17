#!/usr/bin/env python3
"""Answer one question: is the watcher still actually running?

Written after it stopped for four days without a word. The scheduler unit named
an interpreter (`/opt/anaconda3/bin/python3`) that was later uninstalled, so
launchd could not spawn the process at all — no run, no traceback, no log line.
A quiet `watcher.log` is also what a quiet week looks like, so the daily review
had nothing to catch it with.

So check the things whose absence is otherwise invisible: a scheduler unit for
*this* checkout whose interpreter still exists, a heartbeat young enough that a
poll must have happened, the `claude` binary and whether it is signed in (`claude
auth status`, which spends nothing), the config keys poll.py needs, and
whether the API still recognizes the token (one GET to /api/profile; skip it
with --offline).

    python3 scripts/doctor.py
    python3 scripts/doctor.py --offline   # no network: skip the token check

Exits non-zero if anything is broken, so it can run from a cron/CI check.
"""

import argparse
import json
import plistlib
import shutil
import subprocess
import sys
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from appconfig import load_config  # noqa: E402
from bootstrap_ia import get as api_get  # noqa: E402

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


def find_units(launch_agents=LAUNCH_AGENTS, systemd_dir=SYSTEMD_DIR, poll_script=POLL_SCRIPT):
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
        return [
            Check(
                "warn",
                "scheduler",
                "no launchd/systemd unit found for this "
                "checkout — see INSTALL.md (a crontab install is not detectable)",
            )
        ]
    checks = []
    for unit in units:
        if Path(unit.interpreter).exists():
            checks.append(Check("ok", "scheduler", f"{unit.path.name} runs {unit.interpreter}"))
        else:
            checks.append(
                Check(
                    "fail",
                    "scheduler",
                    f"{unit.path.name} names {unit.interpreter}, which no longer exists — "
                    "the job cannot start; re-run scripts/install_agent.py --write --force "
                    "with a present interpreter, then reload the unit",
                )
            )
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


def _spend_note(health, now, max_daily_usd):
    """Lifetime spend, plus today's against the `max_daily_usd` ceiling if set."""
    parts = []
    total = health.get("cost_usd_total") or 0
    if total:
        parts.append(f"${total:.2f} spent on classification to date")
    # cost_usd_today belongs to cost_day; a stale day means nothing spent today
    today = (
        (health.get("cost_usd_today") or 0)
        if health.get("cost_day") == now.date().isoformat()
        else 0
    )
    if max_daily_usd:
        parts.append(f"${today:.2f} of ${max_daily_usd:.2f} daily ceiling used today")
    elif today:
        parts.append(f"${today:.2f} today")
    return "".join(f", {p}" for p in parts)


def check_heartbeat(health, now, max_age_seconds, max_daily_usd=0):
    """poll.py stamps data/health.json on every completed run."""
    if health is None:
        return Check("warn", "heartbeat", "no data/health.json yet — has poll.py ever run here?")
    try:
        last = datetime.fromisoformat(health.get("last_run", ""))
    except (TypeError, ValueError):
        return Check("fail", "heartbeat", f"unreadable last_run: {health.get('last_run')!r}")
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = now - last
    when = _age_phrase(age)
    if age.total_seconds() > max_age_seconds:
        return Check("fail", "heartbeat", f"last poll {when} — the watcher is not running")
    status = health.get("status", "ok")
    fallbacks = health.get("fallbacks") or 0
    if status != "ok":
        return Check(
            "warn",
            "heartbeat",
            f"last poll {when} ended {status}: {health.get('detail', '')}"[:160],
        )
    if fallbacks:
        return Check(
            "warn",
            "heartbeat",
            f"last poll {when}, but {fallbacks} annotation(s) took the "
            "rules fallback — check the classifier (run `claude` and sign in)",
        )
    spend_note = _spend_note(health, now, max_daily_usd)
    return Check(
        "ok", "heartbeat", f"last poll {when}, {health.get('processed', 0)} processed{spend_note}"
    )


def check_config(config):
    missing = [key for key in ("api_token", "user") if not config.get(key)]
    if missing:
        return Check(
            "fail",
            "config",
            f"config.json is missing {', '.join(missing)} — copy "
            "config.example.json and fill it in",
        )
    return Check("ok", "config", f"watching {config['user']}")  # never print the token


def check_since(config):
    """Flag a `since` the api may refuse; say nothing when it is fine or unset.

    /api/search answers 400 to a `search_after` it cannot read as a date
    (probed: "garbage", a 13th month). The watcher's first poll and the
    backfill both start from `since`, so a bad one fails every poll until a
    cursor exists, and the log shows only the api's complaint about
    `search_after`, a name the adopter never wrote. ISO 8601 and epoch
    milliseconds pass; the api reads some looser forms too, so this warns
    rather than fails.
    """
    since = config.get("since")
    if not since:
        return []
    text = str(since)
    if text.isdigit():
        return []
    try:  # Python 3.9's fromisoformat has no trailing Z
        datetime.fromisoformat(text[:-1] + "+00:00" if text[-1:] in "Zz" else text)
        return []
    except ValueError:
        return [
            Check(
                "warn",
                "since",
                f"config.json `since` is {since!r}, not an ISO 8601 date — the "
                "api may answer 400 to every poll until a cursor exists; use "
                "e.g. 2024-07-15T00:00:00+00:00",
            )
        ]


def fetch_profile(token):
    """GET /api/profile as the token's owner."""
    return api_get("profile", token)


def check_token(config, fetch=fetch_profile):
    """Ask the API whose token this is.

    /api/search never rejects a token it does not recognize: it answers 200 as
    an anonymous user and returns public rows only (probed live), so a wrong or
    revoked token drops every private-group annotation with no error in any
    log. /api/profile is the one endpoint that tells: `userid` is null for a
    token the API does not know, and the account for one it does.
    """
    token = config.get("api_token") or ""
    user = config.get("user") or ""
    if not token or token.startswith("YOUR-"):
        return Check(
            "fail",
            "token",
            "config.json still holds the placeholder token — "
            "make one at hypothes.is/account/developer",
        )
    try:
        userid = fetch(token).get("userid")
    except Exception as e:  # URLError, HTTPError, timeout, bad JSON: all "could not ask"
        return Check(
            "warn",
            "token",
            f"could not reach the api to verify the token "
            f"({e}); run again when online, or pass --offline",
        )
    if not userid:
        return Check(
            "fail",
            "token",
            "the api does not recognize the token — "
            "/api/search answers as anonymous, so private-group annotations "
            "never arrive; make a new token at hypothes.is/account/developer",
        )
    if userid != user:
        return Check(
            "warn",
            "token",
            f"the token belongs to {userid}, but config.json "
            f"watches {user} — polls will see {user}'s public annotations only",
        )
    return Check("ok", "token", f"recognized by the api as {userid}")


def claude_signed_in(binary):
    """True or False per `claude auth status`, or None when the CLI cannot say.

    The subcommand reads the local login and makes no model call, so asking
    costs nothing. A CLI too old to have it, or one that will not start, is
    None rather than a failure: the binary check already passed.
    """
    try:
        proc = subprocess.run(
            [str(binary), "auth", "status", "--json"], capture_output=True, text=True, timeout=30
        )
        status = json.loads(proc.stdout)
        return bool(status["loggedIn"])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None


def check_claude(config):
    binary = config.get("claude_bin") or shutil.which("claude")
    if not (binary and Path(binary).exists()):
        return Check("fail", "claude cli", "not on PATH — classification would fall back to rules")
    signed_in = claude_signed_in(binary)
    if signed_in is False:
        return Check(
            "fail",
            "claude cli",
            f"{binary} is not signed in — run `claude` and sign in; "
            "the watcher holds new annotations unclassified until then",
        )
    if signed_in is None:
        return Check("ok", "claude cli", f"{binary} (sign-in state unknown)")
    return Check("ok", "claude cli", f"{binary}, signed in")  # never print the account


def run_checks(
    now=None,
    config=None,
    launch_agents=LAUNCH_AGENTS,
    systemd_dir=SYSTEMD_DIR,
    health_file=HEALTH_FILE,
    offline=False,
    fetch_profile=fetch_profile,
):
    now = now or datetime.now(timezone.utc)
    config = load_config() if config is None else config
    units = find_units(launch_agents, systemd_dir)
    max_age = interval_for(units) * MISSED_POLLS_ALLOWED
    token = [] if offline else [check_token(config, fetch_profile)]
    return [
        check_config(config),
        *token,
        *check_since(config),
        check_claude(config),
        *check_units(units),
        check_heartbeat(
            load_health(health_file), now, max_age, float(config.get("max_daily_usd", 0) or 0)
        ),
    ]


def exit_code(checks):
    return 1 if any(c.level == "fail" for c in checks) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--offline",
        action="store_true",
        help="skip the token check, the one check that needs the network",
    )
    args = ap.parse_args(argv)
    checks = run_checks(offline=args.offline)
    if args.json:
        print(json.dumps([c._asdict() for c in checks], indent=2))
    else:
        for check in checks:
            print(f"{MARKS[check.level]} {check.name}: {check.detail}")
    return exit_code(checks)


if __name__ == "__main__":
    raise SystemExit(main())
