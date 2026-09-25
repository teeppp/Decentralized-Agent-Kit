"""make_complete: OpenAI-compatible HTTP (MAINT_LLM_BASE_URL) or Amazon Bedrock
with IAM credentials (MAINT_LLM_MODEL=bedrock/<model or inference profile>)."""
import sys
import types

import pytest

from dak_maintenance import llm_client


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ("MAINT_LLM_BASE_URL", "MAINT_LLM_MODEL", "MAINT_LLM_API_KEY", "AWS_REGION", "AWS_DEFAULT_REGION"):
        monkeypatch.delenv(key, raising=False)


def test_unconfigured_returns_none():
    assert llm_client.make_complete() is None


def test_openai_compatible_needs_a_base_url(monkeypatch):
    monkeypatch.setenv("MAINT_LLM_MODEL", "gemini-3.5-flash")
    assert llm_client.make_complete() is None


class FakeBedrock:
    def __init__(self):
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": {"message": {"role": "assistant", "content": [
            {"reasoningContent": {"reasoningText": {"text": "thinking"}}},
            {"text": '[{"title": "x"}]'}]}}}


@pytest.fixture
def fake_boto3(monkeypatch):
    client = FakeBedrock()
    made = {}

    def make_client(service, **kwargs):
        made.update(service=service, **kwargs)
        return client

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=make_client))
    return client, made


def test_bedrock_model_uses_converse_with_iam_credentials(monkeypatch, fake_boto3):
    client, made = fake_boto3
    monkeypatch.setenv("MAINT_LLM_MODEL", "bedrock/global.openai.gpt-6-luna")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("MAINT_LLM_API_KEY", "must-not-be-used")

    complete = llm_client.make_complete()
    text = complete("hello")

    assert text == '[{"title": "x"}]'  # reasoning blocks are not part of the answer
    assert made["service"] == "bedrock-runtime" and made["region_name"] == "us-west-2"
    call = client.calls[0]
    assert call["modelId"] == "global.openai.gpt-6-luna"
    assert call["messages"] == [{"role": "user", "content": [{"text": "hello"}]}]
    assert "must-not-be-used" not in repr(made) + repr(call)  # IAM (SigV4), not the API key


def test_bedrock_region_defaults_to_us_east_1(monkeypatch, fake_boto3):
    _, made = fake_boto3
    monkeypatch.setenv("MAINT_LLM_MODEL", "bedrock/global.openai.gpt-6-luna")
    llm_client.make_complete()("hi")
    assert made["region_name"] == "us-east-1"


def test_bedrock_does_not_need_a_base_url(monkeypatch, fake_boto3):
    monkeypatch.setenv("MAINT_LLM_MODEL", "bedrock/global.openai.gpt-6-luna")
    assert llm_client.make_complete() is not None
