"""Provider-neutral web search, decoupled from the LLM provider.

Backends (auto-selected):
  - Tavily      if TAVILY_API_KEY is set (agent-friendly, clean JSON).
  - DuckDuckGo  otherwise (no key, best-effort HTML scrape).

This keeps "open web search" available while the LLM stays swappable
(Gemini / Ollama / OpenAI / …) — the search key is independent of the LLM.
"""

from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from typing import Callable

import httpx


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def _tavily(query: str, k: int, timeout: float) -> list[SearchResult]:
    key = os.environ["TAVILY_API_KEY"]
    r = httpx.post(
        "https://api.tavily.com/search",
        json={"api_key": key, "query": query, "max_results": k, "search_depth": "basic"},
        timeout=timeout,
    )
    r.raise_for_status()
    out = []
    for item in r.json().get("results", [])[:k]:
        out.append(SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("content", ""),
        ))
    return out


_DDG_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
    r'(?:class="result__snippet"[^>]*>(?P<snip>.*?)</a>)?',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text or "")).strip()


def _duckduckgo(query: str, k: int, timeout: float) -> list[SearchResult]:
    r = httpx.get(
        "https://html.duckduckgo.com/html/",
        params={"q": query},
        headers={"User-Agent": "Mozilla/5.0 (compatible; DAK-tech-watch/1.0)"},
        timeout=timeout,
    )
    r.raise_for_status()
    out = []
    for m in _DDG_RE.finditer(r.text):
        url = html.unescape(m.group("url") or "")
        title = _clean(m.group("title"))
        if not url or not title:
            continue
        out.append(SearchResult(title=title, url=url, snippet=_clean(m.group("snip"))))
        if len(out) >= k:
            break
    return out


def web_search(query: str, k: int = 5, timeout: float = 15.0) -> list[SearchResult]:
    """Search the web. Fails soft (returns [] on error) so callers never crash."""
    backend: Callable[[str, int, float], list[SearchResult]]
    backend = _tavily if os.getenv("TAVILY_API_KEY") else _duckduckgo
    try:
        return backend(query, k, timeout)
    except Exception:
        # Fallback to DDG if Tavily failed for some reason.
        if backend is _tavily:
            try:
                return _duckduckgo(query, k, timeout)
            except Exception:
                return []
        return []
