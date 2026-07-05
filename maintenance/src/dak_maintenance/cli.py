"""`dak-maint` CLI. Provider-neutral (Gemini/Ollama/OpenAI/... via MAINT_LLM_*).

Subcommands:
  triage         依存更新を判定（auto-merge / needs-review）
  watch          憲章に沿う新技術を探索し提案 JSON を出力（tech-watch WF が Issue 化）
  feature-sync   依存の新機能取り込み提案 JSON を出力
  charter-review 憲章の見直し提案 JSON を出力

reasoning 系（watch/feature-sync/charter-review）は LLM 必須。MAINT_LLM_* 未設定なら
proposals は空を返す（ワークフローは 0 件として扱う）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .semver import classify_update
from .risk import HeuristicAssessor, LLMAssessor, assess_risk
from .decide import decide
from .changelog import get_changelog
from .llm_client import make_complete
from .watch import propose_technologies
from .feature import propose_feature_adoptions
from .charter import review_charter


def _bool(s: str) -> bool:
    return str(s).strip().lower() in {"1", "true", "yes", "success", "green"}


def _read(path: str) -> str:
    try:
        return open(path, encoding="utf-8").read()
    except OSError as e:
        print(f"warn: {path} 読み込み失敗: {e}", file=sys.stderr)
        return ""


def _require_complete():
    complete = make_complete()
    if complete is None:
        print("warn: MAINT_LLM_* 未設定のため LLM 判定をスキップ（proposals=[]）。", file=sys.stderr)
    return complete


def _emit_proposals(proposals) -> int:
    print(json.dumps([p.to_dict() for p in proposals], ensure_ascii=False, indent=2))
    return 0


# ---- triage (Tier0/1) ----

def cmd_triage(args: argparse.Namespace) -> int:
    bump = classify_update(args.from_version, args.to_version)
    changelog = _read(args.changelog_file) if args.changelog_file else (
        get_changelog(args.package, args.from_version, args.to_version) if args.fetch_changelog else ""
    )
    if args.assessor == "llm":
        complete = make_complete()
        assessor = LLMAssessor(complete, tier="llm") if complete else HeuristicAssessor()
        if complete is None:
            print("warn: ASSESSOR=llm だが MAINT_LLM_* 未設定。heuristic にフォールバック。", file=sys.stderr)
    else:
        assessor = HeuristicAssessor()
    risk = assess_risk(args.package, args.from_version, args.to_version, changelog, assessor)
    decision = decide(bump, _bool(args.ci_passed), risk)

    result = {
        "package": args.package, "from": args.from_version, "to": args.to_version,
        "bump": bump.value,
        "risk": {"level": risk.level.value, "summary": risk.summary, "tier": risk.tier},
        "decision": {"action": decision.action, "reason": decision.reason, "labels": decision.labels},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    gh_out = os.getenv("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"action={decision.action}\nbump={bump.value}\nrisk={risk.level.value}\n")
            f.write("labels=" + ",".join(decision.labels) + "\n")
            f.write("reason=" + decision.reason.replace("\n", " ") + "\n")
    return 0


# ---- watch (Tier2, provider-neutral) ----

def cmd_watch(args: argparse.Namespace) -> int:
    complete = _require_complete()
    if complete is None:
        return _emit_proposals([])
    existing = json.loads(args.existing_titles) if args.existing_titles else []
    proposals = propose_technologies(
        _read(args.charter), complete, existing_titles=existing, max_items=args.max_items,
    )
    return _emit_proposals(proposals)


def cmd_feature_sync(args: argparse.Namespace) -> int:
    complete = _require_complete()
    if complete is None:
        return _emit_proposals([])
    deps = json.loads(args.deps) if args.deps else []
    existing = json.loads(args.existing_titles) if args.existing_titles else []
    proposals = propose_feature_adoptions(
        deps, complete, charter=_read(args.charter) if args.charter else "",
        existing_titles=existing, max_items=args.max_items,
    )
    return _emit_proposals(proposals)


def cmd_charter_review(args: argparse.Namespace) -> int:
    complete = _require_complete()
    if complete is None:
        return _emit_proposals([])
    existing = json.loads(args.existing_titles) if args.existing_titles else []
    proposals = review_charter(
        _read(args.charter), complete, quarter=args.quarter, existing_titles=existing,
    )
    return _emit_proposals(proposals)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dak-maint", description="DAK self-maintenance toolkit")
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("triage", help="依存更新を判定する")
    t.add_argument("--package", required=True)
    t.add_argument("--from", dest="from_version", required=True)
    t.add_argument("--to", dest="to_version", required=True)
    t.add_argument("--ci-passed", default="false")
    t.add_argument("--changelog-file", default=None)
    t.add_argument("--fetch-changelog", action="store_true")
    t.add_argument("--assessor", choices=["heuristic", "llm"], default="heuristic")
    t.set_defaults(func=cmd_triage)

    w = sub.add_parser("watch", help="新技術を探索し提案する")
    w.add_argument("--charter", default="docs/CHARTER.md")
    w.add_argument("--existing-titles", default=None, help="JSON array of existing issue titles")
    w.add_argument("--max-items", type=int, default=2)
    w.set_defaults(func=cmd_watch)

    f = sub.add_parser("feature-sync", help="依存の新機能取り込みを提案する")
    f.add_argument("--deps", default=None, help='JSON: [{"package","from","to"}]')
    f.add_argument("--charter", default="docs/CHARTER.md")
    f.add_argument("--existing-titles", default=None)
    f.add_argument("--max-items", type=int, default=2)
    f.set_defaults(func=cmd_feature_sync)

    c = sub.add_parser("charter-review", help="憲章の見直しを提案する")
    c.add_argument("--charter", default="docs/CHARTER.md")
    c.add_argument("--quarter", default="")
    c.add_argument("--existing-titles", default=None)
    c.set_defaults(func=cmd_charter_review)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
