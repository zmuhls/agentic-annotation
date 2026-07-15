#!/usr/bin/env python3
"""Rule-based initial sort of data/annotations.jsonl into the IA.

Writes architecture/map.jsonl (one record per annotation) and regenerates
architecture/overview.md with per-node counts. New annotations after this
initial pull are placed by Sonnet 5 in scripts/poll.py; this script is only
for the bulk backfill (safe to re-run — it rebuilds the map from scratch).
"""

import json
import urllib.parse
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

GROUP_NAMES = {
    "__world__": "Public",
    "R3qQqNk9": "2024-2025",
    "myPev4rD": "AI FIG | TLC 2024-25",
    "yKvGZkjg": "CSC10800 Annotation Group",
    "eBmn355k": "diss",
    "dWkEjnGy": "ENG 2100: Writing 1 (F23)",
    "6LxnJJoz": "ENG 2100: Writing 1 (S24)",
    "7AD9jqLR": "ENG2100: Writing 1 F20",
    "64Kvk7bx": "ENG2100: Writing 1 F21",
    "M4X9eV2X": "ENG2100: Writing 1 F22",
    "qqqKZmym": "ENG2150: Writing 2 S21",
    "vB9XvzV8": "ENG2150: Writing 2 S22",
    "D8yNabbj": "ENG2150: Writing 2 S23",
    "AK4RLLXQ": "ITP Core II",
    "r752WLJM": "JS Project",
    "wqjpVkmN": "Lesson Prep",
    "NyoW4wez": "Mandarin",
    "RQDYBPax": "N.B.",
    "9pzJABEb": "NYS Common Schools",
    "yxgzy8Br": "Programming",
    "3wR2dMiq": "T&L edits",
    "N2E9Mr3o": "TLC Social Reading Group",
    "vdyirjMa": "Toolkit Annotations",
    "EGMRqLQa": "zm-itp-is",
}

ARTIFACT_DOMAINS = {
    "zmuhls.github.io": "artifacts/personal-site",
    "localhost:4000": "artifacts/personal-site",
    "127.0.0.1:4000": "artifacts/personal-site",
    "cuny-ai-lab.github.io": "artifacts/cuny-ai-lab",
    "bot.inference-arcade.com": "artifacts/inference-arcade",
}

GROUP_NODES = {
    "eBmn355k": "dissertation/sources",
    "myPev4rD": "ai-pedagogy/fig",
    "vdyirjMa": "ai-pedagogy/toolkit",
    "N2E9Mr3o": "ai-pedagogy/fig",
    "yKvGZkjg": "teaching/csc10800",
    "dWkEjnGy": "teaching/writing-courses",
    "6LxnJJoz": "teaching/writing-courses",
    "7AD9jqLR": "teaching/writing-courses",
    "64Kvk7bx": "teaching/writing-courses",
    "M4X9eV2X": "teaching/writing-courses",
    "qqqKZmym": "teaching/writing-courses",
    "vB9XvzV8": "teaching/writing-courses",
    "D8yNabbj": "teaching/writing-courses",
    "wqjpVkmN": "teaching/prep",
    "AK4RLLXQ": "teaching/prep",
    "R3qQqNk9": "teaching/prep",
    "3wR2dMiq": "artifacts/other",
    "EGMRqLQa": "artifacts/other",
}

DH_DOMAINS = {
    "melaniewalsh.github.io", "tedunderwood.com", "crdh.rrchnm.org",
    "quod.lib.umich.edu", "data-feminism.mitpress.mit.edu",
    "abolition.university", "library.oapen.org", "dhdebates.gc.cuny.edu",
}
AIML_DOMAINS = {
    "arxiv.org", "www.anthropic.com", "openai.com", "huggingface.co",
    "www-nature-com.ezproxy.gc.cuny.edu", "www.nature.com",
    "criticaledtech.com",
}

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


def node_for(ann):
    domain = urllib.parse.urlparse(ann.get("uri", "")).netloc
    group = ann.get("group", "__world__")
    # Own artifacts win regardless of group: those are editorial notes-to-self.
    if domain in ARTIFACT_DOMAINS:
        return ARTIFACT_DOMAINS[domain]
    if group == "eBmn355k" and "reddit.com" in domain:
        return "dissertation/corpus"
    if group in GROUP_NODES:
        return GROUP_NODES[group]
    if "reddit.com" in domain:
        return "dissertation/corpus"
    if domain in DH_DOMAINS:
        return "reading/digital-humanities"
    if domain in AIML_DOMAINS:
        return "reading/ai-ml"
    if group in ("__world__", "RQDYBPax", "9pzJABEb", "yxgzy8Br", "NyoW4wez", "r752WLJM"):
        return "reading/general"
    return "inbox"


def quote_of(ann):
    for target in ann.get("target", []):
        for sel in target.get("selector", []) or []:
            if sel.get("type") == "TextQuoteSelector":
                return sel.get("exact", "")
    return ""


def record_for(ann):
    return {
        "id": ann["id"],
        "node": node_for(ann),
        "workflow": workflow_for(ann.get("tags", [])),
        "actions": actions_for(ann.get("tags", [])),
        "uri": ann.get("uri", ""),
        "title": (ann.get("document", {}).get("title") or [""])[0],
        "created": ann.get("created", ""),
        "updated": ann.get("updated", ""),
        "tags": ann.get("tags", []),
        "group": GROUP_NAMES.get(ann.get("group", ""), ann.get("group", "")),
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
    rows = [json.loads(l) for l in (ROOT / "data" / "annotations.jsonl").open()]
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
