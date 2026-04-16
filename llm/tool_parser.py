"""Parse LLM responses into text + tool calls.

Supports both Ollama (dict-based) and legacy Anthropic (object-based) formats.
"""
import uuid
from typing import Any, Dict, List, Tuple


def parse_tool_calls(response: Any) -> Tuple[str, List[dict]]:
    """
    Walk an LLM response and split it into:
    - assistant text
    - structured tool_use calls (normalized to AURIX shape)

    Handles:
      - Ollama dict: {"message": {"content": ..., "tool_calls": [...]}}
      - Anthropic Message object: response.content = [TextBlock, ToolUseBlock, ...]
    """
    # ── Ollama dict format ──────────────────────────────────────────────
    if isinstance(response, dict):
        msg = response.get("message", {})
        text = msg.get("content", "") or ""
        raw_calls = msg.get("tool_calls") or []
        tool_calls = [_normalize_ollama_call(c) for c in raw_calls]
        return text, tool_calls

    # ── Anthropic object format (legacy) ────────────────────────────────
    text_response = ""
    tool_calls: List[dict] = []

    for block in getattr(response, "content", []) or []:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text_response += getattr(block, "text", "")
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "id": getattr(block, "id", None),
                    "tool": getattr(block, "name", None),
                    "params": getattr(block, "input", {}) or {},
                }
            )

    return text_response, tool_calls


def _normalize_ollama_call(raw: Any) -> Dict[str, Any]:
    """Convert a single Ollama tool_call into AURIX's normalized shape."""
    if isinstance(raw, dict):
        fn = raw.get("function", {}) or {}
        name = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", None)
        args = fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", None)
        call_id = raw.get("id")
    else:
        fn = getattr(raw, "function", None)
        name = getattr(fn, "name", None) if fn else None
        args = getattr(fn, "arguments", None) if fn else None
        call_id = getattr(raw, "id", None)

    if args is None:
        args = {}
    if isinstance(args, str):
        import json
        try:
            args = json.loads(args)
        except Exception:
            args = {"_raw": args}

    return {
        "id": call_id or f"call_{uuid.uuid4().hex[:12]}",
        "tool": name,
        "params": args or {},
    }
