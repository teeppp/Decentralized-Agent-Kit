"""BFF (HTMX UI) E2E: chat through the BFF reaches the agent and renders HTML."""
import uuid

import httpx

from conftest import BFF_URL

MODEL = "fake-default"


def test_index_serves_chat_page():
    resp = httpx.get(f"{BFF_URL}/", timeout=30.0)
    resp.raise_for_status()
    assert "session_bff_" in resp.text


def test_chat_round_trip(fake_llm):
    fake_llm.clear(MODEL)
    fake_llm.script(MODEL, [fake_llm.text("BFF round trip answer.")])

    session_id = f"session_bff_it_{uuid.uuid4().hex[:8]}"
    resp = httpx.post(
        f"{BFF_URL}/chat",
        data={
            "prompt": "Hello via BFF",
            "session_id": session_id,
            "user_id": f"user_{session_id}",
        },
        timeout=120.0,
    )
    resp.raise_for_status()

    assert "Hello via BFF" in resp.text  # user message echoed
    assert "BFF round trip answer." in resp.text  # agent answer rendered
