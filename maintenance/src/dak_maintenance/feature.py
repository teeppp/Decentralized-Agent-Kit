"""feature-sync pipeline: summarize NEW features (not fixes) of updated deps.

Deterministic changelog retrieval (changelog.get_changelog) + provider-neutral LLM
summarization. No open web search needed — the deps are already known.
"""

from __future__ import annotations

from typing import Callable

from .changelog import get_changelog
from .jsonutil import extract_json
from .proposals import Proposal, dedupe

CompleteFn = Callable[[str], str]
ChangelogFn = Callable[[str, str, str], str]

_PROMPT = """You review a dependency's changelog for a project with this charter:
---
{charter}
---
Dependency: {package} ({from_version} -> {to_version})
Changelog:
---
{changelog}
---
Identify only genuinely NEW features (not bug fixes) worth adopting in the project.
For each, propose an adoption. Return an empty list if nothing is worth adopting.

Respond with ONLY a JSON array of objects:
[{{"title": "Adopt <feature> in {package} v{to_version}",
   "feature": "<what's new>", "component": "<agent|mcp-server|bff|cli>",
   "sketch": "<how to integrate>"}}]
"""


def propose_feature_adoptions(
    deps: list[dict],
    complete: CompleteFn,
    charter: str = "",
    get_changelog_fn: ChangelogFn = get_changelog,
    existing_titles: list[str] | None = None,
    max_items: int = 2,
) -> list[Proposal]:
    """deps: list of {"package","from","to"} for recently updated dependencies."""
    proposals: list[Proposal] = []
    for dep in deps:
        pkg = dep.get("package", "")
        frm = dep.get("from", "")
        to = dep.get("to", "")
        changelog = dep.get("changelog") or get_changelog_fn(pkg, frm, to)
        if not (changelog or "").strip():
            continue
        raw = complete(_PROMPT.format(
            charter=charter[:4000], package=pkg, from_version=frm,
            to_version=to, changelog=changelog[:8000],
        ))
        data = extract_json(raw)
        for it in (data if isinstance(data, list) else []):
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or "").strip()
            if not title:
                continue
            body = (
                f"**新機能**: {it.get('feature', '')}\n"
                f"**対象コンポーネント**: {it.get('component', '')}\n\n"
                f"**導入スケッチ**: {it.get('sketch', '')}\n\n"
                f"依存: `{pkg}` {frm} -> {to}\n\n"
                f"_自動生成 (feature-sync)。人間が取り込み価値を最終判断する。_"
            )
            proposals.append(Proposal(title=title, body=body, labels=["feature-sync", "automation"]))
    return dedupe(proposals, existing_titles or [], max_items)
