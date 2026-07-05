"""Tier 0: semver bump classification. No network, no LLM — fully deterministic."""

from __future__ import annotations

import re
from enum import Enum


class BumpLevel(str, Enum):
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    NONE = "none"
    UNKNOWN = "unknown"  # 非パース可能 / 比較不能 → 安全側で扱う


_VERSION_RE = re.compile(r"^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _parse(version: str) -> tuple[int, int, int] | None:
    """Extract (major, minor, patch) from a version string.

    Tolerant: strips a leading 'v', ignores pre-release/build suffixes
    (e.g. '1.2.3rc1', '1.2.3+local'). Missing components default to 0.
    """
    if not version:
        return None
    m = _VERSION_RE.match(version.strip())
    if not m:
        return None
    major = int(m.group(1))
    minor = int(m.group(2) or 0)
    patch = int(m.group(3) or 0)
    return (major, minor, patch)


def classify_update(from_version: str, to_version: str) -> BumpLevel:
    """Classify the semver bump between two versions.

    A 0.x.y bump in the leading nonzero component is treated conservatively:
    for 0.x releases a minor bump often carries breaking changes, so a change
    in the first *nonzero* position is escalated to MAJOR.
    """
    a = _parse(from_version)
    b = _parse(to_version)
    if a is None or b is None:
        return BumpLevel.UNKNOWN
    if a == b:
        return BumpLevel.NONE

    a_major, a_minor, a_patch = a
    b_major, b_minor, b_patch = b

    # ダウングレードは通常起きない（起きたら人間判断へ）
    if b < a:
        return BumpLevel.UNKNOWN

    # 0.x 系: 最初の非ゼロ成分の変化を破壊的とみなす（PEP 440 の慣行）
    if a_major == 0 and b_major == 0:
        if a_minor != b_minor:
            return BumpLevel.MAJOR
        if a_patch != b_patch:
            return BumpLevel.MINOR
        return BumpLevel.NONE

    if a_major != b_major:
        return BumpLevel.MAJOR
    if a_minor != b_minor:
        return BumpLevel.MINOR
    if a_patch != b_patch:
        return BumpLevel.PATCH
    return BumpLevel.NONE
