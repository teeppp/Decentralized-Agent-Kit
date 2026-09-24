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


DATE_SCHEMA = {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]}


def test_validate_call_output_returns_field_path_and_reason():
    parsed, issues = call_config.validate_call_output(DATE_SCHEMA, '{"note": "missing date"}')

    assert parsed is None
    assert len(issues) == 1
    assert issues[0]["path"] == "date"
    assert "required" in issues[0]["message"]


def test_validate_call_output_reports_nested_path():
    schema = {"type": "object", "properties": {"trip": {"type": "object", "required": ["to"], "properties": {
        "days": {"type": "integer"}, "to": {"type": "string"}}}}}

    _, issues = call_config.validate_call_output(schema, '{"trip": {"days": "three"}}')

    assert sorted(i["path"] for i in issues) == ["trip/days", "trip/to"]


def test_validate_call_output_accepts_matching_json():
    assert call_config.validate_call_output(DATE_SCHEMA, '{"date": "2026-09-22"}') == ({"date": "2026-09-22"}, [])


def test_validate_call_output_reports_invalid_json():
    parsed, issues = call_config.validate_call_output(DATE_SCHEMA, "not json")

    assert parsed is None
    assert issues[0]["path"] == ""
    assert issues[0]["message"].startswith("invalid JSON:")


def test_validate_call_output_reports_invalid_schema():
    parsed, issues = call_config.validate_call_output({"type": "no-such-type"}, "{}")

    assert parsed is None
    assert issues[0]["message"].startswith("invalid output_schema:")


def test_validate_call_output_resolves_local_refs():
    schema = {"$defs": {"d": {"type": "string"}}, "type": "object",
              "properties": {"date": {"$ref": "#/$defs/d"}}}

    assert call_config.validate_call_output(schema, '{"date": "x"}') == ({"date": "x"}, [])
    assert call_config.validate_call_output(schema, '{"date": 1}')[1][0]["path"] == "date"


def test_validate_call_output_reports_unresolvable_ref():
    parsed, issues = call_config.validate_call_output({"$ref": "#/$defs/missing"}, "{}")

    assert parsed is None
    assert issues[0]["message"].startswith("invalid output_schema:")


def test_validate_call_output_never_fetches_remote_refs():
    """A caller-supplied schema must not make the agent fetch URLs (SSRF)."""
    from unittest.mock import patch

    with patch("urllib.request.urlopen", side_effect=AssertionError("fetched a remote $ref")) as urlopen:
        parsed, issues = call_config.validate_call_output(
            {"$ref": "http://169.254.169.254/latest/meta-data/"}, "{}")

    urlopen.assert_not_called()
    assert parsed is None
    assert issues[0]["message"].startswith("invalid output_schema:")
