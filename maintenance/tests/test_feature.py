from dak_maintenance.feature import propose_feature_adoptions
from dak_maintenance.charter import review_charter
from dak_maintenance.search import SearchResult


def test_feature_sync_summarizes_new_features():
    def complete(prompt: str) -> str:
        return ('[{"title": "Adopt streaming tools in litellm v1.52.0",'
                ' "feature": "native streaming tool calls", "component": "agent",'
                ' "sketch": "use in meta_llm"}]')
    deps = [{"package": "litellm", "from": "1.51.0", "to": "1.52.0", "changelog": "Added streaming."}]
    proposals = propose_feature_adoptions(deps, complete, max_items=5)
    assert proposals[0].title == "Adopt streaming tools in litellm v1.52.0"
    assert "feature-sync" in proposals[0].labels
    assert "litellm" in proposals[0].body


def test_feature_sync_skips_deps_without_changelog():
    called = {"n": 0}

    def complete(prompt: str) -> str:
        called["n"] += 1
        return "[]"

    # changelog 取得関数が空を返す → LLM は呼ばれない
    deps = [{"package": "x", "from": "1.0.0", "to": "1.0.1"}]
    proposals = propose_feature_adoptions(deps, complete, get_changelog_fn=lambda p, a, b: "", max_items=5)
    assert proposals == []
    assert called["n"] == 0


def test_charter_review_produces_single_issue():
    def complete(prompt: str) -> str:
        return ('{"title": "Charter review 2026-Q3", "landscape": "MCP evolving",'
                ' "revisions": "- add domain X", "domains": "add X"}')
    proposals = review_charter("charter", complete, search=lambda q, k: [], quarter="2026-Q3")
    assert len(proposals) == 1
    assert proposals[0].title == "Charter review 2026-Q3"
    assert "charter" in proposals[0].labels


def test_charter_review_dedupes_existing():
    def complete(prompt: str) -> str:
        return '{"title": "Charter review 2026-Q3", "landscape": "x", "revisions": "y", "domains": "z"}'
    proposals = review_charter(
        "charter", complete, search=lambda q, k: [SearchResult("t", "u", "s")],
        quarter="2026-Q3", existing_titles=["Charter review 2026-Q3"],
    )
    assert proposals == []


def test_a_failing_llm_call_skips_only_that_dependency(capsys):
    """One transient LLM error (e.g. 503) must not fail the whole weekly run."""
    from dak_maintenance.feature import propose_feature_adoptions

    def complete(prompt):
        if "pkg-a" in prompt:
            raise RuntimeError("Server error '503 Service Unavailable'")
        return '[{"title": "Adopt B feature", "feature": "f", "component": "agent", "sketch": "s"}]'

    deps = [{"package": "pkg-a", "from": "1", "to": "2", "changelog": "New: x"},
            {"package": "pkg-b", "from": "1", "to": "2", "changelog": "New: y"}]

    proposals = propose_feature_adoptions(deps, complete)

    assert [p.title for p in proposals] == ["Adopt B feature"]
    assert "pkg-a" in capsys.readouterr().err
