"""Tests for the starter-taxonomy drafter.

The Hypothesis API is always mocked: these tests never reach the network and
never read the maintainer's real groups.
"""

import http.client
import sys
import urllib.error
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import bootstrap_ia  # noqa: E402

TEMPLATE = """# Hypothesis Annotation Information Architecture

Taxonomy for all annotations by `acct:someone@hypothes.is`. Every annotation
is assigned one **node**.

## Nodes

### artifacts — someone else's nodes
- `artifacts/personal-site` — not yours

## Action vocabulary (from tags, cross-cutting)

| Tag        | Directive |
|------------|-----------|
| `revision` | Rework the anchored prose |

## Files

- `architecture/map.jsonl` — one line per annotation
"""

GROUPS = [
    {"id": "__world__", "name": "Public"},
    {"id": "DISS01", "name": "Diss Reading"},
    {"id": "TEACH1", "name": "ENG 2100 / Fall"},
]

ANNOTATIONS = [
    {"group": "DISS01", "uri": "https://www.forum.example/a"},
    {"group": "DISS01", "uri": "https://forum.example/b"},
    {"group": "DISS01", "uri": "https://papers.example/c"},  # single hit: no node
    {"group": "__world__", "uri": "https://news.example/d"},
    {"group": "__world__", "uri": "https://news.example/e"},
    {"group": "TEACH1", "uri": ""},  # no uri (local pdf) — contributes nothing
]


class TestSlugify:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("ENG 2100 / Fall", "eng-2100-fall"),
            ("  Diss Reading  ", "diss-reading"),
            ("forum.example", "forum-example"),
            ("", "group"),
            ("!!!", "group"),
        ],
    )
    def test_slugs(self, raw, expected):
        assert bootstrap_ia.slugify(raw) == expected

    def test_truncates_without_a_trailing_dash(self):
        slug = bootstrap_ia.slugify("x" * 39 + " tail")
        assert len(slug) <= 40 and not slug.endswith("-")


class TestDomainCounts:
    def test_counts_per_group_and_strips_www(self):
        counts = bootstrap_ia.domains_by_group(ANNOTATIONS)
        assert counts["DISS01"] == Counter({"forum.example": 2, "papers.example": 1})
        assert counts["__world__"] == Counter({"news.example": 2})

    def test_annotations_without_a_uri_are_skipped(self):
        assert "TEACH1" not in bootstrap_ia.domains_by_group(ANNOTATIONS)


class TestNodesSection:
    @pytest.fixture
    def section(self):
        return bootstrap_ia.nodes_section(GROUPS, bootstrap_ia.domains_by_group(ANNOTATIONS))

    def test_one_top_level_node_per_group_except_public(self, section):
        assert "### diss-reading — Diss Reading" in section
        assert "### eng-2100-fall — ENG 2100 / Fall" in section
        assert "### Public" not in section

    def test_busy_domains_become_children(self, section):
        assert "- `diss-reading/forum-example` — forum.example (2)" in section
        assert "papers.example" not in section  # one hit is not a node

    def test_every_group_keeps_a_general_child(self, section):
        assert "- `diss-reading/general`" in section
        assert "- `eng-2100-fall/general`" in section

    def test_public_layer_becomes_reading(self, section):
        assert "- `reading/news-example` — news.example (2)" in section
        assert "- `reading/general`" in section

    def test_inbox_is_always_present(self, section):
        assert "### inbox — unplaced" in section

    def test_colliding_group_names_get_distinct_slugs(self):
        section = bootstrap_ia.nodes_section(
            [{"id": "A", "name": "Reading"}, {"id": "B", "name": "reading!"}], {}
        )
        assert "### reading-2 —" in section
        assert "### reading-3 —" in section  # `reading` itself is reserved


class TestDraft:
    @pytest.fixture
    def text(self):
        return bootstrap_ia.draft(
            TEMPLATE, "acct:new@hypothes.is", GROUPS, bootstrap_ia.domains_by_group(ANNOTATIONS)
        )

    def test_carries_the_shared_vocabulary_through_verbatim(self, text):
        assert "| `revision` | Rework the anchored prose |" in text
        assert "## Files" in text

    def test_rewrites_the_account_and_drops_foreign_nodes(self, text):
        assert "`acct:new@hypothes.is`" in text
        assert "someone@hypothes.is" not in text
        assert "artifacts/personal-site" not in text

    def test_keeps_the_section_order(self, text):
        assert text.index("## Nodes") < text.index("## Action vocabulary")

    @pytest.mark.parametrize(
        "broken",
        [
            "# no nodes heading\n\n## Action vocabulary\n",
            "# no vocabulary\n\n## Nodes\n\n### a — b\n",
        ],
    )
    def test_refuses_a_template_missing_either_marker(self, broken):
        with pytest.raises(ValueError):
            bootstrap_ia.draft(broken, "acct:new@hypothes.is", GROUPS, {})


class TestExampleNode:
    """The preamble's example node has to come from the adopter's own draft.

    Left alone it names a node out of the maintainer's taxonomy, in the one
    file the classifier reads as the authority on which nodes exist.
    """

    def test_the_example_is_rewritten_to_a_generated_node(self):
        template = TEMPLATE.replace(
            "is assigned one **node**.",
            "is assigned one **node** (e.g. `dissertation/corpus/transfer`).",
        )
        text = bootstrap_ia.draft(
            template, "acct:new@hypothes.is", GROUPS, bootstrap_ia.domains_by_group(ANNOTATIONS)
        )
        assert "dissertation/corpus" not in text
        assert "(e.g. `diss-reading/forum-example/<child>`)" in text

    def test_a_preamble_without_an_example_is_left_alone(self):
        text = bootstrap_ia.draft(TEMPLATE, "acct:new@hypothes.is", GROUPS, {})
        assert "e.g." not in text.partition("## Nodes")[0]

    def test_first_child_is_none_when_nothing_has_children(self):
        assert bootstrap_ia.first_child("### a — b\n\nno list here\n") is None


class TestMain:
    """main() asks /api/profile whose token this is before it drafts anything.

    /api/profile/groups and /api/search answer a token they do not recognize as
    anonymous — the public group alone, public rows only — so the draft would
    hold no group nodes and still look finished.
    """

    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        calls, owner, fail = [], {"userid": "acct:new@hypothes.is"}, {}

        def fake_get(path, token, **params):
            calls.append(path)
            if path in fail:
                raise fail[path]
            if path == "profile":
                return owner
            if path == "profile/groups":
                return GROUPS
            if path == "search":
                return {"rows": ANNOTATIONS}
            raise AssertionError(f"unexpected API call: {path}")

        ia = tmp_path / "ia.md"
        ia.write_text(TEMPLATE)
        monkeypatch.setattr(bootstrap_ia, "get", fake_get)
        monkeypatch.setattr(bootstrap_ia, "OUT", ia)
        monkeypatch.setattr(
            bootstrap_ia,
            "load_config",
            lambda: {"api_token": "test-token", "user": "acct:new@hypothes.is"},
        )
        monkeypatch.setattr(sys, "argv", ["bootstrap_ia.py", "--write", "--force"])
        return {"calls": calls, "owner": owner, "fail": fail, "ia": ia}

    def test_a_recognized_token_drafts_from_the_groups(self, env):
        bootstrap_ia.main()
        assert env["calls"] == ["profile", "profile/groups", "search"]
        assert "### diss-reading — Diss Reading" in env["ia"].read_text()

    def test_an_unrecognized_token_exits_before_drafting(self, env):
        env["owner"]["userid"] = None
        with pytest.raises(SystemExit) as exit_:
            bootstrap_ia.main()
        assert "does not recognize the token" in str(exit_.value)
        assert env["calls"] == ["profile"]
        assert env["ia"].read_text() == TEMPLATE

    def test_a_placeholder_token_exits_before_any_call(self, env, monkeypatch):
        monkeypatch.setattr(bootstrap_ia, "load_config", lambda: {"api_token": "YOUR-TOKEN"})
        with pytest.raises(SystemExit):
            bootstrap_ia.main()
        assert env["calls"] == []

    @pytest.mark.parametrize("path", ["profile", "profile/groups", "search"])
    def test_an_unreachable_api_exits_in_one_line(self, env, path):
        env["fail"][path] = urllib.error.URLError("nodename nor servname provided")
        with pytest.raises(SystemExit) as exit_:
            bootstrap_ia.main()
        assert str(exit_.value).startswith("hypothesis api unreachable")
        assert str(exit_.value).endswith("nothing drafted")
        assert env["ia"].read_text() == TEMPLATE

    def test_a_reply_that_is_not_json_exits_in_one_line(self, env):
        env["fail"]["profile/groups"] = bootstrap_ia.ApiReplyError(
            "/api/profile/groups", "not JSON"
        )
        with pytest.raises(SystemExit) as exit_:
            bootstrap_ia.main()
        assert str(exit_.value).startswith("hypothesis api unreachable")
        assert "/api/profile/groups" in str(exit_.value)
        assert env["ia"].read_text() == TEMPLATE

    def test_an_api_error_names_the_status(self, env):
        env["fail"]["profile/groups"] = urllib.error.HTTPError("u", 503, "Unavailable", {}, None)
        with pytest.raises(SystemExit, match="hypothesis api returned 503 Unavailable"):
            bootstrap_ia.main()
        assert env["ia"].read_text() == TEMPLATE


class TestGet:
    """get() is the one place every script reads an api reply."""

    class _Resp:
        def __init__(self, body):
            self._body = body

        def read(self):
            if isinstance(self._body, Exception):
                raise self._body
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _serve(self, monkeypatch, body):
        resp = self._Resp(body)
        monkeypatch.setattr(bootstrap_ia.urllib.request, "urlopen", lambda req, timeout=None: resp)

    def test_parses_a_json_reply(self, monkeypatch):
        self._serve(monkeypatch, b'{"userid": "acct:a@hypothes.is"}')
        assert bootstrap_ia.get("profile", "t") == {"userid": "acct:a@hypothes.is"}

    @pytest.mark.parametrize(
        "body",
        [
            b"<html><body>Sign in to the wifi</body></html>",  # a captive portal's 200
            b"",
            b"\xff\xfe not utf-8",
        ],
    )
    def test_a_reply_that_is_not_json_names_the_endpoint(self, monkeypatch, body):
        self._serve(monkeypatch, body)
        with pytest.raises(bootstrap_ia.ApiReplyError, match="/api/search.*not JSON"):
            bootstrap_ia.get("search", "t", limit=1)

    def test_a_cut_off_reply_names_the_endpoint(self, monkeypatch):
        self._serve(monkeypatch, http.client.IncompleteRead(b'{"ro', 100))
        with pytest.raises(bootstrap_ia.ApiReplyError, match="/api/profile.*cut off"):
            bootstrap_ia.get("profile", "t")

    def test_the_error_is_an_oserror_so_network_handlers_catch_it(self):
        assert issubclass(bootstrap_ia.ApiReplyError, OSError)
