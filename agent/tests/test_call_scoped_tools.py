"""PBI #136: `dak:tools` chooses the tools of a call. Drives a real ADK
`Runner` (same technique as `test_call_scoped_instruction.py`) and inspects
the tool declarations on the recorded `LlmRequest`s."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types

from dak_agent.skill_registry import SkillRegistry


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
    from google.adk.tools import FunctionTool

    from dak_agent.adaptive_agent import AdaptiveAgent
    from dak_agent.builtin_tools import switch_mode

    agent = AdaptiveAgent(model=llm, name="dak_agent", instruction="Base.", tools=[FunctionTool(switch_mode)])
    agent.skill_registry = MagicMock(spec=SkillRegistry)
    agent.skill_registry.get_skill.return_value = None
    agent.skill_registry.list_skills.return_value = []
    return App(name="dak_agent", root_agent=agent)


async def _declared_tools(state_delta=None):
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    llm, requests = _recording_llm()
    app = _app(llm)
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name="dak_agent", user_id="u")
    runner = Runner(app=app, session_service=sessions, artifact_service=InMemoryArtifactService())
    async for _ in runner.run_async(
        user_id="u", session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="hi")]),
        state_delta=state_delta,
    ):
        pass
    config_tools = requests[0].config.tools or []
    declared = [d.name for tool in config_tools for d in (tool.function_declarations or [])]
    assert sorted(declared) == sorted(requests[0].tools_dict)  # both views agree
    return declared


@pytest.mark.asyncio
async def test_empty_call_tools_sends_no_tool_declarations():
    assert await _declared_tools({"dak:tools": []}) == []


@pytest.mark.asyncio
async def test_call_tools_subset_sends_only_the_named_tools():
    assert await _declared_tools({"dak:tools": ["switch_mode"]}) == ["switch_mode"]


@pytest.mark.asyncio
async def test_without_call_tools_the_built_in_tools_are_sent_as_before():
    declared = await _declared_tools()
    assert {"switch_mode", "list_skills", "enable_skill"} <= set(declared)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["switch_mode", 3, ["switch_mode", 1], {"other": 1}])
async def test_malformed_call_tools_is_refused_without_calling_the_llm(bad):
    """A caller that asked for a restriction must not silently get every tool."""
    import json

    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    llm, requests = _recording_llm()
    app = _app(llm)
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name="dak_agent", user_id="u")
    runner = Runner(app=app, session_service=sessions, artifact_service=InMemoryArtifactService())
    texts = []
    async for event in runner.run_async(
        user_id="u", session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="hi")]),
        state_delta={"dak:tools": bad},
    ):
        texts += [p.text for p in (event.content.parts if event.content else []) if p.text]

    assert requests == []
    assert json.loads(texts[-1])["error"] == "invalid_tools"
