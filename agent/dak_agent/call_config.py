"""Per-call settings: the `dak:` keys a caller passes with a single call.

A caller can pass them as `/run`'s `state_delta` (they land in the session
state) or as A2A message metadata (ADK's A2A request converter puts that under
`RunConfig.custom_metadata["a2a_metadata"]`). Later PBIs add more `dak:` keys
to this module.
"""
import json
import os
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema_specifications import REGISTRY as METASCHEMAS

DAK_PREFIX = "dak:"
STATE_CALL_INSTRUCTION = "dak:instruction"
STATE_CALL_OUTPUT_SCHEMA = "dak:output_schema"  # JSON Schema (dict)
# Tools for this call. A list of names: only those built-in tools and those
# names from the default MCP server; [] means no tools at all.
STATE_CALL_TOOLS = "dak:tools"
STATE_CALL_MODEL = "dak:model"  # LiteLLM model id, e.g. "bedrock/openai.gpt-5.6-luna"
# Operator's allow-list for `dak:model` (comma-separated model ids). Unset
# means no caller may pick a model: callers cannot exceed the operator's
# cost limits unless the operator opens that door explicitly.
ALLOWED_MODELS_ENV = "DAK_ALLOWED_MODELS"
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


def resolve_allowed_models() -> Optional[FrozenSet[str]]:
    """The operator's allow-list, or None when `DAK_ALLOWED_MODELS` is unset."""
    raw = os.environ.get(ALLOWED_MODELS_ENV)
    if raw is None:
        return None
    return frozenset(m.strip() for m in raw.split(",") if m.strip())


def resolve_model_selection(
    call_settings: Dict[str, Any], default_model_name: str
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """The model this call runs on, and an error dict when the caller asked
    for a model the operator does not allow (the call must then not reach
    any LLM)."""
    requested = call_settings.get(STATE_CALL_MODEL)
    if requested is None:
        return default_model_name, None
    allowed = resolve_allowed_models()
    if allowed is None or not isinstance(requested, str) or requested not in allowed:
        return default_model_name, {
            "error": "model_not_allowed",
            "requested_model": requested,
            "allowed_models": sorted(allowed or []),
        }
    return requested, None


def _issue_path(error) -> str:
    """"/"-joined path of the offending value. A missing required property is
    reported by jsonschema on its parent object; name the property itself."""
    path = [str(p) for p in error.absolute_path]
    if error.validator == "required":
        missing = [p for p in error.validator_value if error.message.startswith(repr(p))]
        path += missing[:1]
    return "/".join(path)


def _reject_constant(name: str):
    """Python's json accepts NaN/Infinity; standard JSON does not."""
    raise ValueError(f"{name} is not valid JSON")


def validate_call_output(schema: Dict[str, Any], text: str) -> Tuple[Optional[Any], List[Dict[str, str]]]:
    """Check a final model reply against the call's `dak:output_schema`.
    Returns `(parsed_json, [])` on success, `(None, issues)` otherwise, each
    issue being `{"path": "a/b", "message": "..."}`."""
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        return None, [{"path": "", "message": f"invalid output_schema: {exc.message}"}]
    try:
        parsed = json.loads(text, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as exc:  # RecursionError: absurdly deep nesting
        return None, [{"path": "", "message": f"invalid JSON: {exc}"}]
    # The schema comes from the caller. jsonschema's default registry fetches
    # remote `$ref` URLs; this one only knows the bundled metaschemas, so a
    # remote ref is unresolvable instead of a request from this container.
    validator = Draft202012Validator(schema, registry=METASCHEMAS)
    try:
        errors = sorted(validator.iter_errors(parsed), key=lambda e: [str(p) for p in e.absolute_path])
    except Exception as exc:  # unresolvable $ref and the like
        return None, [{"path": "", "message": f"invalid output_schema: {exc}"}]
    if errors:
        return None, [{"path": _issue_path(e), "message": e.message} for e in errors]
    return parsed, []
