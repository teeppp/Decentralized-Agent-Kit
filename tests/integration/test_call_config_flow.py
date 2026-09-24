"""Per-call settings (`dak:` keys in `/run`'s `state_delta`) through the real
stack: agent container → LiteLLM → fake LLM. See docs/architecture/call_config.md."""
import json

import httpx

from conftest import AGENT_RUN_TIMEOUT, AGENT_URL, APP_NAME, FAKE_LLM_URL, event_texts

MODEL = "fake-default"
DATE_SCHEMA = {"type": "object", "required": ["date"], "properties": {"date": {"type": "string"}}}


def _run(agent, session_id: str, prompt: str, state_delta: dict) -> list:
    """`AgentClient.run` cannot pass `state_delta`; post the payload directly."""
    payload = {
        "app_name": APP_NAME,
        "user_id": agent.user_id,
        "session_id": session_id,
        "new_message": {"parts": [{"text": prompt}]},
        "state_delta": state_delta,
    }
    resp = httpx.post(f"{AGENT_URL}/run", json=payload, timeout=AGENT_RUN_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def test_call_instruction_is_the_system_prompt_the_llm_receives(agent, fake_llm):
    fake_llm.clear(MODEL)
    fake_llm.script(MODEL, [fake_llm.text("ok")])

    _run(agent, agent.create_session(), "hi", {"dak:instruction": "Answer in one word."})

    messages = httpx.get(f"{FAKE_LLM_URL}/requests/{MODEL}", timeout=10.0).json()[-1]["messages"]
    system = messages[0]
    assert system["role"] == "system"
    content = system["content"] if isinstance(system["content"], str) else "".join(
        c.get("text", "") for c in system["content"])
    # The whole system prompt: the caller's instruction plus the identity line
    # ADK appends to every agent's instruction.
    assert content == 'Answer in one word.\n\nYou are an agent. Your internal name is "dak_agent".'


def test_reply_not_matching_output_schema_returns_structured_failure(agent, fake_llm):
    fake_llm.clear(MODEL)
    fake_llm.script(MODEL, [fake_llm.text('{"note": "missing date"}')])

    events = _run(agent, agent.create_session(), "when?", {"dak:output_schema": DATE_SCHEMA})

    failures = [json.loads(t) for t in event_texts(events) if "output_schema_validation_failed" in t]
    assert failures, f"events: {events}"
    assert failures[-1]["error"] == "output_schema_validation_failed"
    assert [i["path"] for i in failures[-1]["issues"]] == ["date"]


def test_reply_matching_output_schema_is_returned_as_json(agent, fake_llm):
    fake_llm.clear(MODEL)
    fake_llm.script(MODEL, [fake_llm.text('{"date": "2026-09-22"}')])

    events = _run(agent, agent.create_session(), "when?", {"dak:output_schema": DATE_SCHEMA})

    texts = event_texts(events)
    assert json.loads(texts[-1]) == {"date": "2026-09-22"}, f"events: {events}"
