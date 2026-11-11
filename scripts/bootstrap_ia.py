#!/usr/bin/env python3
"""Draft an architecture/ia.md from the adopter's own annotation history.

`ia.md` is the one file a new adopter cannot copy from this repo: it is the
taxonomy the classifier reads on every poll, and the version committed here
describes one person's groups, sites, and projects. Written from scratch it is
an hour of staring at a blank page; written from your own history it is an
edit pass. So ask the API which groups you belong to (GET /api/profile/groups)
and where you actually annotate (GET /api/search), and emit a nodes section
with one top-level node per group, its busiest domains as children, and the
public layer folded into `reading`.

The cross-cutting half of the file — the action-tag vocabulary that `poll.py`
and `build_ia.py` both implement — is not personal, so it is carried over from
the existing ia.md verbatim rather than restated here.

    python3 scripts/bootstrap_ia.py            # print to stdout
    python3 scripts/bootstrap_ia.py --write    # write ./architecture/ia.md

Refuses to clobber an existing ia.md unless --force is passed.
"""

import http.client
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from appconfig import load_config  # noqa: E402

API = "https://api.hypothes.is/api"
OUT = ROOT / "architecture" / "ia.md"

NODES_HEADING = "## Nodes"
SHARED_TAIL_HEADING = "## Action vocabulary"
# Enough history to see which domains matter without paging: the sample only
# has to rank a person's sites, not enumerate them.
SAMPLE_LIMIT = 200
# A domain earns its own child node once it is more than a stray one-off.
DOMAIN_MIN_HITS = 2
DOMAIN_CHILDREN = 3
TOKEN_REMEDY = "make a new token at hypothes.is/account/developer"


def require_token(config):
    """The configured API token, or exit before any call if it is still a placeholder."""
    token = config.get("api_token", "")
    if not token or token.startswith("YOUR-"):
        sys.exit("no api_token in config.json — copy config.example.json first")
    return token


def require_recognized(token):
    """Exit unless the API knows whose `token` this is.

    /api/profile/groups and /api/search never say: a token the API does not
    recognize gets the anonymous answer — the public group alone, public rows
    only — so a draft built from them has no group nodes and still looks
    finished. /api/profile does: `userid` is null for anonymous.
    """
    if get("profile", token).get("userid") is None:
        sys.exit(
            f"the hypothesis api does not recognize the token in config.json — "
            f"{TOKEN_REMEDY}; nothing drafted"
        )


class ApiReplyError(OSError):
    """A reply that did not come back whole from the api: not JSON, or cut off.

    A wifi sign-in page or a proxy can answer 200 with HTML, and a dropped link
    can cut a body short (http.client.IncompleteRead). Neither is an OSError, so
    both skipped every network handler. The poll ended in a traceback with an
    "error" heartbeat, and the bootstrap scripts ended in a traceback too. As an
    OSError it is retried and reported like the network drop it usually is.
    """

    def __init__(self, endpoint, problem):
        super().__init__(f"{endpoint}: {problem}")


def get(path, token, **params):
    url = f"{API}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    endpoint = f"/api/{path}"
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
    except OSError:
        raise  # HTTPError, URLError, and RemoteDisconnected (also an HTTPException)
    except http.client.HTTPException as e:
        raise ApiReplyError(endpoint, f"reply cut off or garbled ({type(e).__name__})") from e
    try:
        return json.loads(body.decode())
    except ValueError:  # JSONDecodeError and UnicodeDecodeError both are
        raise ApiReplyError(
            endpoint, "reply was not JSON; a wifi sign-in page or a proxy may have answered"
        ) from None


def api_reason(err):
    """`err`'s status, plus the reason the api put in the error body.

    A bare "400 Bad Request" says nothing about which value the api refused,
    but the body names it — an unreadable `since`, for one, comes back as
    "search_after must be a parsable date..." (probed live). Bodies that are
    missing or not JSON leave just the status.
    """
    status = f"{err.code} {err.reason}"
    try:
        reason = json.loads(err.read().decode()).get("reason") or ""
        reason = " ".join(reason.lstrip(": ").split())
    except Exception:  # an HTTPError with no body raises KeyError from read() on 3.9
        return status
    return f"{status}: {reason}" if reason else status


@contextmanager
def api_or_exit(untouched):
    """Turn a failed API call into one line that says what was left alone.

    A dropped DNS lookup or a 5xx otherwise ends the script in a urllib
    traceback that never says whether ia.md, routing.json, or annotations.jsonl
    was touched. Callers fetch everything before they write anything, so
    `untouched` can always say what was left as it was.
    """
    try:
        yield
    except urllib.error.HTTPError as e:  # a URLError/OSError subclass — catch first
        sys.exit(f"hypothesis api returned {api_reason(e)}; {untouched}")
    except OSError as e:
        sys.exit(f"hypothesis api unreachable ({e}); {untouched}")


def recent_annotations(token, user):
    """The adopter's most recent annotations, enough to rank where they annotate."""
    return get("search", token, user=user, sort="updated", order="desc", limit=SAMPLE_LIMIT).get(
        "rows", []
    )


def slugify(text, fallback="group"):
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:40].strip("-") or fallback


def domain_of(ann):
    return urllib.parse.urlparse(ann.get("uri", "")).netloc.lower().removeprefix("www.")


def domains_by_group(annotations):
    """{group id: Counter(domain)} over the sampled annotations."""
    counts = {}
    for ann in annotations:
        domain = domain_of(ann)
        if not domain:
            continue  # local files and PDFs without a URI tell us nothing
        counts.setdefault(ann.get("group", "__world__"), Counter())[domain] += 1
    return counts


def _unique(slug, taken):
    candidate, n = slug, 2
    while candidate in taken:
        candidate, n = f"{slug}-{n}", n + 1
    taken.add(candidate)
    return candidate


def busy_domains(seen, parent):
    """[(domain, hits, node id)] for the domains that earn a child of `parent`."""
    children = []
    for domain, hits in seen.most_common(DOMAIN_CHILDREN):
        if hits < DOMAIN_MIN_HITS:
            break
        children.append((domain, hits, f"{parent}/{slugify(domain, 'site')}"))
    return children


def plan(groups, counts):
    """The drafted group nodes as data, before they are rendered as markdown.

    One entry per group, the public layer excluded (it becomes `reading`).
    `nodes_section` renders this, and bootstrap_routing.py reads it to point
    each group and busy domain at the node drafted for it.
    """
    entries, taken = [], {"inbox", "reading"}
    for group in sorted(groups, key=lambda g: g.get("name", "")):
        gid = group.get("id")
        if not gid or gid == "__world__":
            continue
        name = group.get("name") or gid
        slug = _unique(slugify(name), taken)
        seen = counts.get(gid, Counter())
        entries.append(
            {
                "id": gid,
                "name": name,
                "slug": slug,
                "total": sum(seen.values()),
                "children": busy_domains(seen, slug),
            }
        )
    return entries


def nodes_section(groups, counts):
    """The one section of ia.md that is nobody else's to write."""
    lines = [NODES_HEADING, ""]
    for entry in plan(groups, counts):
        slug, name = entry["slug"], entry["name"]
        lines.append(f"### {slug} — {name}")
        lines.append(
            f'Annotations in the "{name}" group ({entry["total"]} in a sample of the '
            f"{SAMPLE_LIMIT} most recent). Replace this line with what the group "
            "is actually for — the classifier reads it."
        )
        for domain, hits, node in entry["children"]:
            lines.append(f"- `{node}` — {domain} ({hits})")
        lines.append(f"- `{slug}/general` — anything in this group the children above miss")
        lines.append("")

    lines.append("### reading — public-layer annotation, outside any group")
    lines.append("Reading not tied to a project above.")
    for domain, hits, node in busy_domains(counts.get("__world__", Counter()), "reading"):
        lines.append(f"- `{node}` — {domain} ({hits})")
    lines.append("- `reading/general` — everything else worth keeping")
    lines.append("")
    lines.append("### inbox — unplaced")
    lines.append("Holding node when no rule or classification fits; reviewed periodically.")
    lines.append("")
    return "\n".join(lines)


def nodes_of(text):
    """The nodes section of an ia.md, or '' if it has none.

    Only this section defines nodes; the shared tail has headings and
    backticked bullets of its own (tag groups, the file map) that are not nodes.
    """
    _, sep, rest = text.partition(NODES_HEADING)
    return rest.split(SHARED_TAIL_HEADING, 1)[0] if sep else ""


def node_ids(text):
    """Every node id an ia.md defines: its `### ` headings and `- `id`` children."""
    section = nodes_of(text)
    return set(re.findall(r"^### (\S+)", section, re.MULTILINE)) | set(
        re.findall(r"^- `([^`]+)`", section, re.MULTILINE)
    )


def split_template(text):
    """(preamble, shared tail) of an existing ia.md — everything but the nodes.

    The tail is the action vocabulary and the file map: the same contract for
    every adopter, because poll.py and build_ia.py implement it in code.
    """
    head, sep, rest = text.partition(NODES_HEADING)
    if not sep:
        raise ValueError(f"no '{NODES_HEADING}' heading in {OUT.name}")
    marker = rest.find(SHARED_TAIL_HEADING)
    if marker == -1:
        raise ValueError(f"no '{SHARED_TAIL_HEADING}' heading in {OUT.name}")
    return head, rest[marker:]


def first_child(section):
    """The first `group/child` node id the draft defines, for use as an example."""
    match = re.search(r"^- `([^`]+)`", section, re.MULTILINE)
    return match.group(1) if match else None


def draft(template_text, user, groups, counts):
    preamble, tail = split_template(template_text)
    section = nodes_section(groups, counts)
    # The committed preamble is about the schema and stays as written, except
    # for the two places it can only speak for its author: the account it
    # watches, and the node it reaches for as an example. Both would read as
    # someone else's taxonomy in a file meant to become yours.
    preamble = re.sub(r"`acct:[^`]*`", f"`{user}`", preamble)
    example = first_child(section)
    if example:
        preamble = re.sub(r"\(e\.g\. `[^`]+`\)", f"(e.g. `{example}/<child>`)", preamble, count=1)
    return preamble + section + tail


def main():
    config = load_config()
    token = require_token(config)
    user = config.get("user", "")
    if not user:
        sys.exit("no user in config.json — set it to acct:<you>@hypothes.is")

    if not OUT.exists():
        sys.exit(f"{OUT} is missing — it is the template this script rewrites")
    template_text = OUT.read_text()

    with api_or_exit("nothing drafted"):
        require_recognized(token)
        groups = get("profile/groups", token)
        annotations = recent_annotations(token, user)
    text = draft(template_text, user, groups, domains_by_group(annotations))

    if "--write" not in sys.argv:
        print(text, end="")
        print(
            f"\n# {len(groups)} group(s), {len(annotations)} annotation(s) sampled; "
            "re-run with --write --force to save to architecture/ia.md",
            file=sys.stderr,
        )
        return
    if "--force" not in sys.argv:
        sys.exit(f"{OUT.name} already exists — pass --force to overwrite")
    OUT.write_text(text)
    print(
        f"wrote {OUT} from {len(groups)} group(s); now edit each node's "
        "description and prune what you do not want"
    )


if __name__ == "__main__":
    main()
