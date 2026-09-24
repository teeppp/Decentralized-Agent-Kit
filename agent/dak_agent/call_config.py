"""Per-call settings: the `dak:` keys a caller passes with a single call.

A caller can pass them as `/run`'s `state_delta` (they land in the session
state) or as A2A message metadata (ADK's A2A request converter puts that under
`RunConfig.custom_metadata["a2a_metadata"]`). Later PBIs add more `dak:` keys
to this module.
"""
import json
from typing import Any, Dict, List, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

DAK_PREFIX = "dak:"
STATE_CALL_INSTRUCTION = "dak:instruction"
STATE_CALL_OUTPUT_SCHEMA = "dak:output_schema"  # JSON Schema (dict)
# Same value as google.adk.a2a.converters.request_converter.A2A_METADATA_KEY.
A2A_METADATA_KEY = "a2a_metadata"


def _dak_keys(source: Any) -> Dict[str, Any]:
    if not isinstance(source, Mapping):
        return {}
    return {k: v for k, v in source.items() if isinstance(k, str) and k.startswith(DAK_PREFIX)}


def resolve_dak_settings(callback_context) -> Dict[str, Any]:
    """Collect this call's `dak:` settings. Precedence (low → high):
    `run_config.custom_metadata`, its nested A2A metadata, session state."""
    try:
        run_config = callback_context._invocation_context.run_config
    except AttributeError:
        run_config = None
    custom_metadata = getattr(run_config, "custom_metadata", None) or {}

    settings: Dict[str, Any] = {}
    settings.update(_dak_keys(custom_metadata))
    if isinstance(custom_metadata, Mapping):
        settings.update(_dak_keys(custom_metadata.get(A2A_METADATA_KEY)))
    state = callback_context.state
    # ADK's `State` is not a Mapping; `to_dict()` merges the committed value
    # with this invocation's pending delta.
    settings.update(_dak_keys(state.to_dict() if hasattr(state, "to_dict") else state))
    return settings


def _issue_path(error) -> str:
    """"/"-joined path of the offending value. A missing required property is
    reported by jsonschema on its parent object; name the property itself."""
    path = [str(p) for p in error.absolute_path]
    if error.validator == "required":
        missing = [p for p in error.validator_value if error.message.startswith(repr(p))]
        path += missing[:1]
    return "/".join(path)


def validate_call_output(schema: Dict[str, Any], text: str) -> Tuple[Optional[Any], List[Dict[str, str]]]:
    """Check a final model reply against the call's `dak:output_schema`.
    Returns `(parsed_json, [])` on success, `(None, issues)` otherwise, each
    issue being `{"path": "a/b", "message": "..."}`."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return None, [{"path": "", "message": f"invalid output_schema: {exc.message}"}]
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        return None, [{"path": "", "message": f"invalid JSON: {exc}"}]
    errors = sorted(Draft202012Validator(schema).iter_errors(parsed), key=lambda e: [str(p) for p in e.absolute_path])
    if errors:
        return None, [{"path": _issue_path(e), "message": e.message} for e in errors]
    return parsed, []
