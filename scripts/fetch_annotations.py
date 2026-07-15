#!/usr/bin/env python3
"""Full pull of Hypothesis annotations for the configured user.

Paginates /api/search with search_after on created (ascending) and writes
one annotation per line to data/annotations.jsonl. Safe to re-run: it
overwrites the file with a fresh complete pull.
"""

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text())

API = "https://api.hypothes.is/api"
TOKEN = CONFIG["api_token"]
USER = CONFIG["user"]
SINCE = CONFIG.get("since", "2024-07-15T00:00:00.000000+00:00")
OUT = ROOT / "data" / "annotations.jsonl"


def search(params):
    url = f"{API}/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    search_after = SINCE
    while True:
        page = search({
            "user": USER,
            "sort": "created",
            "order": "asc",
            "search_after": search_after,
            "limit": 200,
        })
        batch = page.get("rows", [])
        if not batch:
            break
        rows.extend(batch)
        search_after = batch[-1]["created"]
        print(f"fetched {len(rows)} (through {search_after})", file=sys.stderr)

    with OUT.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} annotations to {OUT}")


if __name__ == "__main__":
    main()
