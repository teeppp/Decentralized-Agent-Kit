from dak_maintenance.search import SearchResult
from dak_maintenance.watch import propose_technologies, generate_queries, gather_candidates
from dak_maintenance.jsonutil import extract_json


def test_extract_json_array():
    assert extract_json('```json\n["a", "b"]\n```') == ["a", "b"]
    assert extract_json('prefix [1, 2] suffix') == [1, 2]


def test_generate_queries():
    complete = lambda p: '["mcp new spec", "a2a update"]'
    assert generate_queries("charter", complete) == ["mcp new spec", "a2a update"]


def test_gather_candidates_dedupes_by_url():
    def search(q, k):
        return [SearchResult("T", "http://x", "s"), SearchResult("T2", "http://x", "s")]
    got = gather_candidates(["q1", "q2"], search, k=5)
    assert len(got) == 1


def _fake_complete_factory():
    calls = {"n": 0}

    def complete(prompt: str) -> str:
        calls["n"] += 1
        if calls["n"] == 1:  # generate_queries
            return '["query one"]'
        # evaluate -> two proposals
        return (
            '[{"title": "[tech-watch] Foo の採用検討", "subject": "Foo", "url": "http://foo",'
            ' "fit": "MCP", "sketch": "add to mcp-server"},'
            ' {"title": "[tech-watch] Bar の採用検討", "subject": "Bar", "url": "http://bar",'
            ' "fit": "A2A", "sketch": "add to agent"}]'
        )
    return complete


def test_propose_technologies_end_to_end():
    def search(q, k):
        return [SearchResult("Foo lib", "http://foo", "great")]
    proposals = propose_technologies("charter text", _fake_complete_factory(), search=search, max_items=5)
    titles = [p.title for p in proposals]
    assert "[tech-watch] Foo の採用検討" in titles
    assert all("tech-watch" in p.labels for p in proposals)
    assert "http://foo" in proposals[0].body


def test_propose_technologies_dedupes_existing_and_caps():
    def search(q, k):
        return [SearchResult("Foo", "http://foo", "s")]
    proposals = propose_technologies(
        "charter", _fake_complete_factory(), search=search,
        existing_titles=["[tech-watch] Foo の採用検討"], max_items=5,
    )
    # Foo は既存なので除外され Bar のみ
    assert [p.title for p in proposals] == ["[tech-watch] Bar の採用検討"]


def test_propose_technologies_caps_to_max():
    def search(q, k):
        return [SearchResult("Foo", "http://foo", "s")]
    proposals = propose_technologies("charter", _fake_complete_factory(), search=search, max_items=1)
    assert len(proposals) == 1


def test_no_candidates_returns_empty():
    proposals = propose_technologies("charter", lambda p: "[]", search=lambda q, k: [], max_items=5)
    assert proposals == []
