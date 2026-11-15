"""Tests for the config helpers poll.py and doctor.py share."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import appconfig  # noqa: E402


class TestClaudeEnv:
    def test_without_the_key_the_cli_gets_this_process_environment(self):
        assert appconfig.claude_env({}) == dict(os.environ)

    def test_adds_the_configured_variables(self):
        env = appconfig.claude_env({"claude_env": {"CLAUDE_CODE_OAUTH_TOKEN": "tok-test"}})
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "tok-test"
        assert env.get("PATH") == os.environ.get("PATH")

    def test_a_configured_value_outranks_an_inherited_one(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://shell.example")
        env = appconfig.claude_env({"claude_env": {"ANTHROPIC_BASE_URL": "https://cfg.example"}})
        assert env["ANTHROPIC_BASE_URL"] == "https://cfg.example"

    def test_values_become_strings_and_nulls_are_dropped(self):
        # subprocess refuses non-string values with a TypeError, which would
        # fail every classification for a config typo
        env = appconfig.claude_env({"claude_env": {"CLAUDE_CODE_USE_BEDROCK": 1, "UNSET_ME": None}})
        assert env["CLAUDE_CODE_USE_BEDROCK"] == "1"
        assert "UNSET_ME" not in env

    def test_a_value_that_is_not_an_object_is_ignored(self):
        # doctor.py fails it; the watcher keeps running on the inherited login
        assert appconfig.claude_env({"claude_env": "CLAUDE_CODE_OAUTH_TOKEN=tok"}) == dict(
            os.environ
        )

    def test_leaves_this_process_environment_alone(self):
        before = dict(os.environ)
        appconfig.claude_env({"claude_env": {"CLAUDE_CODE_OAUTH_TOKEN": "tok-test"}})
        assert dict(os.environ) == before


class TestConfigCredential:
    def test_names_the_credential_config_hands_the_cli(self):
        config = {"claude_env": {"CLAUDE_CODE_OAUTH_TOKEN": "tok-test"}}
        assert appconfig.config_credential(config) == "CLAUDE_CODE_OAUTH_TOKEN"

    def test_an_api_key_counts(self):
        assert appconfig.config_credential({"claude_env": {"ANTHROPIC_API_KEY": "sk-test"}}) == (
            "ANTHROPIC_API_KEY"
        )

    def test_none_without_a_credential(self):
        assert appconfig.config_credential({}) is None
        assert appconfig.config_credential({"claude_env": {"CLAUDE_CODE_USE_BEDROCK": "1"}}) is None
        assert appconfig.config_credential({"claude_env": {"CLAUDE_CODE_OAUTH_TOKEN": ""}}) is None
        assert appconfig.config_credential({"claude_env": "not an object"}) is None


class TestIaSource:
    """ia.md is personal and gitignored; a fresh clone has only ia.example.md."""

    def test_prefers_the_adopters_own_file(self, tmp_path):
        (tmp_path / "ia.md").write_text("mine")
        (tmp_path / "ia.example.md").write_text("sample")
        assert appconfig.ia_source(tmp_path / "ia.md").read_text() == "mine"

    def test_falls_back_to_the_example_beside_it(self, tmp_path):
        (tmp_path / "ia.example.md").write_text("sample")
        assert appconfig.ia_source(tmp_path / "ia.md").read_text() == "sample"


class TestShippedExamples:
    """A fresh clone runs on the three example files, so they must agree."""

    IA = (appconfig.ROOT / "architecture" / "ia.example.md").read_text()

    def test_every_node_the_example_routing_names_is_in_the_example_taxonomy(self):
        import bootstrap_ia

        routing = json.loads((appconfig.ROOT / "routing.example.json").read_text())
        named = {
            *routing["artifact_domains"].values(),
            *routing["group_nodes"].values(),
            *routing["domain_contains"].values(),
            *routing["domain_nodes"].values(),
            *(o["node"] for o in routing["group_domain_overrides"]),
            routing["general_node"],
            routing["default_node"],
        }
        assert named <= bootstrap_ia.node_ids(self.IA)

    def test_the_example_taxonomy_is_a_usable_template(self):
        import bootstrap_ia

        text = bootstrap_ia.draft(self.IA, "acct:new@hypothes.is", [], {})
        assert "`acct:new@hypothes.is`" in text
        assert "sample" not in text.split(bootstrap_ia.NODES_HEADING)[0]
        assert bootstrap_ia.SHARED_TAIL_HEADING in text

    def test_the_personal_taxonomy_is_not_tracked(self):
        ignored = (appconfig.ROOT / ".gitignore").read_text().splitlines()
        assert "architecture/ia.md" in ignored
