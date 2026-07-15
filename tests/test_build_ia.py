"""Tests for the rule-based helpers in build_ia.py.

These lock in the shape-robustness fixes: the Hypothesis API hands back
malformed / half-populated annotations (e.g. `document` as an empty list for
freshly-created ones), and none of the pure extractors may crash on them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from build_ia import (  # noqa: E402
    actions_for, node_for, quote_of, record_for, title_of, workflow_for,
)


class TestTitleOf:
    def test_normal_document(self):
        assert title_of({"document": {"title": ["Hello"]}}) == "Hello"

    def test_document_empty_list(self):
        # the exact shape that crashed the classifier on freshly-created anns
        assert title_of({"document": []}) == ""

    def test_document_missing(self):
        assert title_of({}) == ""

    def test_document_none(self):
        assert title_of({"document": None}) == ""

    def test_document_without_title(self):
        assert title_of({"document": {}}) == ""

    def test_title_empty_list(self):
        assert title_of({"document": {"title": []}}) == ""


class TestQuoteOf:
    def test_normal_quote_selector(self):
        ann = {"target": [{"selector": [
            {"type": "TextQuoteSelector", "exact": "the passage"}]}]}
        assert quote_of(ann) == "the passage"

    def test_no_target(self):
        assert quote_of({}) == ""

    def test_target_none(self):
        assert quote_of({"target": None}) == ""

    def test_target_element_not_dict(self):
        assert quote_of({"target": [["bad"]]}) == ""

    def test_selector_is_dict_not_list(self):
        assert quote_of({"target": [{"selector": {"type": "x"}}]}) == ""

    def test_selector_element_not_dict(self):
        assert quote_of({"target": [{"selector": ["nope"]}]}) == ""

    def test_no_matching_selector_type(self):
        ann = {"target": [{"selector": [{"type": "RangeSelector"}]}]}
        assert quote_of(ann) == ""


class TestActionsFor:
    def test_matches_known_tags(self):
        assert actions_for(["revision", "cite", "random"]) == ["revision", "cite"]

    def test_case_insensitive(self):
        assert actions_for(["REVISION"]) == ["revision"]

    def test_preserves_vocabulary_order(self):
        # ACTION_TAGS order, not input order
        assert actions_for(["cite", "revision"]) == ["revision", "cite"]

    def test_empty(self):
        assert actions_for([]) == []


class TestWorkflowFor:
    def test_outstanding(self):
        assert workflow_for(["outstanding"]) == "outstanding"

    def test_resolved(self):
        assert workflow_for(["Resolved"]) == "resolved"

    def test_none(self):
        assert workflow_for(["revision"]) is None


class TestNodeFor:
    def test_own_artifact_wins_over_group(self):
        ann = {"uri": "https://zmuhls.github.io/x", "group": "eBmn355k"}
        assert node_for(ann) == "artifacts/personal-site"

    def test_diss_group_reddit_goes_to_corpus(self):
        ann = {"uri": "https://reddit.com/r/x", "group": "eBmn355k"}
        assert node_for(ann) == "dissertation/corpus"

    def test_group_node_mapping(self):
        assert node_for({"uri": "https://example.com", "group": "vdyirjMa"}) \
            == "ai-pedagogy/toolkit"

    def test_unknown_falls_to_inbox(self):
        assert node_for({"uri": "https://example.com", "group": "ZZZ"}) == "inbox"

    def test_missing_uri_and_group(self):
        assert node_for({}) == "reading/general"  # __world__ default


class TestRecordFor:
    def test_freshly_created_annotation_does_not_crash(self):
        # document=[], no target, no tags — the mid-creation shape
        rec = record_for({
            "id": "abc", "document": [], "tags": [], "target": [],
            "uri": "https://zmuhls.github.io/x",
        })
        assert rec["id"] == "abc"
        assert rec["title"] == ""
        assert rec["node"] == "artifacts/personal-site"
        assert rec["classified_by"] == "rules"
