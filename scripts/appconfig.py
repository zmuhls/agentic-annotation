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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
