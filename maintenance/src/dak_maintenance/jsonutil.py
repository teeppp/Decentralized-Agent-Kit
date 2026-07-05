"""Tolerant JSON extraction from LLM responses (prose / code-fence wrapped)."""

from __future__ import annotations

import json
import re

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)
_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)
_ARR_RE = re.compile(r"\[.*\]", re.DOTALL)


def extract_json(text: str):
    """Return the first JSON object or array found, or {} if none/invalid."""
    if not text:
        return {}
    m = _FENCE_RE.search(text)
    candidate = m.group(1) if m else None
    if candidate is None:
        obj = _OBJ_RE.search(text)
        arr = _ARR_RE.search(text)
        # pick whichever appears first
        if obj and arr:
            candidate = obj.group(0) if obj.start() < arr.start() else arr.group(0)
        else:
            candidate = (obj or arr).group(0) if (obj or arr) else None
    if candidate is None:
        return {}
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return {}
