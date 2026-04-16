"""Tool execution orchestrator."""
import asyncio
import inspect
from typing import Any, Awaitable, Callable, Dict, List, Optional

from utils.error_handler import ToolExecutionError
from utils.logger import get_logger

from tools import (
    app_control, browser_automation, file_system, media_control,
    calendar_reminders, weather, system_info, web_search, notes, timer,
    macro, gmail, system_control,
)

# Params the LLM sometimes sends that should be remapped to the canonical kwarg.
_PARAM_ALIASES: Dict[str, Dict[str, str]] = {
    "open_application": {
        "query": "app_name", "app": "app_name", "name": "app_name",
        "application": "app_name", "application_name": "app_name",
    },
    "close_application": {
        "query": "app_name", "app": "app_name", "name": "app_name",
        "application": "app_name", "application_name": "app_name",
    },
}

logger = get_logger(__name__)


class ToolExecutor:
    """
    Routes tool calls from the LLM to concrete handlers.
    Holds lazy references so unused integrations don't pay startup cost.
    """

    def __init__(self) -> None:
        self.handlers: Dict[str, Callable[..., Awaitable[Any]]] = {
            "open_application": app_control.open_application,
            "close_application": app_control.close_application,
            "search_youtube": browser_automation.search_youtube,
            "control_media": media_control.control_media,
            "file_search": file_system.file_search,
            "delete_file": file_system.delete_file,
            "create_reminder": calendar_reminders.create_reminder,
            "get_weather": weather.get_weather,
            "get_system_info": system_info.get_system_info,
            "web_search": web_search.web_search,
            "local_file_search": web_search.local_file_search,
            "create_note": notes.create_note,
            "read_note": notes.read_note,
            "list_notes": notes.list_notes,
            "set_timer": timer.set_timer,
            "cancel_timer": timer.cancel_timer,
            "start_recording": macro.start_recording,
            "stop_recording": macro.stop_recording,
            "play_macro": macro.play_macro,
            "list_macros": macro.list_macros,
            "delete_macro": macro.delete_macro,
            "check_unread_count": gmail.check_unread_count,
            "get_recent_emails": gmail.get_recent_emails,
            "send_email": gmail.send_email,
            "search_emails": gmail.search_emails,
            "shutdown_aurix": system_control.shutdown_aurix,
        }

    async def execute_tools(
        self,
        tool_calls: List[dict],
        state: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute a list of tool calls. Returns aggregated result dict."""
        results: List[Dict[str, Any]] = []
        all_success = True

        for call in tool_calls:
            tool_name = call.get("tool")
            params = call.get("params", {}) or {}

            if state is not None and state.should_skip_action(call):
                logger.info(f"Skipping redundant action: {tool_name}")
                results.append({"tool": tool_name, "skipped": True, "success": True})
                continue

            try:
                result = await self._invoke(tool_name, params)
                results.append({"tool": tool_name, "result": result, "success": True})
            except ToolExecutionError as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                results.append({"tool": tool_name, "error": str(e), "success": False})
                all_success = False
            except Exception as e:
                logger.exception(f"Unexpected tool error in {tool_name}")
                results.append({"tool": tool_name, "error": str(e), "success": False})
                all_success = False

        summary = ", ".join(
            f"{r['tool']}={'ok' if r['success'] else 'fail'}" for r in results
        )
        return {"results": results, "success": all_success, "summary": summary}

    async def execute_sequence(self, sequence: List[str]) -> Dict[str, Any]:
        """Execute a serialized macro sequence (each entry is "tool: params")."""
        calls = []
        for entry in sequence or []:
            if ":" in entry:
                tool, _, _ = entry.partition(":")
                calls.append({"tool": tool.strip(), "params": {}})
        return await self.execute_tools(calls)

    async def _invoke(self, tool_name: Optional[str], params: dict) -> Any:
        if not tool_name or tool_name not in self.handlers:
            raise ToolExecutionError(f"Unknown tool: {tool_name}")
        handler = self.handlers[tool_name]
        params = self._sanitize_params(tool_name, handler, params)
        result = handler(**params)
        if asyncio.iscoroutine(result):
            return await result
        return result

    @staticmethod
    def _sanitize_params(tool_name: str, handler: Callable, params: dict) -> dict:
        """Remap LLM-provided aliases and drop kwargs the handler doesn't accept."""
        aliases = _PARAM_ALIASES.get(tool_name, {})
        remapped: Dict[str, Any] = {}
        for k, v in (params or {}).items():
            remapped[aliases.get(k, k)] = v

        try:
            sig = inspect.signature(handler)
        except (TypeError, ValueError):
            return remapped

        accepted = {
            name for name, p in sig.parameters.items()
            if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
        }
        accepts_var_kw = any(
            p.kind == p.VAR_KEYWORD for p in sig.parameters.values()
        )
        if accepts_var_kw:
            return remapped

        cleaned = {k: v for k, v in remapped.items() if k in accepted}
        dropped = set(remapped) - set(cleaned)
        if dropped:
            logger.debug(f"{tool_name}: dropped unsupported params {sorted(dropped)}")
        return cleaned
