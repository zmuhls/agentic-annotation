#!/usr/bin/env python3
"""Draft a routing.json from the adopter's own Hypothesis groups.

The placement tables in routing.json are per-person: only you know which of
your groups is coursework and which is dissertation reading. But the group ids
are not something anyone should have to copy out of the web UI by hand, so ask
the API for them (GET /api/profile/groups) and emit a draft with every group
named.

Run it after bootstrap_ia.py and the draft already agrees with your taxonomy:
it plans the same nodes that script drafted (one per group, busy domains as
children, public reading under `reading`) and points each group and busy domain
at its node, keeping only the ones architecture/ia.md actually defines. Run it
against an ia.md that is not yours and every group starts at `inbox` instead.

    python3 scripts/bootstrap_routing.py            # print to stdout
    python3 scripts/bootstrap_routing.py --write    # write ./routing.json

Refuses to clobber an existing routing.json unless --force is passed.
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bootstrap_ia  # noqa: E402
from appconfig import load_config  # noqa: E402

OUT = ROOT / "routing.json"
IA_FILE = ROOT / "architecture" / "ia.md"


def skeleton(groups, counts, known):
    """A routing.json for `groups`, naming only the node ids in `known`.

    `counts` is {group id: Counter(domain)} from the adopter's recent
    annotations; `known` is the set of node ids their ia.md defines.
    """
    def node(candidate):
        return candidate if candidate in known else "inbox"

    names, nodes, overrides = {"__world__": "Public"}, {}, []
    for entry in bootstrap_ia.plan(groups, counts):
        gid = entry["id"]
        names[gid] = entry["name"]
        nodes[gid] = node(f"{entry['slug']}/general")
        overrides += [{"group": gid, "domain_contains": domain, "node": child}
                      for domain, _, child in entry["children"] if child in known]
    public = bootstrap_ia.busy_domains(counts.get("__world__", Counter()), "reading")
    overrides += [{"group": "__world__", "domain_contains": domain, "node": child}
                  for domain, _, child in public if child in known]
    return {
        "_comment": "Drafted by scripts/bootstrap_routing.py from your groups, your "
                    "recent annotations, and the nodes in architecture/ia.md. "
                    "Anything ia.md did not define starts at 'inbox' — point it "
                    "at a real node. See routing.example.json for the full "
                    "schema and the order the tables are consulted in.",
        "group_names": names,
        "artifact_domains": {},
        "group_domain_overrides": overrides,
        "group_nodes": nodes,
        "domain_contains": {},
        "domain_nodes": {},
        "general_groups": ["__world__"],
        "general_node": node("reading/general"),
        "default_node": "inbox",
    }


def main():
    config = load_config()
    token = bootstrap_ia.require_token(config)

    groups = bootstrap_ia.get("profile/groups", token)
    # Without a user there is no sample to rank domains by; groups still route.
    user = config.get("user", "")
    annotations = bootstrap_ia.recent_annotations(token, user) if user else []
    known = bootstrap_ia.node_ids(IA_FILE.read_text()) if IA_FILE.exists() else set()
    routing = skeleton(groups, bootstrap_ia.domains_by_group(annotations), known)
    text = json.dumps(routing, indent=2) + "\n"

    unplaced = sum(n == "inbox" for n in routing["group_nodes"].values())
    if "--write" not in sys.argv:
        print(text, end="")
        print(f"\n# {len(groups)} group(s), {unplaced} still at inbox; "
              "re-run with --write to save to routing.json", file=sys.stderr)
        return
    if OUT.exists() and "--force" not in sys.argv:
        sys.exit(f"{OUT.name} already exists — pass --force to overwrite")
    OUT.write_text(text)
    print(f"wrote {OUT} with {len(groups)} group(s), {unplaced} still at inbox; "
          "point those at nodes in ia.md")


if __name__ == "__main__":
    main()
