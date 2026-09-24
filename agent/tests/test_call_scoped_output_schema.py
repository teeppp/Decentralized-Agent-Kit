"""PBI #137 acceptance criterion 2 (request side): a `dak:output_schema`
passed with a call puts a structured-output spec on that call's LLM request.
Same `Runner` + recording `BaseLlm` technique as
`test_call_scoped_instruction.py`."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types

from dak_agent.skill_registry import SkillRegistry

SCHEMA = {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]}


@pytest.fixture(autouse=True)
def no_remote_mcp_discovery():
    with patch("dak_agent.remote_tools.discover_remote_tools", AsyncMock(return_value={})):
        yield


def _recording_llm():
    from google.adk.models._capabilities import LlmCapabilities
    from google.adk.models.base_llm import BaseLlm
    from google.adk.models.llm_response import LlmResponse

    requests = []

    class RecordingLlm(BaseLlm):
        @property
        def capabilities(self) -> LlmCapabilities:
            # What DAK's LiteLlm reports: structured output alongside tools.
            return LlmCapabilities(output_schema_and_tools=True)

        async def generate_content_async(self, llm_request, stream=False):
            requests.append(llm_request)
            yield LlmResponse(content=types.Content(
                role="model", parts=[types.Part(text='{"date": "2026-09-22"}')]))

    return RecordingLlm(model="recording"), requests


def _app(llm):
    from google.adk.apps import App

    from dak_agent.adaptive_agent import AdaptiveAgent

    agent = AdaptiveAgent(model=llm, name="dak_agent", instruction="Base instruction.", tools=[])
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


@pytest.mark.asyncio
async def test_call_output_schema_sets_structured_output_on_that_session_only():
    from google.adk.sessions import InMemorySessionService

    llm, requests = _recording_llm()
    app = _app(llm)
    sessions = InMemorySessionService()
    with_schema = await sessions.create_session(app_name="dak_agent", user_id="u")
    without_schema = await sessions.create_session(app_name="dak_agent", user_id="u")

    await _run(app, sessions, with_schema.id, state_delta={"dak:output_schema": SCHEMA})
    await _run(app, sessions, without_schema.id)

    config = requests[0].config
    assert config.response_mime_type == "application/json"
    schema = config.response_schema
    schema = schema if isinstance(schema, dict) else schema.model_dump(exclude_none=True)
    assert schema["required"] == ["date"]
    assert "date" in schema["properties"]

    assert requests[1].config.response_schema is None
    assert requests[1].config.response_mime_type is None
