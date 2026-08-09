"""Feeds the control panel so the projector has something to show.

A waiting agent renders as nothing at all, and a blank screen for forty seconds
loses the room. This plugin narrates every tool call to the venue's activity
feed, which is also a working demo of ADK's plugin hooks.
"""

from __future__ import annotations

from typing import Any

import httpx
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools import BaseTool, ToolContext

from . import venue


def _emit(kind: str, message: str, detail: dict | None = None) -> None:
    try:
        httpx.post(
            f"{venue.VENUE_URL}/admin/agent-event",
            json={"kind": kind, "message": message, "detail": detail},
            timeout=2,
        )
    except httpx.HTTPError:
        pass  # the panel is a nicety; never let it break a run


class PanelPlugin(BasePlugin):
    """Narrates tool calls to the venue control panel."""

    def __init__(self) -> None:
        super().__init__(name="panel")

    async def before_tool_callback(
        self, *, tool: BaseTool, tool_args: dict[str, Any], tool_context: ToolContext
    ) -> None:
        _emit("agent", f"calling {tool.name}", {"args": _short(tool_args)})
        return None

    async def after_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
        result: dict,
    ) -> None:
        if isinstance(result, dict) and result.get("error"):
            _emit("error", f"{tool.name} failed: {result.get('message', '')[:80]}")
        else:
            _emit("agent", f"{tool.name} returned")
        return None


def _short(args: dict) -> dict:
    return {k: (str(v)[:60]) for k, v in list(args.items())[:4]}
