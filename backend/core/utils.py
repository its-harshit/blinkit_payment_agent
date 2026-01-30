"""Shared utilities for MCP tool result parsing."""
import json
from typing import Any


def parse_mcp_text_result(result: dict, key: str | None = None) -> Any:
    """Parse MCP tools/call result: content[0].text as JSON.
    If key is set, return data[key]; otherwise return the full parsed data.
    Raises ValueError if result is missing content or text.
    """
    if not result or "content" not in result or not result["content"]:
        raise ValueError("MCP result missing content")
    raw = result["content"][0].get("text")
    if raw is None:
        raise ValueError("MCP result content missing text")
    data = json.loads(raw)
    return data.get(key) if key is not None else data
