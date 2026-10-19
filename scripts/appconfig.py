#!/usr/bin/env python3
"""Config loading shared by poll.py and build_ia.py.

Two files, split by what they hold. `config.json` carries the API token and the
account to watch; `routing.json` carries the personal placement tables (group
ids, own-artifact domains) that used to be literals in build_ia.py. Both are
gitignored — this repo is public — and both fall back to a committed `.example`
so a fresh clone, the test suite, and CI can import these modules without any
local setup.
"""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Where Claude Code's native installer puts the CLI. launchd starts jobs with a
# bare PATH that rarely includes it, so PATH alone misses a working install.
DEFAULT_CLAUDE_BIN = Path.home() / ".local" / "bin" / "claude"


def load_json_with_example(name):
    """Read `<name>.json`, else the committed `<name>.example.json`, else {}."""
    for candidate in (f"{name}.json", f"{name}.example.json"):
        path = ROOT / candidate
        if path.exists():
            return json.loads(path.read_text())
    return {}


def load_config():
    return load_json_with_example("config")


def load_routing():
    return load_json_with_example("routing")


def claude_bin(config):
    """The claude CLI the watcher runs: `claude_bin` from config, else PATH,
    else the installer's default. One answer for poll.py and doctor.py, so the
    health check never fails a binary the watcher would find."""
    return config.get("claude_bin") or shutil.which("claude") or str(DEFAULT_CLAUDE_BIN)
