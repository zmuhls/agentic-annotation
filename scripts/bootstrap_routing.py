#!/usr/bin/env python3
"""Draft a routing.json from the adopter's own Hypothesis groups.

The placement tables in routing.json are per-person: only you know which of
your groups is coursework and which is dissertation reading. But the group ids
are not something anyone should have to copy out of the web UI by hand, so ask
the API for them (GET /api/profile/groups) and emit a skeleton with every group
named and mapped to `inbox`, ready to edit.

    python3 scripts/bootstrap_routing.py            # print to stdout
    python3 scripts/bootstrap_routing.py --write    # write ./routing.json

Refuses to clobber an existing routing.json unless --force is passed.
"""

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from appconfig import load_config  # noqa: E402

API = "https://api.hypothes.is/api"
OUT = ROOT / "routing.json"


def fetch_groups(token):
    req = urllib.request.Request(
        f"{API}/profile/groups", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def skeleton(groups):
    names, nodes = {"__world__": "Public"}, {}
    for g in groups:
        gid = g.get("id")
        if not gid or gid == "__world__":
            continue
        names[gid] = g.get("name", gid)
        nodes[gid] = "inbox"  # edit: point each group at a node from ia.md
    return {
        "_comment": "Drafted by scripts/bootstrap_routing.py. Every group starts "
                    "at 'inbox' — replace those with node ids from "
                    "architecture/ia.md. See routing.example.json for the full "
                    "schema and the order the tables are consulted in.",
        "group_names": names,
        "artifact_domains": {},
        "group_domain_overrides": [],
        "group_nodes": nodes,
        "domain_contains": {},
        "domain_nodes": {},
        "general_groups": ["__world__"],
        "general_node": "reading/general",
        "default_node": "inbox",
    }


def main():
    config = load_config()
    token = config.get("api_token", "")
    if not token or token.startswith("YOUR-"):
        sys.exit("no api_token in config.json — copy config.example.json first")

    groups = fetch_groups(token)
    text = json.dumps(skeleton(groups), indent=2) + "\n"

    if "--write" not in sys.argv:
        print(text, end="")
        print(f"\n# {len(groups)} group(s); re-run with --write to save to routing.json",
              file=sys.stderr)
        return
    if OUT.exists() and "--force" not in sys.argv:
        sys.exit(f"{OUT.name} already exists — pass --force to overwrite")
    OUT.write_text(text)
    print(f"wrote {OUT} with {len(groups)} group(s); now map each to a node in ia.md")


if __name__ == "__main__":
    main()
