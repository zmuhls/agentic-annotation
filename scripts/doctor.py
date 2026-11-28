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
auth status`, which spends nothing), the config keys poll.py needs, whether
the taxonomy is still the shipped example, whether every action tag it lists
can write a file, and whether the API still recognizes the token (one GET to
/api/profile; skip it with --offline).

    python3 scripts/doctor.py
    python3 scripts/doctor.py --offline   # no network: skip the token check
    python3 scripts/doctor.py --live      # also make one small billed claude call

`claude auth status` reads the login stored on this machine and nothing else, so
it can call a credential the API has since refused "signed in". --live settles
it the way the watcher would find out: one real call through poll.py's own code
path, a few cents at most. It is opt-in because it is the only check that costs
money.

Exits non-zero if anything is broken, so it can run from a cron/CI check.
"""

import argparse
import json
import plistlib
import subprocess
import sys
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from appconfig import (  # noqa: E402
    claude_bin,
    claude_env,
    config_credential,
    ia_source,
    load_config,
)
from bootstrap_ia import get as api_get  # noqa: E402
from build_ia import BUILTIN_ACTION_TAGS, directive_cells, vocabulary_tags  # noqa: E402

POLL_SCRIPT = ROOT / "scripts" / "poll.py"
HEALTH_FILE = ROOT / "data" / "health.json"
IA_FILE = ROOT / "architecture" / "ia.md"
LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"
SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
DEFAULT_INTERVAL = 300
# three missed polls: one laptop sleep is normal, three in a row is not
MISSED_POLLS_ALLOWED = 3
# A hold only a person can clear (a dead token, a signed-out CLI) that has
# outlived a day is broken, not a blip. Without this a token hold read "warn"
# for three weeks, and `--offline`, which skips the token check, exited 0.
HOLD_DAYS_ALLOWED = 1

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


def _hold_start(health):
    """The `held_since` poll.py records for a hold that needs a person, or None.

    Absent for a fault that clears itself (a wifi drop, the daily ceiling) and
    from heartbeats written before the field existed; both stay warnings.
    """
    try:
        began = datetime.fromisoformat(health.get("held_since") or "")
    except (TypeError, ValueError):
        return None
    return began if began.tzinfo else began.replace(tzinfo=timezone.utc)


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
        began = _hold_start(health)
        stuck = began is not None and now - began >= timedelta(days=HOLD_DAYS_ALLOWED)
        return Check(
            "fail" if stuck else "warn",
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


def check_taxonomy(ia_file=IA_FILE):
    """Flag a watcher classifying against the shipped example; say nothing
    when the adopter's own ia.md is in place."""
    if ia_file.exists():
        return []
    example = ia_source(ia_file)
    if example.exists():
        return [
            Check(
                "warn",
                "taxonomy",
                f"no {ia_file.name} yet, so the classifier reads {example.name}, a "
                "sample taxonomy — draft your own with scripts/bootstrap.py --write",
            )
        ]
    return [
        Check(
            "fail",
            "taxonomy",
            f"neither {ia_file.name} nor {example.name} exists in {ia_file.parent} — "
            "every classification will fail; restore the example with git checkout",
        )
    ]


def check_action_tags(ia_file=IA_FILE):
    """Flag action-vocabulary rows that will write no file; say nothing when
    every row works.

    build_ia.py takes its action tags from the `| Tag | Directive |` tables of
    the taxonomy the classifier reads. A row it cannot use, or a taxonomy with
    no such table, fails quietly: the tag is simply never acted on.
    """
    source = ia_source(ia_file)
    if not source.exists():
        return []  # check_taxonomy already fails this
    text = source.read_text()
    tags = vocabulary_tags(text)
    if not tags:
        return [
            Check(
                "warn",
                "action tags",
                f"{source.name} has no usable row in a table headed `| Tag | Directive |`, "
                f"so only the {len(BUILTIN_ACTION_TAGS)} built-in action tags write files",
            )
        ]
    unusable = [cell for cell in directive_cells(text) if cell.lower() not in tags]
    if unusable:
        return [
            Check(
                "warn",
                "action tags",
                f"no file is written for {', '.join(f'`{c}`' for c in unusable)} in "
                f"{source.name}: an action tag must be a plain slug (letters, digits, "
                "- or _) and not a status tag",
            )
        ]
    return []


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


def claude_signed_in(binary, env=None):
    """True or False per `claude auth status`, or None when the CLI cannot say.

    The subcommand reads the local login and makes no model call, so asking
    costs nothing. A CLI too old to have it, or one that will not start, is
    None rather than a failure: the binary check already passed. `env` is the
    environment the watcher gives the CLI, so the login asked about is its own.
    """
    try:
        proc = subprocess.run(
            [str(binary), "auth", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        status = json.loads(proc.stdout)
        return bool(status["loggedIn"])
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None


def check_claude(config):
    if config.get("model") == "rules":
        return Check("ok", "claude cli", 'not needed: config.json sets "model": "rules"')
    if config.get("claude_env") is not None and not isinstance(config["claude_env"], dict):
        return Check(
            "fail",
            "claude cli",
            'claude_env in config.json must be an object of "NAME": "value" pairs; '
            "the watcher ignores it until it is",
        )
    binary = claude_bin(config)
    if not Path(binary).exists():
        return Check(
            "fail",
            "claude cli",
            f"not found at {binary} — the watcher holds new annotations until it is "
            'installed; set claude_bin in config.json, or "model": "rules" to run without it',
        )
    signed_in = claude_signed_in(binary, claude_env(config))
    if signed_in is False:
        return Check(
            "fail",
            "claude cli",
            f"{binary} is not signed in — run `claude` and sign in; "
            "the watcher holds new annotations unclassified until then",
        )
    if signed_in is None:
        return Check("ok", "claude cli", f"{binary} (sign-in state unknown)")
    credential = config_credential(config)
    via = f" with {credential} from config.json" if credential else ""
    return Check("ok", "claude cli", f"{binary}, signed in{via}")  # never print the account


# Small on purpose: the call is billed by the token, and all it has to prove is
# that the CLI can reach a model with the login the watcher gives it.
LIVE_PROMPT = 'Respond with ONLY this JSON object and nothing else: {"ok": true}'


def call_classifier(prompt, meta):
    """One real call through the watcher's own path (poll.call_sonnet).

    Imported here, not at the top: poll.py is the watcher itself, and only
    --live needs it. A single attempt, since a health check should report a
    failure rather than wait out poll.py's 30-second retry.
    """
    import poll

    return poll.call_sonnet(prompt, attempts=1, meta=meta)


def check_claude_live(config, call=call_classifier):
    """Make one billed call and say whether the classifier answered.

    Says nothing when there is no call to make: `"model": "rules"` never runs
    the CLI, and a missing binary has already failed check_claude.
    """
    if config.get("model") == "rules" or not Path(claude_bin(config)).exists():
        return []
    meta = {}
    try:
        call(LIVE_PROMPT, meta)
    except ValueError:
        pass  # it answered, just not in JSON: the login works, which is the question
    except Exception as e:  # auth, a CLI that will not start, a timeout, an API outage
        return [Check("fail", "claude live", f"a real call failed: {e}"[:300])]
    cost = meta.get("cost_usd")
    spent = f" (${cost:.4f})" if isinstance(cost, (int, float)) else ""
    return [Check("ok", "claude live", f"a real call was answered{spent}")]


def run_checks(
    now=None,
    config=None,
    launch_agents=LAUNCH_AGENTS,
    systemd_dir=SYSTEMD_DIR,
    health_file=HEALTH_FILE,
    ia_file=IA_FILE,
    offline=False,
    fetch_profile=fetch_profile,
    live=False,
    live_call=call_classifier,
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
        *check_taxonomy(ia_file),
        *check_action_tags(ia_file),
        check_claude(config),
        *(check_claude_live(config, live_call) if live else []),
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
    ap.add_argument(
        "--live",
        action="store_true",
        help="also make one small billed claude call, to test the login for real",
    )
    args = ap.parse_args(argv)
    if args.live and args.offline:
        ap.error("--live makes a network call, so it cannot be combined with --offline")
    checks = run_checks(offline=args.offline, live=args.live)
    if args.json:
        print(json.dumps([c._asdict() for c in checks], indent=2))
    else:
        for check in checks:
            print(f"{MARKS[check.level]} {check.name}: {check.detail}")
    return exit_code(checks)


if __name__ == "__main__":
    raise SystemExit(main())
