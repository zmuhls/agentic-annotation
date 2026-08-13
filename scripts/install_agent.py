#!/usr/bin/env python3
"""Generate the scheduler unit that runs poll.py every few minutes.

The committed launchd plist used to carry one person's absolute paths, python
interpreter, and reverse-dns label — unusable by anyone else and the last piece
of the maintainer's machine left in a public repo. This writes the unit instead,
from the checkout you are standing in: macOS launchd, Linux systemd user timer,
or a crontab line for anything else.

    python3 scripts/install_agent.py              # print the unit, install nothing
    python3 scripts/install_agent.py --write      # install it and print how to load
    python3 scripts/install_agent.py --target systemd --interval 600
"""

import argparse
import os
import plistlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LABEL = "local.hypothesis-watcher"
DEFAULT_INTERVAL = 300


def launchd_plist(label, python, interval):
    """launchd wants an absolute PATH: agents inherit almost no environment."""
    path_entries = [str(Path(python).parent), "/usr/local/bin", "/usr/bin", "/bin",
                    str(Path.home() / ".local" / "bin")]
    seen, path = set(), []
    for entry in path_entries:
        if entry not in seen:
            seen.add(entry)
            path.append(entry)
    plist = {
        "Label": label,
        "ProgramArguments": [python, str(ROOT / "scripts" / "poll.py")],
        "WorkingDirectory": str(ROOT),
        "StartInterval": interval,
        "RunAtLoad": True,
        "EnvironmentVariables": {"PATH": ":".join(path)},
        "StandardOutPath": str(ROOT / "logs" / "launchd.log"),
        "StandardErrorPath": str(ROOT / "logs" / "launchd.log"),
        "ProcessType": "Background",
    }
    return plistlib.dumps(plist).decode()


def systemd_units(label, python, interval):
    """A .service that runs once plus a .timer that fires it on an interval."""
    service = f"""[Unit]
Description=Hypothesis annotation watcher

[Service]
Type=oneshot
WorkingDirectory={ROOT}
ExecStart={python} {ROOT / "scripts" / "poll.py"}
Environment=PATH={Path(python).parent}:{Path.home() / ".local" / "bin"}:/usr/local/bin:/usr/bin:/bin
StandardOutput=append:{ROOT / "logs" / "launchd.log"}
StandardError=append:{ROOT / "logs" / "launchd.log"}
"""
    timer = f"""[Unit]
Description=Run the Hypothesis annotation watcher every {interval}s

[Timer]
OnBootSec={interval}s
OnUnitActiveSec={interval}s
AccuracySec=30s
Unit={label}.service

[Install]
WantedBy=timers.target
"""
    return {f"{label}.service": service, f"{label}.timer": timer}


def cron_line(python, interval):
    minutes = max(1, interval // 60)
    step = f"*/{minutes}" if minutes < 60 else "0"
    return (f"{step} * * * * cd {ROOT} && {python} scripts/poll.py "
            f">> {ROOT / 'logs' / 'launchd.log'} 2>&1\n")


def default_target():
    return {"darwin": "launchd", "linux": "systemd"}.get(sys.platform, "cron")


def write_file(path, text, force):
    if path.exists() and not force:
        raise SystemExit(f"{path} exists — re-run with --force to overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=("launchd", "systemd", "cron"),
                    default=default_target())
    ap.add_argument("--label", default=os.environ.get("WATCHER_LABEL", DEFAULT_LABEL),
                    help=f"unit name / launchd label (default {DEFAULT_LABEL})")
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter to run poll.py with (default: this one)")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                    help="seconds between polls (default 300)")
    ap.add_argument("--write", action="store_true", help="install, don't just print")
    ap.add_argument("--force", action="store_true", help="overwrite an existing unit")
    args = ap.parse_args(argv)

    label, python, interval = args.label, args.python, args.interval

    if args.target == "launchd":
        text = launchd_plist(label, python, interval)
        if not args.write:
            print(text, end="")
            return 0
        dest = write_file(Path.home() / "Library" / "LaunchAgents" / f"{label}.plist",
                          text, args.force)
        print(f"wrote {dest}\n\nload it:\n  launchctl load {dest}\n"
              f"\nlater, to pause:\n  launchctl unload {dest}")
    elif args.target == "systemd":
        units = systemd_units(label, python, interval)
        if not args.write:
            for name, text in units.items():
                print(f"# ---- {name} ----\n{text}")
            return 0
        base = Path.home() / ".config" / "systemd" / "user"
        for name, text in units.items():
            print(f"wrote {write_file(base / name, text, args.force)}")
        print(f"\nenable it:\n  systemctl --user daemon-reload\n"
              f"  systemctl --user enable --now {label}.timer\n"
              f"  systemctl --user list-timers {label}.timer")
    else:
        line = cron_line(python, interval)
        print(line, end="")
        if args.write:
            print("\nadd it with `crontab -e` — this script will not edit your "
                  "crontab for you.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
