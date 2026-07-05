"""`dak-maint` CLI. Primary entry: `triage` — used by the dependency-triage workflow.

Always exits 0 (the workflow reads the emitted JSON to decide labels/merge),
except on usage errors.
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
from .llm_client import make_openai_complete


def _bool(s: str) -> bool:
    return str(s).strip().lower() in {"1", "true", "yes", "success", "green"}


def _pick_assessor(kind: str):
    if kind == "llm":
        complete = make_openai_complete()
        if complete is not None:
            return LLMAssessor(complete, tier="llm")
        print("warn: ASSESSOR=llm だが MAINT_LLM_* 未設定。heuristic にフォールバック。", file=sys.stderr)
    return HeuristicAssessor()


def cmd_triage(args: argparse.Namespace) -> int:
    bump = classify_update(args.from_version, args.to_version)

    changelog = ""
    if args.changelog_file:
        try:
            changelog = open(args.changelog_file, encoding="utf-8").read()
        except OSError as e:
            print(f"warn: changelog 読み込み失敗: {e}", file=sys.stderr)
    elif args.fetch_changelog:
        changelog = get_changelog(args.package, args.from_version, args.to_version)

    assessor = _pick_assessor(args.assessor)
    risk = assess_risk(args.package, args.from_version, args.to_version, changelog, assessor)
    decision = decide(bump, _bool(args.ci_passed), risk)

    result = {
        "package": args.package,
        "from": args.from_version,
        "to": args.to_version,
        "bump": bump.value,
        "risk": {"level": risk.level.value, "summary": risk.summary, "tier": risk.tier},
        "decision": {"action": decision.action, "reason": decision.reason, "labels": decision.labels},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # GitHub Actions 用の出力（$GITHUB_OUTPUT があれば追記）
    gh_out = os.getenv("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as f:
            f.write(f"action={decision.action}\n")
            f.write(f"bump={bump.value}\n")
            f.write(f"risk={risk.level.value}\n")
            f.write("labels=" + ",".join(decision.labels) + "\n")
            f.write("reason=" + decision.reason.replace("\n", " ") + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dak-maint", description="DAK self-maintenance toolkit")
    sub = p.add_subparsers(dest="command", required=True)

    t = sub.add_parser("triage", help="依存更新を判定する")
    t.add_argument("--package", required=True)
    t.add_argument("--from", dest="from_version", required=True)
    t.add_argument("--to", dest="to_version", required=True)
    t.add_argument("--ci-passed", default="false", help="true/false/success")
    t.add_argument("--changelog-file", default=None, help="ローカルの changelog テキスト")
    t.add_argument("--fetch-changelog", action="store_true", help="PyPI/GitHub から取得")
    t.add_argument("--assessor", choices=["heuristic", "llm"], default="heuristic")
    t.set_defaults(func=cmd_triage)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
