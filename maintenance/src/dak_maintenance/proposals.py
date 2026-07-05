"""Shared proposal model for tech-watch / feature-sync / charter-review."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Proposal:
    title: str
    body: str
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"title": self.title, "body": self.body, "labels": self.labels}


def _norm(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip().lower())


def dedupe(proposals: list[Proposal], existing_titles: list[str], max_items: int) -> list[Proposal]:
    """Drop proposals whose title matches an existing issue, then cap the count."""
    seen = {_norm(t) for t in (existing_titles or [])}
    out: list[Proposal] = []
    for p in proposals:
        key = _norm(p.title)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(p)
        if len(out) >= max_items:
            break
    return out
