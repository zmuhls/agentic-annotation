#!/usr/bin/env python3
"""Incremental Hypothesis watcher + Claude Sonnet 5 classifier.

Hypothesis has no webhooks, so this polls /api/search on a cursor over the
`updated` timestamp (new annotations AND tag edits to old ones re-trigger).
Each new/updated annotation is sent to Claude Sonnet 5 (headless `claude -p`),
which places it in the information architecture (architecture/ia.md) and,
when the annotation carries a revision / expansion / condense tag, writes
concrete instructions for the target artifact into actions/.

Run by launchd every 5 minutes (see launchd/com.zachmuhlbauer.hypothesis-watcher.plist).
Manual run: python3 scripts/poll.py [--dry-run]
"""

import fcntl
import json
import shutil
import subprocess
import sys
import time
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_ia import (  # noqa: E402
    ACTION_TAGS, GROUP_NAMES, actions_for, node_for, quote_of, record_for,
    title_of, write_overview,
)

def load_config():
    # Adopters (and the test suite / CI) clone without the private config.json;
    # fall back to the committed example so imports never hard-fail on setup.
    for name in ("config.json", "config.example.json"):
        path = ROOT / name
        if path.exists():
            return json.loads(path.read_text())
    return {}


CONFIG = load_config()
API = "https://api.hypothes.is/api"
MODEL = CONFIG.get("model", "claude-sonnet-5")

CURSOR_FILE = ROOT / "data" / "cursor.json"
SEEN_FILE = ROOT / "data" / "seen.json"
MAP_FILE = ROOT / "architecture" / "map.jsonl"
IA_FILE = ROOT / "architecture" / "ia.md"
EMERGENT_FILE = ROOT / "architecture" / "emergent-nodes.md"
ACTIONS_DIR = ROOT / "actions"
LOG_FILE = ROOT / "logs" / "watcher.log"
LOCK_FILE = ROOT / "data" / ".poll.lock"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a") as f:
        f.write(f"[{stamp}] {msg}\n")
    print(msg)


def search(params):
    url = f"{API}/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {CONFIG['api_token']}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_new(cursor):
    rows, search_after = [], cursor
    while True:
        page = search({
            "user": CONFIG["user"],
            "sort": "updated",
            "order": "asc",
            "search_after": search_after,
            "limit": 200,
        })
        batch = page.get("rows", [])
        if not batch:
            return rows
        rows.extend(batch)
        search_after = batch[-1]["updated"]


def claude_bin():
    return CONFIG.get("claude_bin") or shutil.which("claude") \
        or str(Path.home() / ".local" / "bin" / "claude")


def siblings_at(node, exclude_id, limit=6):
    """Compact context: recent annotations already mapped to the same node."""
    if not MAP_FILE.exists():
        return []
    records = [json.loads(l) for l in MAP_FILE.open()]
    sibs = [r for r in records if r["node"] == node and r["id"] != exclude_id]
    sibs.sort(key=lambda r: r.get("created", ""), reverse=True)
    return [{
        "title": r.get("title") or r.get("uri", ""),
        "gist": (r.get("role") or r.get("note") or r.get("quote") or "")[:120],
    } for r in sibs[:limit]]


def classify_prompt(ann):
    ia = IA_FILE.read_text()
    group = GROUP_NAMES.get(ann.get("group", ""), ann.get("group", ""))
    predicted = node_for(ann)
    payload = {
        "uri": ann.get("uri", ""),
        "title": title_of(ann),
        "group": group,
        "tags": ann.get("tags", []),
        "quoted_passage": quote_of(ann)[:600],
        "annotation_note": (ann.get("text") or "")[:2000],
        "created": ann.get("created", ""),
        "is_reply": bool(ann.get("references")),
    }
    action_tags = actions_for(ann.get("tags", []))
    return f"""You are the annotation librarian for Zach Muhlbauer's Hypothesis knowledge system. His information architecture is below, followed by one new annotation.

<information_architecture>
{ia}
</information_architecture>

<annotation>
{json.dumps(payload, indent=2)}
</annotation>

<neighbors note="recent annotations already living at the rule-predicted node '{predicted}'">
{json.dumps(siblings_at(predicted, ann.get("id")), indent=2)}
</neighbors>

Do three things:

1. Assign the annotation to exactly one node. Prefer an existing node id from the architecture. You may propose one new child under an existing node (e.g. "dissertation/sources/platform-studies") when a cluster clearly deserves it; set "new_node" true in that case. Use "inbox" only as a last resort.

2. In one sentence, state the annotation's role within the broader architecture — what it contributes to or connects with at that node.

3. This annotation carries these action tags: {json.dumps(action_tags)}. For EACH action tag, produce one action object honoring that tag's directive as defined in the Action vocabulary section of the architecture. Instructions must be concrete and executable — anchored to the quoted passage, faithful to the note's intent, specific about what to do (for `synthesize`, draw on the neighbors above). If the list of action tags is empty, "actions" is an empty list.

Respond with ONLY a JSON object (no markdown fences, no commentary):
{{"node": "<node-id>", "new_node": false, "role": "<one sentence>", "actions": [{{"type": "<the action tag>", "artifact": "<uri>", "anchor": "<quoted passage or location>", "instructions": "<what to do>"}}]}}"""


def call_sonnet(prompt, attempts=2):
    proc = None
    for attempt in range(attempts):
        proc = subprocess.run(
            [claude_bin(), "-p", "--model", MODEL, "--output-format", "json"],
            input=prompt, capture_output=True, text=True, timeout=600,
        )
        if proc.returncode == 0:
            break
        if attempt < attempts - 1:
            time.sleep(30)  # transient API outages are common enough to ride out
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[:400]}")
    try:
        wrapper = json.loads(proc.stdout)
    except json.JSONDecodeError:
        wrapper = None
    if isinstance(wrapper, dict):
        result = wrapper.get("result", "")
    elif isinstance(wrapper, list):
        # some CLI versions emit a list of message objects ending in a result
        result = next((m.get("result", "") for m in reversed(wrapper)
                       if isinstance(m, dict) and m.get("type") == "result"), "")
    else:
        result = proc.stdout
    start, end = result.find("{"), result.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON in model output: {result[:200]}")
    return json.loads(result[start:end + 1])


def upsert_map(record):
    records = []
    if MAP_FILE.exists():
        records = [json.loads(l) for l in MAP_FILE.open()]
    records = [r for r in records if r["id"] != record["id"]] + [record]
    with MAP_FILE.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return records


def write_action_file(ann, action):
    ACTIONS_DIR.mkdir(exist_ok=True)
    date = ann.get("updated", "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = ACTIONS_DIR / f"{date}-{action['type']}-{ann['id']}.md"
    title = title_of(ann)
    path.write_text(f"""# {action['type'].capitalize()}: {title or ann.get('uri', '')}

- **artifact**: {action.get('artifact', ann.get('uri', ''))}
- **annotation**: {ann.get('links', {}).get('incontext', '')}
- **tagged**: {', '.join(ann.get('tags', []))}
- **created**: {ann.get('created', '')}

## Anchor

> {action.get('anchor', quote_of(ann))}

## Annotation note

{ann.get('text') or '(no note)'}

## Instructions

{action.get('instructions', '')}
""")
    return path


def note_emergent(node, role, ann):
    if not EMERGENT_FILE.exists():
        EMERGENT_FILE.write_text("# Emergent nodes proposed by Sonnet (review, then fold into ia.md)\n\n")
    with EMERGENT_FILE.open("a") as f:
        f.write(f"- `{node}` — {role} (from {ann.get('links', {}).get('incontext', ann['id'])})\n")


def process(ann, dry_run=False):
    wanted = actions_for(ann.get("tags", []))
    record = record_for(ann)  # rules-based baseline record
    actions = []
    try:
        result = call_sonnet(classify_prompt(ann))
        record["node"] = result.get("node") or record["node"]
        record["role"] = result.get("role", "")
        record["classified_by"] = MODEL
        actions = result.get("actions") or []
        if isinstance(actions, dict):  # tolerate a bare single object
            actions = [actions]
        legacy = result.get("action")  # pre-vocabulary contract
        if legacy and not actions:
            actions = [legacy]
        if result.get("new_node") and not dry_run:
            note_emergent(record["node"], record.get("role", ""), ann)
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        where = f" at {tb[-1].filename.split('/')[-1]}:{tb[-1].lineno}" if tb else ""
        log(f"  sonnet failed for {ann['id']}: {type(e).__name__}: {e}{where}"
            "; falling back to rules")
        record["classified_by"] = "rules-fallback"
    # every tagged action produces a file: stub any the model missed
    produced = {a.get("type") for a in actions}
    for tag in wanted:
        if tag not in produced:
            actions.append({
                "type": tag,
                "artifact": ann.get("uri", ""),
                "anchor": quote_of(ann),
                "instructions": "(model produced no instructions — act on the annotation note directly)",
            })
    actions = [a for a in actions if a.get("type") in wanted]  # tags drive files
    if dry_run:
        print(json.dumps({**record, "pending_actions": actions}, indent=2))
        return record
    upsert_map(record)
    for action in actions:
        path = write_action_file(ann, action)
        log(f"  action file: {path.name}")
    log(f"  {ann['id']} -> {record['node']}"
        f"{' [' + ','.join(wanted) + ']' if wanted else ''}")
    return record


def main():
    dry_run = "--dry-run" in sys.argv
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock = LOCK_FILE.open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return  # previous run still going

    cursor = json.loads(CURSOR_FILE.read_text())["search_after"] \
        if CURSOR_FILE.exists() else CONFIG.get("since")
    seen = json.loads(SEEN_FILE.read_text()) if SEEN_FILE.exists() else {}

    anns = fetch_new(cursor)
    fresh = [a for a in anns if seen.get(a["id"]) != a["updated"]]
    if not fresh:
        return
    log(f"processing {len(fresh)} new/updated annotation(s) with {MODEL}")
    for ann in fresh:
        process(ann, dry_run=dry_run)
        if not dry_run:
            seen[ann["id"]] = ann["updated"]
            SEEN_FILE.write_text(json.dumps(seen))
            CURSOR_FILE.write_text(json.dumps({"search_after": ann["updated"]}))
    if not dry_run and MAP_FILE.exists():
        write_overview([json.loads(l) for l in MAP_FILE.open()])


if __name__ == "__main__":
    main()
