"""LLM integration with hybrid fast/smart routing (Ollama backend).

The class is still named ClaudeInterface for back-compat with the rest of
AURIX — only the underlying provider has changed from Anthropic to a local
Ollama daemon. No API key is needed; Ollama must be running on localhost.
"""
import asyncio
import re
import uuid
from typing import Any, Dict, List, Optional

import ollama

from llm.prompt_builder import PromptBuilder
from utils.logger import get_logger

logger = get_logger(__name__)


# Fast path: simple commands ("open chrome", "play music").
FAST_MODEL = "llama3.2:3b"
# Smart path: multi-step reasoning. llama3.2:1b supports tool calling.
SMART_MODEL = "llama3.2:1b"


class ComplexityDetector:
    """
    Cheap heuristic that decides whether a command should escalate to the
    smart model. Runs locally — no API call — so it adds ~microseconds.

    Signals that escalate:
      - Reasoning verbs: explain, why, how come, analyze, compare, plan, decide,
        figure out, research, summarize, design, debug, troubleshoot
      - Multi-step connectives: "and then", "after that", "first ... then ..."
      - Long utterances (>15 words) — usually means a non-trivial request
      - Code / writing tasks: "write", "draft", "code", "refactor"

    Signals that stay fast (override length):
      - Pure action verbs: open, close, launch, start, stop, play, pause, mute,
        skip, next, previous, volume, search, find, show
    """

    REASONING_PATTERNS = (
        r"\b(explain|analy[sz]e|compare|reason|figure\s+out|decide|research|"
        r"summari[sz]e|design|debug|troubleshoot|plan|brainstorm|recommend|"
        r"evaluate|investigate)\b"
    )
    QUESTION_PATTERNS = r"\b(why|how\s+come|what\s+if|should\s+i|which\s+one)\b"
    MULTISTEP_PATTERNS = (
        r"\b(and\s+then|after\s+that|first.*then|step\s+by\s+step|"
        r"one\s+by\s+one|in\s+order)\b"
    )
    AUTHOR_PATTERNS = r"\b(write|draft|compose|code|refactor|generate|rewrite)\b"

    SIMPLE_ACTIONS = {
        "open", "close", "launch", "quit", "exit", "start", "stop",
        "play", "pause", "resume", "mute", "unmute",
        "skip", "next", "previous", "back",
        "volume", "louder", "quieter",
        "search", "find", "show", "hide",
        "minimize", "maximize", "switch",
        "weather", "forecast",
        "cpu", "ram", "disk", "battery", "system",
        "note", "notes", "memo",
        "timer", "alarm", "countdown",
        "check",
        "record", "recording", "macro", "replay",
        "email", "emails", "mail", "inbox", "send", "unread", "read",
        "goodnight", "goodbye", "shutdown", "shut",
    }

    LONG_UTTERANCE_WORDS = 15

    def __init__(self):
        self._reasoning = re.compile(self.REASONING_PATTERNS, re.IGNORECASE)
        self._question = re.compile(self.QUESTION_PATTERNS, re.IGNORECASE)
        self._multistep = re.compile(self.MULTISTEP_PATTERNS, re.IGNORECASE)
        self._author = re.compile(self.AUTHOR_PATTERNS, re.IGNORECASE)

    def is_complex(self, text: str) -> bool:
        if not text:
            return False

        normalized = text.strip().lower()
        words = normalized.split()

        # Strong escalation signals — always smart model
        if self._reasoning.search(normalized):
            return True
        if self._question.search(normalized):
            return True
        if self._multistep.search(normalized):
            return True
        if self._author.search(normalized):
            return True

        # Pure single-action commands stay on the fast path even if long-ish
        if words and words[0] in self.SIMPLE_ACTIONS and len(words) <= 8:
            return False

        # Long utterances default to smart model
        if len(words) > self.LONG_UTTERANCE_WORDS:
            return True

        return False

    def is_actionable(self, text: str) -> bool:
        """Does this look like a system action that needs tool calls?"""
        if not text:
            return False
        words = text.strip().lower().split()
        return any(w in self.SIMPLE_ACTIONS for w in words[:5])

    def pick_model(self, text: str) -> str:
        return SMART_MODEL if self.is_complex(text) else FAST_MODEL


class ClaudeInterface:
    """Local LLM interface (Ollama) for intent understanding and tool generation."""

    DESTRUCTIVE_TOOLS = {"delete_file", "shutdown_system", "close_all_apps", "send_email", "shutdown_aurix"}

    def __init__(
        self,
        fast_model: str = FAST_MODEL,
        smart_model: str = SMART_MODEL,
        host: Optional[str] = None,
    ):
        # ollama.Client() defaults to http://localhost:11434. host kwarg lets
        # tests / configs point at a different daemon if needed.
        self.client = ollama.Client(host=host) if host else ollama.Client()
        self.fast_model = fast_model
        self.smart_model = smart_model
        # Back-compat: callers that read .model still get a sensible value.
        self.model = fast_model
        self.prompt_builder = PromptBuilder()
        self.tools = self._load_tool_definitions()
        self.complexity = ComplexityDetector()

    def _load_tool_definitions(self) -> List[Dict]:
        """Tool definitions in OpenAI / Ollama function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "open_application",
                    "description": "Open or switch to an application",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "app_name": {
                                "type": "string",
                                "description": "Name of the application (chrome, vscode, spotify, etc.)",
                            }
                        },
                        "required": ["app_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_youtube",
                    "description": "Search and play a video on YouTube",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "autoplay": {
                                "type": "boolean",
                                "description": "Automatically play first result",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "control_media",
                    "description": "Control media playback (play, pause, skip, volume)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "play",
                                    "pause",
                                    "next",
                                    "previous",
                                    "volume_up",
                                    "volume_down",
                                ],
                            }
                        },
                        "required": ["action"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "file_search",
                    "description": "Search for files in the file system",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "Name or pattern of file to search for",
                            },
                            "directory": {
                                "type": "string",
                                "description": "Directory to search in (optional)",
                            },
                        },
                        "required": ["filename"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "create_reminder",
                    "description": "Create a reminder or calendar event",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "description": "Reminder message"},
                            "time": {
                                "type": "string",
                                "description": "When to remind (natural language or ISO format)",
                            },
                        },
                        "required": ["message", "time"],
                    },
                },
            },
            # ── Weather ─────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get current weather for a location. Leave location empty for local weather.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "City name or location (e.g. 'London', 'New York'). Empty for auto-detect.",
                            },
                        },
                        "required": [],
                    },
                },
            },
            # ── System info ─────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "get_system_info",
                    "description": "Get current system status: CPU usage, RAM usage, disk space, and battery level.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            # ── Web search ──────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web via Google and return top result summaries. Do NOT use this for email — use check_unread_count or get_recent_emails instead.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query",
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "Number of results to return (default 3)",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            # ── Local file search ───────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "local_file_search",
                    "description": "Search for files on the local computer by name. Use when user says 'search laptop for', 'find file', 'search my computer for'.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Filename or keyword to search for",
                            },
                            "directory": {
                                "type": "string",
                                "description": "Directory to search in (optional, defaults to user home)",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            # ── Notes ───────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "create_note",
                    "description": "Save a quick text note to disk.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "description": "The note text to save",
                            },
                            "title": {
                                "type": "string",
                                "description": "Optional short title for the note",
                            },
                        },
                        "required": ["content"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_note",
                    "description": "Read a specific note by filename or keyword.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "filename": {
                                "type": "string",
                                "description": "Filename or keyword to find the note",
                            },
                        },
                        "required": ["filename"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_notes",
                    "description": "List all saved notes.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            # ── Timer ───────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "set_timer",
                    "description": "Set a countdown timer that alerts with a sound when done.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "duration": {
                                "type": "string",
                                "description": "Duration like '5 minutes', '2m30s', '90 seconds', '1 hour'",
                            },
                            "label": {
                                "type": "string",
                                "description": "Optional label for the timer (e.g. 'pasta', 'break')",
                            },
                        },
                        "required": ["duration"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "cancel_timer",
                    "description": "Cancel an active timer by name.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Name of the timer to cancel",
                            },
                        },
                        "required": ["name"],
                    },
                },
            },
            # ── Macros ──────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "start_recording",
                    "description": "Start recording mouse and keyboard actions as a macro.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "stop_recording",
                    "description": "Stop recording and save the macro with an optional name.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Name for the macro (e.g. 'open_email', 'morning_routine')",
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "play_macro",
                    "description": "Replay a saved macro by name.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Name of the macro to replay",
                            },
                            "speed": {
                                "type": "number",
                                "description": "Playback speed multiplier (1.0 = normal, 2.0 = double speed)",
                            },
                        },
                        "required": ["name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_macros",
                    "description": "List all saved macros.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_macro",
                    "description": "Delete a saved macro by name.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Name of the macro to delete",
                            },
                        },
                        "required": ["name"],
                    },
                },
            },
            # ── Gmail ───────────────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "check_unread_count",
                    "description": "Check Gmail inbox for unread email count, new emails today, and top senders. Use this for: 'check my email', 'any new emails', 'how many unread emails', 'check inbox', 'any unread messages'. This is the PRIMARY tool for all email checking requests.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_recent_emails",
                    "description": "Get summaries of the most recent emails from Gmail (sender, subject, snippet). Use for: 'read my emails', 'show recent emails', 'what emails did I get'.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "count": {
                                "type": "integer",
                                "description": "Number of recent emails to fetch (default 5, max 20)",
                            },
                        },
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "send_email",
                    "description": "Send an email via Gmail.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Recipient email address",
                            },
                            "subject": {
                                "type": "string",
                                "description": "Email subject line",
                            },
                            "body": {
                                "type": "string",
                                "description": "Email body text",
                            },
                        },
                        "required": ["to", "subject", "body"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_emails",
                    "description": "Search emails by keyword or Gmail search syntax (e.g. 'from:john', 'subject:invoice', 'has:attachment').",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (keyword, sender, subject, etc.)",
                            },
                            "count": {
                                "type": "integer",
                                "description": "Max results to return (default 5)",
                            },
                        },
                        "required": ["query"],
                    },
                },
            },
            # ── System control ─────────────────────────────────────────
            {
                "type": "function",
                "function": {
                    "name": "shutdown_aurix",
                    "description": "Shut down AURIX gracefully. Use when the user says goodnight, goodbye, or asks to shut down.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            },
        ]

    def _chat_stream(self, model: str, messages: List[Dict[str, Any]], tools: List[Dict]):
        """Blocking call to ollama — runs inside an executor.

        Returns a tuple (text, tool_calls) where tool_calls is in AURIX's
        normalized shape: [{"id": ..., "tool": ..., "params": ...}, ...].

        We stream so we can accumulate text incrementally; tool_calls are
        emitted by Ollama on the final chunk for tool-capable models.
        """
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        chat_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            chat_kwargs["tools"] = tools

        try:
            stream = self.client.chat(**chat_kwargs)
            for chunk in stream:
                msg = chunk.get("message", {}) if isinstance(chunk, dict) else getattr(chunk, "message", {}) or {}
                # Content can arrive as either dict access or attribute access
                content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
                if content:
                    text_parts.append(content)
                raw_calls = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
                if raw_calls:
                    for raw in raw_calls:
                        tool_calls.append(self._normalize_tool_call(raw))
        except Exception as e:
            logger.error(f"Ollama chat failed on {model}: {e}")
            raise

        return "".join(text_parts), tool_calls

    @staticmethod
    def _normalize_tool_call(raw: Any) -> Dict[str, Any]:
        """Convert an Ollama tool_call into AURIX's normalized shape."""
        # Ollama: {"function": {"name": ..., "arguments": {...}}}
        if isinstance(raw, dict):
            fn = raw.get("function", {}) or {}
            name = fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", None)
            args = fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", None)
            call_id = raw.get("id")
        else:
            fn = getattr(raw, "function", None)
            name = getattr(fn, "name", None) if fn is not None else None
            args = getattr(fn, "arguments", None) if fn is not None else None
            call_id = getattr(raw, "id", None)

        if args is None:
            args = {}
        # Some Ollama builds return arguments as a JSON string — be defensive.
        if isinstance(args, str):
            import json as _json
            try:
                args = _json.loads(args)
            except Exception:
                args = {"_raw": args}

        return {
            "id": call_id or f"call_{uuid.uuid4().hex[:12]}",
            "tool": name,
            "params": args or {},
        }

    async def process_command(
        self,
        user_input: str,
        context: List[Dict[str, str]],
        system_state: str,
        force_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send command to the local LLM and get tool calls.

        Routing:
          - Default: ComplexityDetector picks fast or smart model
          - force_model: pass an explicit model id to override routing
            (e.g. for retries after a fast-model tool-call failure)
        """
        model = force_model or self.complexity.pick_model(user_input)
        actionable = self.complexity.is_actionable(user_input)
        query_type = "ACTION" if actionable else "CONVERSATIONAL"
        logger.debug(f"Query type: {query_type} | '{user_input[:50]}' -> {model}")

        system_prompt = self.prompt_builder.build_system_prompt(
            context=context, system_state=system_state
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        tools_for_call = self.tools if actionable else []

        loop = asyncio.get_event_loop()
        text_response, tool_calls = await loop.run_in_executor(
            None, self._chat_stream, model, messages, tools_for_call
        )

        return {
            "response": text_response.strip(),
            "tool_calls": tool_calls,
            "requires_confirmation": self._needs_confirmation(tool_calls),
            "model_used": model,
            "query_type": query_type,
        }

    async def escalate(
        self,
        user_input: str,
        context: List[Dict[str, str]],
        system_state: str,
    ) -> Dict[str, Any]:
        """Force a smart-model call — use after a fast attempt under-delivers."""
        return await self.process_command(
            user_input, context, system_state, force_model=self.smart_model
        )

    def _needs_confirmation(self, tool_calls: List[dict]) -> bool:
        return any(call.get("tool") in self.DESTRUCTIVE_TOOLS for call in tool_calls)
