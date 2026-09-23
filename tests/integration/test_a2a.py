"""A2A protocol integration tests.

A2A is the peer-to-peer seam of the kit (`agent/dak_agent/a2a_peer_manager.py`),
but it had no test coverage, so a breaking `a2a-sdk` bump passed CI green while
making every peer handshake fail (PR #76). These tests pin the two things that
broke: the agent-card wire format and an actual JSON-RPC task exchange.
"""
import uuid

import httpx
import pytest

from conftest import AGENT_URL, APP_NAME

MODEL = "fake-default"
AGENT_CARD_URL = f"{AGENT_URL}/a2a/{APP_NAME}/.well-known/agent-card.json"
A2A_RPC_URL = f"{AGENT_URL}/a2a/{APP_NAME}"


@pytest.fixture
def agent_card():
    resp = httpx.get(AGENT_CARD_URL, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def test_agent_card_is_served(agent_card):
    """`a2a_peer_manager` resolves peers at this well-known path."""
    assert agent_card["name"] == APP_NAME
    assert agent_card["skills"], "card advertises no skills"


def test_agent_card_carries_a_top_level_transport_url(agent_card):
    """The card must keep the top-level `url` + `preferredTransport` fields.

    This guards the `a2a-sdk<1` pin in agent/pyproject.toml. a2a-sdk 1.x serves
    the card with `url` moved into `supportedInterfaces`, which 0.3 peers reject
    ("url Field required"); and because DAK's card declares protocolVersion
    0.2.6, 1.x clients find "no compatible transports". Update this test
    together with the card when migrating to 1.x.
    """
    assert "url" in agent_card, (
        f"agent card has no top-level 'url' (a2a-sdk 1.x wire format?): {agent_card}"
    )
    assert agent_card["url"].endswith(f"/a2a/{APP_NAME}")
    assert agent_card["preferredTransport"] == "JSONRPC"


def test_a2a_message_send_round_trip(fake_llm):
    """A peer can drive the agent over A2A JSON-RPC and get its reply back."""
    fake_llm.clear(MODEL)
    fake_llm.script(MODEL, [fake_llm.text("A2A pong from DAK.")])

    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "ping"}],
                "messageId": uuid.uuid4().hex,
                "kind": "message",
            }
        },
    }
    resp = httpx.post(A2A_RPC_URL, json=payload, timeout=120.0)
    resp.raise_for_status()
    body = resp.json()

    assert "error" not in body, f"A2A call returned an error: {body}"
    result = body["result"]
    assert result["kind"] == "task"

    texts = [
        part.get("text")
        for artifact in result.get("artifacts") or []
        for part in artifact.get("parts") or []
    ]
    assert "A2A pong from DAK." in texts, f"agent reply missing from artifacts: {result}"
