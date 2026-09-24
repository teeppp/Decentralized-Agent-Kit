"""PBI #137 acceptance criteria 2 and 3: a `dak:output_schema` passed with a
call puts a structured-output spec on that call's LLM request, and a reply
that does not match it comes back as a structured failure.
Same `Runner` + recording `BaseLlm` technique as
`test_call_scoped_instruction.py`."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types

from dak_agent.skill_registry import SkillRegistry

SCHEMA = {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]}


@pytest.fixture(autouse=True)
def no_remote_mcp_discovery():
    with patch("dak_agent.remote_tools.discover_remote_tools", AsyncMock(return_value={})):
        yield


def _recording_llm(reply='{"date": "2026-09-22"}'):
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
                role="model", parts=[types.Part(text=reply)]))

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
    """Returns the texts of the events the call produced."""
    from google.adk.artifacts import InMemoryArtifactService
    from google.adk.runners import Runner

    runner = Runner(app=app, session_service=sessions, artifact_service=InMemoryArtifactService())
    texts = []
    async for event in runner.run_async(
        user_id="u", session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text="hi")]),
        state_delta=state_delta,
    ):
        for part in (event.content.parts if event.content else []) or []:
            if part.text:
                texts.append(part.text)
    return texts


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


@pytest.mark.asyncio
async def test_reply_not_matching_output_schema_becomes_structured_failure():
    from google.adk.sessions import InMemorySessionService

    llm, _ = _recording_llm(reply='{"note": "missing date"}')
    app = _app(llm)
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name="dak_agent", user_id="u")

    texts = await _run(app, sessions, session.id, state_delta={"dak:output_schema": SCHEMA})

    failure = json.loads(texts[-1])
    assert failure["error"] == "output_schema_validation_failed"
    assert [i["path"] for i in failure["issues"]] == ["date"]


@pytest.mark.asyncio
async def test_reply_matching_output_schema_is_returned_unchanged():
    from google.adk.sessions import InMemorySessionService

    llm, _ = _recording_llm(reply='{"date": "2026-09-22"}')
    app = _app(llm)
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name="dak_agent", user_id="u")

    texts = await _run(app, sessions, session.id, state_delta={"dak:output_schema": SCHEMA})

    assert texts[-1] == '{"date": "2026-09-22"}'


@pytest.mark.asyncio
async def test_reply_without_output_schema_is_not_validated():
    from google.adk.sessions import InMemorySessionService

    llm, _ = _recording_llm(reply="plain text, not JSON")
    app = _app(llm)
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name="dak_agent", user_id="u")

    assert (await _run(app, sessions, session.id))[-1] == "plain text, not JSON"


@pytest.mark.asyncio
async def test_empty_output_schema_still_requires_json():
    """`{}` accepts any JSON value, but a non-JSON reply must still fail."""
    from google.adk.sessions import InMemorySessionService

    llm, _ = _recording_llm(reply="plain text, not JSON")
    app = _app(llm)
    sessions = InMemorySessionService()
    session = await sessions.create_session(app_name="dak_agent", user_id="u")

    texts = await _run(app, sessions, session.id, state_delta={"dak:output_schema": {}})

    assert json.loads(texts[-1])["error"] == "output_schema_validation_failed"


class TestReplyEligibility:
    """Only a complete, final text reply is validated (`_check_call_output`)."""

    def _check(self, response, schema=SCHEMA):
        from dak_agent.adaptive_agent import AdaptiveAgent

        agent = AdaptiveAgent(model="test-model", name="dak_agent", instruction="x", tools=[])
        with patch("dak_agent.call_config.resolve_dak_settings", return_value={"dak:output_schema": schema}):
            return agent._check_call_output(response, MagicMock())

    @staticmethod
    def _response(*parts, partial=None):
        from google.adk.models.llm_response import LlmResponse

        return LlmResponse(content=types.Content(role="model", parts=list(parts)), partial=partial)

    def test_tool_call_turn_is_not_validated(self):
        call = types.Part(function_call=types.FunctionCall(name="t", args={}))
        assert self._check(self._response(types.Part(text="let me look"), call)) is None

    def test_partial_stream_chunk_is_not_validated(self):
        assert self._check(self._response(types.Part(text='{"da'), partial=True)) is None

    def test_thought_text_is_left_out(self):
        reply = self._response(types.Part(text="thinking...", thought=True),
                               types.Part(text='{"date": "2026-09-22"}'))
        assert self._check(reply) is None

    def test_validation_error_fails_closed(self):
        """An unexpected error while validating must not let the reply through."""
        with patch("dak_agent.call_config.validate_call_output", side_effect=RuntimeError("boom")):
            failure = self._check(self._response(types.Part(text='{"date": "x"}')))
        assert json.loads(failure.content.parts[0].text)["error"] == "output_schema_validation_failed"
