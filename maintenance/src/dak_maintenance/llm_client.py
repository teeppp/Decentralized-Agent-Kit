"""Optional OpenAI-compatible `complete` callable for the LLM assessor.

Works with Ollama's OpenAI endpoint (Tier 1) or any OpenAI-compatible server.
Configured entirely via env so the toolkit stays SDK-free (httpx only), matching
the repo's LiteLLM/openai-compatible convention.

Env:
  MAINT_LLM_BASE_URL  e.g. http://localhost:11434/v1  (Ollama) or an OpenAI base
  MAINT_LLM_MODEL     e.g. llama3.2:3b
  MAINT_LLM_API_KEY   e.g. "ollama" (Ollama ignores it) or a real key
"""

from __future__ import annotations

import os

import httpx


def make_openai_complete(timeout: float = 60.0):
    """Return a `complete(prompt) -> str`, or None if env is not configured."""
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
