"""Tests for request_issue.py (run: `uv run --no-project --with pytest pytest scripts/setup -q`).
`gh` is replaced by a fake that records every call."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("request_issue", Path(__file__).with_name("request_issue.py"))
request_issue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(request_issue)

PROJECT_URL = "https://github.com/users/octo/projects/7"
ISSUE_URL = "https://github.com/octo/repo/issues/42"


class FakeGh:
    def __init__(self):
        self.calls = []  # (args, env GH_TOKEN)

    def __call__(self, args, env=None):
        self.calls.append((args, (env or {}).get("GH_TOKEN")))
        if args[:2] == ["issue", "create"]:
            return ISSUE_URL + "\n"
        if args[:2] == ["project", "item-add"]:
            return json.dumps({"id": "ITEM"})
        if args[:2] == ["project", "field-list"]:
            return json.dumps({"fields": [
                {"id": "F-other", "name": "Priority", "options": [{"id": "p0", "name": "P0"}]},
                {"id": "F-status", "name": "Status", "options": [
                    {"id": "o-todo", "name": "Ready"}, {"id": "o-backlog", "name": "Backlog"}]},
            ]})
        if args[:2] == ["project", "view"]:
            return json.dumps({"id": "PROJ"})
        return ""


def _proposals(tmp_path, items):
    path = tmp_path / "proposals.json"
    path.write_text(json.dumps(items))
    return path


PROPOSAL = {"title": "Adopt X", "body": "**新機能**: X を使う", "labels": ["feature-sync", "automation", "type:pbi"]}


def test_proposal_becomes_a_request_issue_and_lands_in_the_backlog(tmp_path, monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(request_issue, "gh", gh)
    monkeypatch.setenv("DAK_PROJECT_URL", PROJECT_URL)
    monkeypatch.setenv("DAK_PROJECT_TOKEN", "project-token")

    assert request_issue.main([str(_proposals(tmp_path, [PROPOSAL])), "--source", "feature-sync"]) == 0

    create = gh.calls[0][0]
    assert create[:2] == ["issue", "create"]
    assert create[create.index("--title") + 1] == "要望: Adopt X"
    assert create[create.index("--label") + 1] == "feature-sync,automation,type:request"
    body = Path(create[create.index("--body-file") + 1])  # already deleted; content checked below
    assert body.suffix == ".md"
    add, fields, view, edit = (c for c in gh.calls[1:])
    assert add[0] == ["project", "item-add", "7", "--owner", "octo", "--url", ISSUE_URL, "--format", "json"]
    assert fields[0][:2] == ["project", "field-list"] and view[0][:2] == ["project", "view"]
    assert edit[0] == ["project", "item-edit", "--id", "ITEM", "--project-id", "PROJ",
                       "--field-id", "F-status", "--single-select-option-id", "o-backlog"]
    assert {token for _, token in gh.calls[1:]} == {"project-token"}  # Project calls use the Project token
    assert gh.calls[0][1] is None  # the issue itself is created with the workflow's own token


def test_request_body_is_a_tidy_request_not_a_verbatim_quote():
    body = request_issue.request_body("**新機能**: X を使う", "tech-watch")

    assert body.startswith("## 要望\n\n**新機能**: X を使う\n")
    assert "- 経路: tech-watch" in body
    assert "## 派生 PBI" in body
    for old in ("## 原文", "一字も", "そのまま保存", "```"):
        assert old not in body


def test_title_that_already_says_request_is_not_prefixed_twice(tmp_path, monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(request_issue, "gh", gh)
    monkeypatch.delenv("DAK_PROJECT_URL", raising=False)

    request_issue.main([str(_proposals(tmp_path, [dict(PROPOSAL, title="要望: Adopt X")])), "--source", "x"])

    create = gh.calls[0][0]
    assert create[create.index("--title") + 1] == "要望: Adopt X"
    assert len(gh.calls) == 1  # no Project configured: only the issue


def test_project_configured_without_token_fails_after_creating_the_issue(tmp_path, monkeypatch):
    gh = FakeGh()
    monkeypatch.setattr(request_issue, "gh", gh)
    monkeypatch.setenv("DAK_PROJECT_URL", PROJECT_URL)
    monkeypatch.delenv("DAK_PROJECT_TOKEN", raising=False)

    with pytest.raises(SystemExit, match="DAK_PROJECT_TOKEN"):
        request_issue.main([str(_proposals(tmp_path, [PROPOSAL])), "--source", "x"])
    assert [c[0][:2] for c in gh.calls] == [["issue", "create"]]


@pytest.mark.parametrize("text", ["", "[]"])
def test_no_proposals_is_zero_issues(tmp_path, monkeypatch, capsys, text):
    gh = FakeGh()
    monkeypatch.setattr(request_issue, "gh", gh)
    path = tmp_path / "proposals.json"
    path.write_text(text)

    assert request_issue.main([str(path), "--source", "x"]) == 0
    assert gh.calls == []
    assert "0 proposal(s)" in capsys.readouterr().out


def test_org_project_url_is_understood():
    assert request_issue.parse_project_url("https://github.com/orgs/acme/projects/12") == ("acme", "12")
    with pytest.raises(SystemExit):
        request_issue.parse_project_url("https://example.com/not-a-project")
