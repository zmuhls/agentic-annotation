"""Tests for the rule-based helpers in build_ia.py.

These lock in the shape-robustness fixes: the Hypothesis API hands back
malformed / half-populated annotations (e.g. `document` as an empty list for
freshly-created ones), and none of the pure extractors may crash on them.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_ia  # noqa: E402
from build_ia import (  # noqa: E402
    actions_for,
    group_name_for,
    node_for,
    quote_of,
    record_for,
    title_of,
    workflow_for,
)

# the `routing` fixture (fictional placement tables) comes from conftest.py


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
        ann = {"target": [{"selector": [{"type": "TextQuoteSelector", "exact": "the passage"}]}]}
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


@pytest.mark.usefixtures("routing")
class TestNodeFor:
    def test_own_artifact_wins_over_group(self):
        ann = {"uri": "https://mysite.example/x", "group": "DISS01"}
        assert node_for(ann) == "artifacts/personal-site"

    def test_group_domain_override_beats_group_node(self):
        ann = {"uri": "https://forum.example/r/x", "group": "DISS01"}
        assert node_for(ann) == "dissertation/corpus"

    def test_group_node_mapping(self):
        assert (
            node_for({"uri": "https://elsewhere.example", "group": "DISS01"})
            == "dissertation/sources"
        )

    def test_domain_contains_applies_without_a_group_rule(self):
        assert (
            node_for({"uri": "https://forum.example/r/x", "group": "ZZZ"}) == "dissertation/corpus"
        )

    def test_exact_domain_mapping(self):
        assert node_for({"uri": "https://papers.example/2401", "group": "ZZZ"}) == "reading/ai-ml"

    def test_general_group(self):
        assert (
            node_for({"uri": "https://elsewhere.example", "group": "MISC01"}) == "reading/general"
        )

    def test_unknown_falls_to_default_node(self):
        assert node_for({"uri": "https://elsewhere.example", "group": "ZZZ"}) == "inbox"

    def test_missing_uri_and_group(self):
        assert node_for({}) == "reading/general"  # __world__ default


class TestRoutingDefaults:
    def test_empty_routing_sends_everything_to_the_default_node(self, monkeypatch):
        # a clone with no routing.json at all must still classify, not crash
        for name in (
            "ARTIFACT_DOMAINS",
            "GROUP_NODES",
            "DOMAIN_CONTAINS",
            "DOMAIN_NODES",
            "GROUP_NAMES",
        ):
            monkeypatch.setattr(build_ia, name, {})
        monkeypatch.setattr(build_ia, "GROUP_DOMAIN_OVERRIDES", [])
        monkeypatch.setattr(build_ia, "GENERAL_GROUPS", frozenset())
        assert node_for({"uri": "https://anything.example", "group": "G"}) == "inbox"

    def test_routing_file_on_disk_parses(self):
        # routing.json locally, routing.example.json on a fresh clone / in CI
        from appconfig import load_json_with_example

        routing = load_json_with_example("routing")
        assert routing["default_node"]
        assert isinstance(routing["group_names"], dict)


@pytest.mark.usefixtures("routing")
class TestGroupNameFor:
    def test_known_group(self):
        assert group_name_for({"group": "DISS01"}) == "diss"

    def test_unknown_group_falls_back_to_the_id(self):
        assert group_name_for({"group": "ZZZ"}) == "ZZZ"

    def test_missing_group(self):
        assert group_name_for({}) == ""


@pytest.mark.usefixtures("routing")
class TestRecordFor:
    def test_freshly_created_annotation_does_not_crash(self):
        # document=[], no target, no tags — the mid-creation shape
        rec = record_for(
            {
                "id": "abc",
                "document": [],
                "tags": [],
                "target": [],
                "uri": "https://mysite.example/x",
            }
        )
        assert rec["id"] == "abc"
        assert rec["title"] == ""
        assert rec["node"] == "artifacts/personal-site"
        assert rec["classified_by"] == "rules"
