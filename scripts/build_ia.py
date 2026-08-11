#!/usr/bin/env python3
"""Rule-based initial sort of data/annotations.jsonl into the IA.

Writes architecture/map.jsonl (one record per annotation) and regenerates
architecture/overview.md with per-node counts. New annotations after this
initial pull are placed by Sonnet 5 in scripts/poll.py; this script is only
for the bulk backfill (safe to re-run — it rebuilds the map from scratch).
"""

import json
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from appconfig import load_routing  # noqa: E402

# Placement tables live in routing.json (gitignored — group ids and the sites
# you annotate are personal), with routing.example.json as the documented
# fallback so a fresh clone still imports. See node_for() for precedence.
ROUTING = load_routing()
GROUP_NAMES = ROUTING.get("group_names", {})
ARTIFACT_DOMAINS = ROUTING.get("artifact_domains", {})
GROUP_DOMAIN_OVERRIDES = ROUTING.get("group_domain_overrides", [])
GROUP_NODES = ROUTING.get("group_nodes", {})
DOMAIN_CONTAINS = ROUTING.get("domain_contains", {})
DOMAIN_NODES = ROUTING.get("domain_nodes", {})
GENERAL_GROUPS = frozenset(ROUTING.get("general_groups", ()))
GENERAL_NODE = ROUTING.get("general_node", "reading/general")
DEFAULT_NODE = ROUTING.get("default_node", "inbox")

ACTION_TAGS = (
    # prose & argument
    "revision", "expansion", "condense", "restructure", "hedge",
    "reframe", "exemplify", "counter", "define",
    # research & evidence
    "cite", "evidence", "verify", "question", "synthesize",
    # development objects
    "bug", "feature", "a11y",
)
STATUS_TAGS = ("outstanding", "resolved")


def workflow_for(tags):
    lower = [t.lower() for t in tags]
    for w in STATUS_TAGS:
        if w in lower:
            return w
    return None


def actions_for(tags):
    lower = [t.lower() for t in tags]
    return [a for a in ACTION_TAGS if a in lower]


def group_name_for(ann):
    group = ann.get("group", "")
    return GROUP_NAMES.get(group, group)


def node_for(ann):
    """Rule-based prior for an annotation's node; Sonnet may override it.

    First match wins, table by table (see routing.example.json for the schema).
    """
    domain = urllib.parse.urlparse(ann.get("uri", "")).netloc
    group = ann.get("group", "__world__")
    # Own artifacts win regardless of group: those are editorial notes-to-self.
    if domain in ARTIFACT_DOMAINS:
        return ARTIFACT_DOMAINS[domain]
    # A group whose node depends on where the annotation lives (e.g. corpus
    # material read on one site vs. secondary sources read anywhere else).
    for rule in GROUP_DOMAIN_OVERRIDES:
        if rule.get("group") == group and rule.get("domain_contains", "") in domain:
            return rule["node"]
    if group in GROUP_NODES:
        return GROUP_NODES[group]
    for fragment, node in DOMAIN_CONTAINS.items():
        if fragment in domain:
            return node
    if domain in DOMAIN_NODES:
        return DOMAIN_NODES[domain]
    if group in GENERAL_GROUPS:
        return GENERAL_NODE
    return DEFAULT_NODE


def title_of(ann):
    # The API returns `document` as an empty list for annotations caught mid-
    # creation (before metadata populates), so coerce anything non-dict away.
    doc = ann.get("document")
    doc = doc if isinstance(doc, dict) else {}
    return (doc.get("title") or [""])[0]


def quote_of(ann):
    for target in ann.get("target", []) or []:
        if not isinstance(target, dict):
            continue
        for sel in target.get("selector", []) or []:
            if isinstance(sel, dict) and sel.get("type") == "TextQuoteSelector":
                return sel.get("exact", "")
    return ""


def record_for(ann):
    return {
        "id": ann["id"],
        "node": node_for(ann),
        "workflow": workflow_for(ann.get("tags", [])),
        "actions": actions_for(ann.get("tags", [])),
        "uri": ann.get("uri", ""),
        "title": title_of(ann),
        "created": ann.get("created", ""),
        "updated": ann.get("updated", ""),
        "tags": ann.get("tags", []),
        "group": group_name_for(ann),
        "quote": quote_of(ann)[:300],
        "note": (ann.get("text") or "")[:500],
        "link": ann.get("links", {}).get("incontext", ""),
        "classified_by": "rules",
    }


def write_overview(records):
    counts = Counter(r["node"] for r in records)
    workflows = Counter(r["workflow"] for r in records if r["workflow"])
    lines = [
        "# IA Overview (generated — do not hand-edit)",
        "",
        f"Total annotations mapped: {len(records)}",
        "",
        "## Annotations per node",
        "",
    ]
    for node, count in sorted(counts.items()):
        lines.append(f"- `{node}`: {count}")
    lines += ["", "## Workflow statuses", ""]
    for w, count in workflows.most_common():
        lines.append(f"- `{w}`: {count}")
    action_counts = Counter(a for r in records for a in r.get("actions", []))
    if action_counts:
        lines += ["", "## Action tags", ""]
        for a, count in action_counts.most_common():
            lines.append(f"- `{a}`: {count}")
    lines.append("")
    (ROOT / "architecture" / "overview.md").write_text("\n".join(lines))


def main():
    rows = [json.loads(line) for line in (ROOT / "data" / "annotations.jsonl").open()]
    records = [record_for(r) for r in rows]
    out = ROOT / "architecture" / "map.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    write_overview(records)
    print(f"mapped {len(records)} annotations -> {out}")
    for node, count in sorted(Counter(r['node'] for r in records).items()):
        print(f"  {count:4d}  {node}")


if __name__ == "__main__":
    main()
