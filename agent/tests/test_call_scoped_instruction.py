"""PBI #137 acceptance criterion 1: a `dak:instruction` passed with a call
becomes that session's whole system prompt, and other sessions keep the
default. Drives a real ADK `Runner` (same technique as
`test_session_isolation.py`) and inspects the recorded `LlmRequest`s."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types

from dak_agent.skill_registry import SkillRegistry

DEFAULT_INSTRUCTION = "Base instruction."


@pytest.fixture(autouse=True)
def no_remote_mcp_discovery():
    with patch("dak_agent.remote_tools.discover_remote_tools", AsyncMock(return_value={})):
        yield


def _recording_llm():
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse

    requests = []

    class RecordingLlm(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            requests.append(llm_request)
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="ok")]))

    return RecordingLlm(model="recording"), requests


def _app(llm):
    from google.adk.apps import App

    from dak_agent.adaptive_agent import AdaptiveAgent

    agent = AdaptiveAgent(model=llm, name="dak_agent", instruction=DEFAULT_INSTRUCTION, tools=[])
    agent.skill_registry = MagicMock(spec=SkillRegistry)
    agent.skill_registry.get_skill.return_value = None
    agent.skill_registry.list_skills.return_value = []
    return App(name="dak_agent", root_agent=agent)


async def _run(app, sessions, session_id, state_delta=None):
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.runners import Runner

    runner = Runner(app=app, session_service=sessions, artifact_service=InMemoryArtifactService())
    async for _ in runner.run_async(
        user_id="u", session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text="hi")]),
        state_delta=state_delta,
    ):
        pass


def _system(llm_request) -> str:
    return llm_request.config.system_instruction or ""


def _agent_instruction(system: str) -> str:
    """ADK appends its own identity line ("You are an agent. Your internal
    name is ...") after the agent's instruction, whatever that instruction
    is; strip it to compare the instruction itself."""
    return system.split("\n\nYou are an agent.", 1)[0]


@pytest.mark.asyncio
async def test_call_instruction_replaces_system_prompt_for_that_session_only():
    from google.adk.sessions import InMemorySessionService

    llm, requests = _recording_llm()
    app = _app(llm)
    sessions = InMemorySessionService()
    with_call = await sessions.create_session(app_name="dak_agent", user_id="u")
    without_call = await sessions.create_session(app_name="dak_agent", user_id="u")

    await _run(app, sessions, with_call.id, state_delta={"dak:instruction": "Answer in one word."})
    await _run(app, sessions, without_call.id)

    assert _agent_instruction(_system(requests[0])) == "Answer in one word."
    assert _agent_instruction(_system(requests[1])) == DEFAULT_INSTRUCTION


@pytest.mark.asyncio
async def test_call_instruction_reaches_the_model_verbatim():
    """`{name}` is ADK's session-state placeholder syntax; the caller's text
    must not be run through it (an unknown name would fail the turn)."""
    from google.adk.sessions import InMemorySessionService

    llm, requests = _recording_llm()
    app = _app(llm)
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name="dak_agent", user_id="u")

    text = "Return {date} as YYYY-MM-DD."
    await _run(app, sessions, session.id, state_delta={"dak:instruction": text})

    assert _agent_instruction(_system(requests[0])) == text
