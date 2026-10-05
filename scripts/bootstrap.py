#!/usr/bin/env python3
"""Draft architecture/ia.md and routing.json together, from one API pass.

bootstrap_ia.py and bootstrap_routing.py are two halves of one step, and they
only agree when run in that order: routing.json names nodes, and only the ia.md
on disk says which nodes exist. Run the second first, or skip the first, and
every group starts at `inbox`. This runs both from the same groups and the same
annotation sample, reads the routing's node ids off the ia.md it just drafted
rather than the one on disk, and writes either both files or neither — so the
preview already shows where each group will land.

    python3 scripts/bootstrap.py                    # preview the plan
    python3 scripts/bootstrap.py --write --force    # write ia.md and routing.json

architecture/ia.md always exists (it is the template), so writing needs
--force. The two scripts still work on their own for a full-text preview or for
redrafting one file after hand edits to the other.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap_ia  # noqa: E402
import bootstrap_routing  # noqa: E402
from appconfig import load_config  # noqa: E402

IA_FILE = bootstrap_ia.OUT
ROUTING_FILE = bootstrap_routing.OUT


def drafts(template_text, user, groups, annotations):
    """(ia.md text, routing dict) drafted from one fetch, the routing read off the new ia."""
    counts = bootstrap_ia.domains_by_group(annotations)
    ia_text = bootstrap_ia.draft(template_text, user, groups, counts)
    known = bootstrap_ia.node_ids(ia_text)
    return ia_text, bootstrap_routing.skeleton(groups, counts, known)


def summary(ia_text, routing):
    """Where each group and busy domain will land, one line apiece."""
    names = routing["group_names"]
    overrides = {}
    for o in routing["group_domain_overrides"]:
        overrides.setdefault(o["group"], []).append(o)
    placed = dict(routing["group_nodes"])
    for gid in routing["general_groups"]:
        placed[gid] = routing["general_node"]

    lines = [f"{IA_FILE.name}: {len(bootstrap_ia.node_ids(ia_text))} node(s)",
             f"{ROUTING_FILE.name}:"]
    for gid, node in placed.items():
        lines.append(f"  {names.get(gid, gid)} → {node}")
        lines += [f"    {o['domain_contains']} → {o['node']}" for o in overrides.get(gid, [])]
    unplaced = sum(n == "inbox" for n in routing["group_nodes"].values())
    lines.append(f"{unplaced} group(s) still at inbox")
    return lines


def main():
    config = load_config()
    token = bootstrap_ia.require_token(config)
    user = config.get("user", "")
    if not user:
        sys.exit("no user in config.json — set it to acct:<you>@hypothes.is")
    if not IA_FILE.exists():
        sys.exit(f"{IA_FILE} is missing — it is the template this script rewrites")
    write = "--write" in sys.argv
    # Both guards run before the API is asked anything, so a refusal never
    # leaves a new ia.md beside a routing.json drafted against the old one.
    if write and "--force" not in sys.argv:
        taken = [p.name for p in (IA_FILE, ROUTING_FILE) if p.exists()]
        sys.exit(f"{' and '.join(taken)} already exist(s) — pass --force to overwrite")

    groups = bootstrap_ia.get("profile/groups", token)
    annotations = bootstrap_ia.recent_annotations(token, user)
    ia_text, routing = drafts(IA_FILE.read_text(), user, groups, annotations)

    print("\n".join(summary(ia_text, routing)))
    if not write:
        print(f"\n# {len(groups)} group(s), {len(annotations)} annotation(s) sampled; "
              "re-run with --write --force to save both", file=sys.stderr)
        return
    IA_FILE.write_text(ia_text)
    ROUTING_FILE.write_text(json.dumps(routing, indent=2) + "\n")
    print(f"wrote {IA_FILE} and {ROUTING_FILE}; now edit each node's description in "
          "ia.md, prune what you do not want, and re-run bootstrap_routing.py "
          "--write --force if you rename nodes")


if __name__ == "__main__":
    main()
