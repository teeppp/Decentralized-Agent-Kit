"""Per-call settings: the `dak:` keys a caller passes with a single call.

A caller can pass them as `/run`'s `state_delta` (they land in the session
state) or as A2A message metadata (ADK's A2A request converter puts that under
`RunConfig.custom_metadata["a2a_metadata"]`). Later PBIs add more `dak:` keys
to this module.
"""
from typing import Any, Dict, Mapping

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
