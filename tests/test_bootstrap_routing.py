"""Tests for the routing.json drafter.

The Hypothesis API is always mocked: these tests never reach the network and
never read the maintainer's real groups or taxonomy. The groups, sample, and
ia.md template are the ones the ia.md drafter is tested against, so the two
bootstrappers are checked against each other, not just each on its own terms.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import bootstrap_ia  # noqa: E402
import bootstrap_routing  # noqa: E402
import build_ia  # noqa: E402
from test_bootstrap_ia import ANNOTATIONS, GROUPS, TEMPLATE  # noqa: E402

COUNTS = bootstrap_ia.domains_by_group(ANNOTATIONS)
DRAFT = bootstrap_ia.draft(TEMPLATE, "acct:new@hypothes.is", GROUPS, COUNTS)
KNOWN = bootstrap_ia.node_ids(DRAFT)


class TestNodeIds:
    def test_reads_headings_and_children_from_the_nodes_section(self):
        assert {
            "diss-reading",
            "diss-reading/forum-example",
            "diss-reading/general",
            "eng-2100-fall/general",
            "reading/news-example",
            "reading/general",
            "inbox",
        } <= KNOWN

    def test_the_shared_tail_defines_no_nodes(self):
        assert "architecture/map.jsonl" not in KNOWN
        assert "revision" not in KNOWN

    def test_reads_a_hand_written_taxonomy_too(self):
        text = (
            "## Nodes\n\n### artifacts — notes on your own work\n\n"
            "- `artifacts/site` — a site\n\n## Action vocabulary\n"
        )
        assert bootstrap_ia.node_ids(text) == {"artifacts", "artifacts/site"}

    def test_a_file_without_a_nodes_section_defines_nothing(self):
        assert bootstrap_ia.node_ids("# nothing here\n") == set()


class TestSkeleton:
    @pytest.fixture
    def drafted(self):
        return bootstrap_routing.skeleton(GROUPS, COUNTS, KNOWN)

    def test_names_every_group(self, drafted):
        assert drafted["group_names"] == {
            "__world__": "Public",
            "DISS01": "Diss Reading",
            "TEACH1": "ENG 2100 / Fall",
        }

    def test_each_group_points_at_its_drafted_general_node(self, drafted):
        assert drafted["group_nodes"] == {
            "DISS01": "diss-reading/general",
            "TEACH1": "eng-2100-fall/general",
        }

    def test_busy_domains_route_to_their_child_nodes(self, drafted):
        assert drafted["group_domain_overrides"] == [
            {
                "group": "DISS01",
                "domain_contains": "forum.example",
                "node": "diss-reading/forum-example",
            },
            {
                "group": "__world__",
                "domain_contains": "news.example",
                "node": "reading/news-example",
            },
        ]

    def test_names_only_nodes_the_taxonomy_defines(self, drafted):
        named = (
            set(drafted["group_nodes"].values())
            | {rule["node"] for rule in drafted["group_domain_overrides"]}
            | {drafted["general_node"], drafted["default_node"]}
        )
        assert named <= KNOWN

    def test_falls_back_to_inbox_against_someone_elses_taxonomy(self):
        # bootstrap_ia.py never ran: ia.md still holds the template's nodes
        drafted = bootstrap_routing.skeleton(GROUPS, COUNTS, bootstrap_ia.node_ids(TEMPLATE))
        assert set(drafted["group_nodes"].values()) == {"inbox"}
        assert drafted["group_domain_overrides"] == []
        assert drafted["general_node"] == "inbox"

    def test_groups_still_route_without_a_sample(self):
        drafted = bootstrap_routing.skeleton(GROUPS, {}, KNOWN)
        assert drafted["group_nodes"]["DISS01"] == "diss-reading/general"
        assert drafted["group_domain_overrides"] == []


class TestDraftRoutesThroughNodeFor:
    """A draft is only worth writing if build_ia reads it the way it was meant."""

    @pytest.fixture(autouse=True)
    def load_draft(self, monkeypatch):
        drafted = bootstrap_routing.skeleton(GROUPS, COUNTS, KNOWN)
        for key, value in drafted.items():
            if key.startswith("_"):
                continue
            if key == "general_groups":
                value = frozenset(value)
            monkeypatch.setattr(build_ia, key.upper(), value)

    @pytest.mark.parametrize(
        "ann, node",
        [
            (
                {"group": "DISS01", "uri": "https://www.forum.example/a"},
                "diss-reading/forum-example",
            ),
            ({"group": "DISS01", "uri": "https://papers.example/c"}, "diss-reading/general"),
            ({"group": "TEACH1", "uri": ""}, "eng-2100-fall/general"),
            ({"group": "__world__", "uri": "https://news.example/d"}, "reading/news-example"),
            ({"group": "__world__", "uri": "https://elsewhere.example/"}, "reading/general"),
            ({"group": "JOINED1", "uri": "https://elsewhere.example/"}, "inbox"),
        ],
    )
    def test_node_for(self, ann, node):
        assert build_ia.node_for(ann) == node


class TestMain:
    @pytest.fixture
    def env(self, tmp_path, monkeypatch):
        calls = []

        def fake_get(path, token, **params):
            calls.append(path)
            if path == "profile/groups":
                return GROUPS
            if path == "search":
                return {"rows": ANNOTATIONS}
            raise AssertionError(f"unexpected API call: {path}")

        ia = tmp_path / "ia.md"
        ia.write_text(DRAFT)
        monkeypatch.setattr(bootstrap_ia, "get", fake_get)
        monkeypatch.setattr(bootstrap_routing, "IA_FILE", ia)
        monkeypatch.setattr(bootstrap_routing, "OUT", tmp_path / "routing.json")
        monkeypatch.setattr(
            bootstrap_routing,
            "load_config",
            lambda: {"api_token": "test-token", "user": "acct:new@hypothes.is"},
        )
        monkeypatch.setattr(sys, "argv", ["bootstrap_routing.py", "--write"])
        return {"calls": calls, "out": tmp_path / "routing.json", "ia": ia}

    def test_writes_a_routing_that_agrees_with_the_ia_on_disk(self, env):
        bootstrap_routing.main()
        written = json.loads(env["out"].read_text())
        assert written["group_nodes"]["DISS01"] == "diss-reading/general"
        assert env["calls"] == ["profile/groups", "search"]

    def test_a_missing_ia_routes_everything_to_inbox(self, env):
        env["ia"].unlink()
        bootstrap_routing.main()
        written = json.loads(env["out"].read_text())
        assert set(written["group_nodes"].values()) == {"inbox"}

    def test_without_a_user_the_sample_is_skipped(self, env, monkeypatch):
        monkeypatch.setattr(bootstrap_routing, "load_config", lambda: {"api_token": "test-token"})
        bootstrap_routing.main()
        assert env["calls"] == ["profile/groups"]
        assert json.loads(env["out"].read_text())["group_domain_overrides"] == []

    def test_refuses_to_clobber_without_force(self, env):
        env["out"].write_text("{}\n")
        with pytest.raises(SystemExit):
            bootstrap_routing.main()
        assert env["out"].read_text() == "{}\n"

    def test_preview_prints_and_writes_nothing(self, env, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["bootstrap_routing.py"])
        bootstrap_routing.main()
        assert '"group_nodes"' in capsys.readouterr().out
        assert not env["out"].exists()

    def test_a_placeholder_token_exits_before_any_call(self, env, monkeypatch):
        monkeypatch.setattr(bootstrap_routing, "load_config", lambda: {"api_token": "YOUR-TOKEN"})
        with pytest.raises(SystemExit):
            bootstrap_routing.main()
        assert env["calls"] == []
