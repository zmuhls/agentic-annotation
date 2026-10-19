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
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Where Claude Code's native installer puts the CLI. launchd starts jobs with a
# bare PATH that rarely includes it, so PATH alone misses a working install.
DEFAULT_CLAUDE_BIN = Path.home() / ".local" / "bin" / "claude"
# Variables that carry a login of their own. The CLI prefers any of them to the
# login `claude` stores after an interactive sign-in.
CREDENTIAL_VARS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


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


def claude_env(config):
    """The environment the claude CLI runs in: this process's, plus the
    `claude_env` object from config.json.

    A scheduler starts the watcher with almost no environment, so a credential
    exported in a shell profile never reaches the CLI there, and the login an
    interactive sign-in stores has to keep refreshing itself: the watcher's
    lapsed on 2026-08-13, 10-16 and 10-18, and each time classification
    stopped until someone signed in again. `claude_env` is where a sturdier login goes: the
    long-lived token `claude setup-token` prints, as CLAUDE_CODE_OAUTH_TOKEN, or
    an API key or a provider's variables. A value that is not an object is
    ignored here and failed by doctor.py.
    """
    env = dict(os.environ)
    extra = config.get("claude_env")
    if isinstance(extra, dict):
        # subprocess refuses non-string values outright, failing every call
        env.update({str(k): str(v) for k, v in extra.items() if v is not None})
    return env


def config_credential(config):
    """The credential variable `claude_env` sets, or None. When there is one, a
    refused login is that credential's fault, and signing in again fixes nothing."""
    extra = config.get("claude_env")
    if not isinstance(extra, dict):
        return None
    return next((name for name in CREDENTIAL_VARS if extra.get(name)), None)
