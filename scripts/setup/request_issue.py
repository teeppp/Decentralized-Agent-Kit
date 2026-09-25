#!/usr/bin/env python3
"""Create the scheduled workflows' proposals as request Issues ("要望:") and put
them in the Project's Backlog.

    python3 scripts/setup/request_issue.py proposals.json --source tech-watch

proposals.json: [{"title", "body", "labels"}] as printed by `dak-maint`.
An Issue created with the workflow's GITHUB_TOKEN does not trigger
project-autoadd.yml, so when DAK_PROJECT_URL is set this script adds the Issue
to the Project and sets Status=Backlog itself, with DAK_PROJECT_TOKEN, using
only the `gh project` CLI.
"""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PROJECT_URL_RE = re.compile(r"https://github\.com/(?:users|orgs)/([^/]+)/projects/(\d+)")


def gh(args, env=None):
    """Run `gh` and return stdout (tests replace this)."""
    return subprocess.run(["gh", *args], check=True, text=True, capture_output=True, env=env).stdout


def request_body(body, source):
    return f"""## 要望

{body.strip()}

## 出典

- 誰から: DAK 保守ワークフロー（自動提案）
- いつ: {date.today().isoformat()}
- 経路: {source}

## 派生 PBI

未起票。採否と価値を検討してから PBI にする。提案の生成は、採用の決定ではない。
"""


def parse_project_url(url):
    m = PROJECT_URL_RE.fullmatch(url.strip().rstrip("/"))
    if not m:
        raise SystemExit(f"DAK_PROJECT_URL is not a GitHub Project URL: {url}")
    return m.group(1), m.group(2)


def add_to_backlog(issue_url, project_url, token):
    owner, number = parse_project_url(project_url)
    env = {**os.environ, "GH_TOKEN": token}
    item_id = json.loads(gh(["project", "item-add", number, "--owner", owner, "--url", issue_url,
                             "--format", "json"], env))["id"]
    fields = json.loads(gh(["project", "field-list", number, "--owner", owner, "--format", "json"], env))["fields"]
    status = next((f for f in fields if f.get("name") == "Status"), None)
    backlog = next((o for o in (status or {}).get("options", []) if o.get("name") == "Backlog"), None)
    if not backlog:
        raise SystemExit("The Project's Status field has no 'Backlog' option; run scripts/setup/bootstrap_project.sh")
    project_id = json.loads(gh(["project", "view", number, "--owner", owner, "--format", "json"], env))["id"]
    gh(["project", "item-edit", "--id", item_id, "--project-id", project_id,
        "--field-id", status["id"], "--single-select-option-id", backlog["id"]], env)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("proposals", type=Path)
    parser.add_argument("--source", required=True, help="the workflow that made the proposals")
    args = parser.parse_args(argv)

    text = args.proposals.read_text(encoding="utf-8").strip()
    proposals = json.loads(text) if text else []
    print(f"{len(proposals)} proposal(s)")
    project_url = os.getenv("DAK_PROJECT_URL", "").strip()
    token = os.getenv("DAK_PROJECT_TOKEN", "").strip()

    for proposal in proposals:
        title = proposal["title"].strip()
        if not title.startswith("要望:"):
            title = f"要望: {title}"
        labels = [label for label in proposal.get("labels", []) if not label.startswith("type:")] + ["type:request"]
        with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as f:
            f.write(request_body(proposal.get("body", ""), args.source))
        try:
            issue_url = gh(["issue", "create", "--title", title, "--body-file", f.name,
                            "--label", ",".join(labels)]).strip()
        finally:
            os.unlink(f.name)
        print(issue_url, flush=True)
        if not project_url:
            continue
        if not token:
            raise SystemExit(f"{issue_url} was created, but DAK_PROJECT_TOKEN is missing: add it to the Project by hand")
        add_to_backlog(issue_url, project_url, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
