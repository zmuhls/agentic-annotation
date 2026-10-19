"""Tests for the config helpers poll.py and doctor.py share."""

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
