"""Provider-neutral `complete(prompt) -> str`, selectable at runtime.

Every major provider exposes an OpenAI-compatible /chat/completions endpoint, so
one httpx call covers all of them — no litellm/SDK bloat, no hardcoded vendor.
Pick a provider purely via env:

  MAINT_LLM_BASE_URL   OpenAI-compatible base URL
  MAINT_LLM_MODEL      model id
  MAINT_LLM_API_KEY    api key ("ollama" / anything for keyless local)

Presets (set BASE_URL/MODEL accordingly):
  Gemini  https://generativelanguage.googleapis.com/v1beta/openai   gemini-2.5-flash   (GOOGLE_API_KEY)
  Ollama  http://localhost:11434/v1                                 llama3.2:3b        (any key)
  OpenAI  https://api.openai.com/v1                                 gpt-4o-mini        (OPENAI_API_KEY)
  Anthropic https://api.anthropic.com/v1                            claude-sonnet-5    (ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import os

import httpx


def make_complete(timeout: float = 60.0):
    """Return a `complete(prompt) -> str`, or None if MAINT_LLM_* is not configured."""
    base_url = os.getenv("MAINT_LLM_BASE_URL")
    model = os.getenv("MAINT_LLM_MODEL")
    if not base_url or not model:
        return None
    api_key = os.getenv("MAINT_LLM_API_KEY", "not-needed")

    def complete(prompt: str) -> str:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    return complete


# Backwards-compatible alias (earlier name).
make_openai_complete = make_complete
