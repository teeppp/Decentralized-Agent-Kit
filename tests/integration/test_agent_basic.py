"""Basic agent E2E: session creation and a scripted text exchange."""
from conftest import event_texts

MODEL = "fake-default"


def test_session_create_and_text_response(agent, fake_llm):
    fake_llm.clear(MODEL)
    fake_llm.script(MODEL, [fake_llm.text("Hello! I am the DAK agent.")])

    session_id = agent.create_session()
    events = agent.run(session_id, "Hello, who are you?")

    texts = event_texts(events)
    assert any("Hello! I am the DAK agent." in t for t in texts), f"events: {events}"


def test_conversation_history_persists(agent, fake_llm):
    fake_llm.clear(MODEL)
    fake_llm.script(MODEL, [fake_llm.text("first answer"), fake_llm.text("second answer")])

    session_id = agent.create_session()
    agent.run(session_id, "first message")
    events = agent.run(session_id, "second message")

    assert any("second answer" in t for t in event_texts(events))

    # The session transcript should contain both turns
    import httpx
    from conftest import APP_NAME

    resp = httpx.get(
        f"{agent.base_url}/apps/{APP_NAME}/users/{agent.user_id}/sessions/{session_id}",
        timeout=30.0,
    )
    resp.raise_for_status()
    transcript = str(resp.json())
    assert "first message" in transcript
    assert "second message" in transcript
