"""Tests for the full backfill in fetch_annotations.py.

`poll.search` is always replaced, so these tests never reach api.hypothes.is,
and `OUT` points into a tmp dir, so they never touch the real
data/annotations.jsonl.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_annotations  # noqa: E402
import poll  # noqa: E402
from test_poll import _FakeSearch  # noqa: E402

# a1 and a2 share a millisecond, so a two-row page ends inside it
CREATED = ["2026-09-20T00:00:00.100000+00:00",
           "2026-09-20T00:00:01.500100+00:00",
           "2026-09-20T00:00:01.500900+00:00",
           "2026-09-20T00:00:02.000000+00:00"]


def _rows():
    return [{"id": f"a{i}", "created": s} for i, s in enumerate(CREATED)]


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_annotations, "OUT", tmp_path / "annotations.jsonl")
    monkeypatch.setattr(poll, "CONFIG", {"api_token": "test-token",
                                         "user": "acct:new@hypothes.is",
                                         "since": "2026-09-19T00:00:00.000000+00:00"})


def _written():
    return [json.loads(line)["id"] for line in fetch_annotations.OUT.open()]


class TestBackfill:
    def test_a_page_boundary_inside_one_created_millisecond_loses_nothing(self, monkeypatch):
        # the old last-row cursor skipped a2 here: the api truncates
        # search_after to a1's millisecond and returns only rows after it
        monkeypatch.setattr(poll, "search", _FakeSearch(_rows()))
        got = poll.fetch_new("2026-09-19T00:00:00.000000+00:00", page_size=2, key="created")
        assert [r["id"] for r in got] == ["a0", "a1", "a2", "a3"]

    def test_writes_every_annotation_oldest_first(self, monkeypatch):
        fake = _FakeSearch(_rows())
        monkeypatch.setattr(poll, "search", fake)
        fetch_annotations.main()
        assert _written() == ["a0", "a1", "a2", "a3"]
        assert fake.calls == 1

    def test_no_since_pulls_the_whole_history(self, monkeypatch):
        asked = []
        monkeypatch.setattr(poll, "search", lambda params, **kw: asked.append(params) or {"rows": []})
        monkeypatch.setattr(poll, "CONFIG", {**poll.CONFIG, "since": None})
        fetch_annotations.main()
        assert asked[0]["search_after"] < "1970-01-01"
        assert asked[0]["sort"] == "created"

    def test_a_failed_pull_leaves_the_previous_file_untouched(self, monkeypatch):
        fetch_annotations.OUT.write_text('{"id": "old"}\n')

        def down(params, **kw):
            raise poll.urllib.error.URLError("no route to host")

        monkeypatch.setattr(poll, "search", down)
        with pytest.raises(SystemExit, match="unreachable"):
            fetch_annotations.main()
        assert _written() == ["old"]
        assert not list(fetch_annotations.OUT.parent.glob("*.tmp"))

    def test_an_auth_failure_names_the_status(self, monkeypatch):
        def unauthorized(params, **kw):
            raise poll.urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

        monkeypatch.setattr(poll, "search", unauthorized)
        with pytest.raises(SystemExit, match="401 Unauthorized"):
            fetch_annotations.main()

    def test_a_placeholder_token_exits_before_any_call(self, monkeypatch):
        monkeypatch.setattr(poll, "CONFIG", {**poll.CONFIG,
                                             "api_token": "YOUR-HYPOTHESIS-DEVELOPER-TOKEN"})
        monkeypatch.setattr(poll, "search", lambda *a, **k: pytest.fail("called the api"))
        with pytest.raises(SystemExit, match="api_token"):
            fetch_annotations.main()
