"""Tests for the starter-taxonomy drafter.

The Hypothesis API is always mocked: these tests never reach the network and
never read the maintainer's real groups.
"""

import sys
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
