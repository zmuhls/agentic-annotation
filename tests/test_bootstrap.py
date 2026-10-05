"""Tests for the one-step bootstrap that drafts ia.md and routing.json together.

The Hypothesis API is always mocked: these tests never reach the network and
never read the maintainer's real groups or taxonomy. The fixtures are the ones
both drafters are tested against, so a passing run here means the combined
command produces the same pair the two scripts produce run in order.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import bootstrap  # noqa: E402
import bootstrap_ia  # noqa: E402
from test_bootstrap_ia import ANNOTATIONS, GROUPS, TEMPLATE  # noqa: E402

USER = "acct:new@hypothes.is"


class TestDrafts:
    @pytest.fixture
    def pair(self):
        return bootstrap.drafts(TEMPLATE, USER, GROUPS, ANNOTATIONS)

    def test_routing_reads_the_drafted_ia_not_the_one_on_disk(self, pair):
        # No ia.md is involved: the routing agrees with the text drafted
        # alongside it, which is what a preview needs before anything is written.
        _, routing = pair
        assert routing["group_nodes"] == {
            "DISS01": "diss-reading/general", "TEACH1": "eng-2100-fall/general"}

    def test_every_node_the_routing_names_is_defined_in_the_ia(self, pair):
        ia_text, routing = pair
        named = (set(routing["group_nodes"].values())
                 | {o["node"] for o in routing["group_domain_overrides"]}
                 | {routing["general_node"], routing["default_node"]})
        assert named <= bootstrap_ia.node_ids(ia_text)

    def test_ia_is_the_same_draft_bootstrap_ia_makes(self, pair):
        counts = bootstrap_ia.domains_by_group(ANNOTATIONS)
        assert pair[0] == bootstrap_ia.draft(TEMPLATE, USER, GROUPS, counts)


class TestSummary:
    def test_lists_each_group_and_busy_domain_with_its_node(self):
        ia_text, routing = bootstrap.drafts(TEMPLATE, USER, GROUPS, ANNOTATIONS)
        text = "\n".join(bootstrap.summary(ia_text, routing))
        assert "Diss Reading → diss-reading/general" in text
        assert "forum.example → diss-reading/forum-example" in text
        assert "ENG 2100 / Fall → eng-2100-fall/general" in text
        assert "Public → reading/general" in text
        assert "news.example → reading/news-example" in text

    def test_counts_groups_left_at_inbox(self):
        _, routing = bootstrap.drafts(TEMPLATE, USER, GROUPS, ANNOTATIONS)
        routing["group_nodes"]["TEACH1"] = "inbox"
        text = "\n".join(bootstrap.summary(TEMPLATE, routing))
        assert "1 group(s) still at inbox" in text


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
        ia.write_text(TEMPLATE)
        monkeypatch.setattr(bootstrap_ia, "get", fake_get)
        monkeypatch.setattr(bootstrap, "IA_FILE", ia)
        monkeypatch.setattr(bootstrap, "ROUTING_FILE", tmp_path / "routing.json")
        monkeypatch.setattr(bootstrap, "load_config",
                            lambda: {"api_token": "test-token", "user": USER})
        monkeypatch.setattr(sys, "argv", ["bootstrap.py", "--write", "--force"])
        return {"calls": calls, "ia": ia, "routing": tmp_path / "routing.json"}

    def test_writes_an_agreeing_pair_from_one_api_pass(self, env):
        bootstrap.main()
        ia_text = env["ia"].read_text()
        routing = json.loads(env["routing"].read_text())
        assert USER in ia_text
        assert routing["group_nodes"]["DISS01"] == "diss-reading/general"
        assert "diss-reading/general" in bootstrap_ia.node_ids(ia_text)
        assert env["calls"] == ["profile/groups", "search"]

    def test_force_replaces_an_existing_routing(self, env):
        env["routing"].write_text("{}\n")
        bootstrap.main()
        assert json.loads(env["routing"].read_text())["group_nodes"]

    def test_write_without_force_refuses_before_any_call(self, env, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["bootstrap.py", "--write"])
        with pytest.raises(SystemExit):
            bootstrap.main()
        assert env["calls"] == []
        assert env["ia"].read_text() == TEMPLATE
        assert not env["routing"].exists()

    def test_preview_prints_the_plan_and_writes_nothing(self, env, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["bootstrap.py"])
        bootstrap.main()
        assert "Diss Reading → diss-reading/general" in capsys.readouterr().out
        assert env["ia"].read_text() == TEMPLATE
        assert not env["routing"].exists()

    def test_a_missing_template_exits_before_any_call(self, env):
        env["ia"].unlink()
        with pytest.raises(SystemExit):
            bootstrap.main()
        assert env["calls"] == []
        assert not env["routing"].exists()

    @pytest.mark.parametrize("config", [
        {"api_token": "YOUR-TOKEN", "user": USER},
        {"api_token": "test-token"},
    ])
    def test_incomplete_config_exits_before_any_call(self, env, monkeypatch, config):
        monkeypatch.setattr(bootstrap, "load_config", lambda: config)
        with pytest.raises(SystemExit):
            bootstrap.main()
        assert env["calls"] == []
