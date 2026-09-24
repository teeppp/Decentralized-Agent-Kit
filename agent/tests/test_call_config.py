from types import SimpleNamespace

from google.adk.sessions.state import State

from dak_agent import call_config


def _context(state=None, custom_metadata=None):
    run_config = SimpleNamespace(custom_metadata=custom_metadata)
    return SimpleNamespace(
        state=State(value=dict(state or {}), delta={}),
        _invocation_context=SimpleNamespace(run_config=run_config),
    )


def test_resolve_dak_settings_prefers_state_over_custom_metadata():
    ctx = _context(
        state={"dak:instruction": "from state", "other": "ignored"},
        custom_metadata={
            "dak:instruction": "from custom_metadata",
            "a2a_metadata": {"dak:instruction": "from a2a"},
        },
    )

    assert call_config.resolve_dak_settings(ctx) == {"dak:instruction": "from state"}


def test_resolve_dak_settings_reads_a2a_metadata():
    ctx = _context(custom_metadata={"a2a_metadata": {"dak:instruction": "from a2a", "trace": "x"}})

    assert call_config.resolve_dak_settings(ctx) == {"dak:instruction": "from a2a"}


def test_resolve_dak_settings_reads_output_schema():
    schema = {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]}
    ctx = _context(state={call_config.STATE_CALL_OUTPUT_SCHEMA: schema})

    assert call_config.resolve_dak_settings(ctx)["dak:output_schema"] == schema


def test_resolve_dak_settings_without_run_config_reads_state_only():
    ctx = SimpleNamespace(state=State(value={"dak:instruction": "s"}, delta={}))

    assert call_config.resolve_dak_settings(ctx) == {"dak:instruction": "s"}
