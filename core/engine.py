"""AURIX main orchestrator."""
import asyncio
import os
import re
from typing import Optional

from core.state_manager import SystemState
from gui.hud_panel import HUDPanel
from gui.orb_renderer import OrbGUI
from gui.sphere_controller import SphereController
from llm.claude_interface import ClaudeInterface
from memory.graph_memory import GraphMemory
from tools.executor import ToolExecutor
from tools import system_control
from utils.logger import get_logger
from utils.ollama_manager import OllamaManager
from voice.wake_word_detector import WakeWordDetector
from voice.speech_to_text import SpeechToText, list_microphones
from voice.text_to_speech import TextToSpeech


logger = get_logger(__name__)

GOODNIGHT_PATTERN = re.compile(
    r"\b(good\s*night|goodnight|goodbye|good\s*bye|shut\s*down)\b.*\b(jarvis|aurix)\b"
    r"|\b(jarvis|aurix)\b.*\b(good\s*night|goodnight|goodbye|good\s*bye|shut\s*down)\b",
    re.IGNORECASE,
)

PAUSE_PATTERN = re.compile(
    r"^\s*(hold on|wait|pause|stop listening|never\s*mind|nevermind)\s*$",
    re.IGNORECASE,
)

SHOW_HUD_PATTERN = re.compile(
    r"\b(show|display|open)\b.+\b(hud|panel|display|screen)\b",
    re.IGNORECASE,
)

HIDE_HUD_PATTERN = re.compile(
    r"\b(hide|close|dismiss)\b.+\b(hud|panel|display|screen|it)\b",
    re.IGNORECASE,
)

FOLLOW_UP_INDICATORS = re.compile(
    r"\[FOLLOW_UP\]"
    r"|\bwould you like\b|\bdo you want\b|\bwhich one\b|\bwhat would\b"
    r"|\bshould I\b|\bwould you prefer\b|\bdo you mean\b",
    re.IGNORECASE,
)

def _format_tool_summary(tool: str, result: dict) -> str:
    """Per-tool pretty summary shown in the HUD Summary section."""
    if not isinstance(result, dict):
        return ""

    if tool == "get_weather":
        loc = result.get("location", "your location")
        desc = result.get("description", "Unknown")
        tc = result.get("temperature_c", "?")
        tf = result.get("temperature_f", "?")
        feels = result.get("feels_like_c", "?")
        hum = result.get("humidity", "?")
        lines = [f"Weather in {loc}:", f"{desc}, {tc}°C ({tf}°F)"]
        if feels not in ("?", None, ""):
            lines.append(f"Feels like {feels}°C")
        if hum not in ("?", None, ""):
            lines.append(f"Humidity: {hum}%")
        return "\n".join(lines)

    if tool == "open_application":
        display = result.get("display") or result.get("app", "application")
        return f"Opened {display}"

    if tool == "close_application":
        app = result.get("app", "application")
        killed = result.get("killed", 0)
        return f"Closed {app}" + (f" ({killed} process)" if killed else "")

    if tool == "get_system_info":
        return result.get("summary", "")

    if tool in ("check_unread_count", "get_recent_emails", "search_emails"):
        return result.get("brief") or result.get("summary", "")

    if tool == "web_search":
        results = result.get("results") or []
        if not results:
            return f"No results for '{result.get('query', '')}'"
        top = results[0]
        parts = [f"Top result: {top.get('title', '')}"]
        snippet = top.get("snippet", "")
        if snippet:
            parts.append(snippet[:180])
        return "\n".join(parts)

    if tool == "set_timer":
        return result.get("summary") or result.get("brief", "Timer set")

    if tool in ("create_note", "read_note", "list_notes"):
        return result.get("summary") or result.get("brief", "")

    if tool == "local_file_search":
        return result.get("summary", "")

    return result.get("brief") or result.get("summary", "")


def _format_response_text(
    command: str, llm_text: str, tool_summary: str, tool_calls: list,
) -> str:
    """Produce the one-line conversational response shown/spoken to the user."""
    stripped = (llm_text or "").replace("[FOLLOW_UP]", "").strip()

    if tool_summary:
        first_line = tool_summary.split("\n", 1)[0].strip()
        if first_line:
            return first_line

    if stripped and stripped.lower() not in {"task completed", "done", "ok"}:
        return stripped

    if tool_calls:
        name = tool_calls[0].get("tool", "task")
        return f"Completed {name.replace('_', ' ')}"

    math_answer = _try_quick_math(command)
    if math_answer is not None:
        return math_answer

    return stripped or "Done"


_MATH_RE = re.compile(r"^[\s0-9+\-*/().x×÷]+$")


def _try_quick_math(command: str) -> Optional[str]:
    """Evaluate simple arithmetic phrased in natural language."""
    if not command:
        return None
    text = command.lower()
    text = text.replace("what is", "").replace("whats", "").replace("what's", "")
    text = text.replace("calculate", "").replace("compute", "").replace("equals", "")
    text = text.replace("plus", "+").replace("minus", "-")
    text = text.replace("times", "*").replace("multiplied by", "*").replace("x", "*").replace("×", "*")
    text = text.replace("divided by", "/").replace("over", "/").replace("÷", "/")
    text = text.replace("?", "").strip()
    if not text or not _MATH_RE.match(text):
        return None
    try:
        value = eval(text, {"__builtins__": {}}, {})  # noqa: S307 - constrained math
    except Exception:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    display = text.replace("*", " × ").replace("/", " ÷ ").strip()
    display = re.sub(r"\s+", " ", display)
    return f"{display} = {value}"


OPEN_APP_RE = re.compile(
    r"^\s*(?:can\s+you\s+|please\s+|could\s+you\s+)?"
    r"(open|launch|start|run)\s+"
    r"(?:the\s+|my\s+)?"
    r"([a-zA-Z][a-zA-Z0-9 _.-]{0,40}?)"
    r"(?:\s+(?:please|now|for\s+me|app|application|program))?"
    r"[.!?\s]*$",
    re.IGNORECASE,
)
CLOSE_APP_RE = re.compile(
    r"^\s*(?:can\s+you\s+|please\s+|could\s+you\s+)?"
    r"(close|quit|kill|stop)\s+"
    r"(?:the\s+|my\s+)?"
    r"([a-zA-Z][a-zA-Z0-9 _.-]{0,40}?)"
    r"(?:\s+(?:please|now|app|application|program))?"
    r"[.!?\s]*$",
    re.IGNORECASE,
)


ACTION_VERBS = {
    "open", "close", "launch", "quit", "exit", "start", "stop", "kill",
    "play", "pause", "resume", "mute", "unmute", "skip",
    "search", "find", "show", "hide", "minimize", "maximize", "switch",
    "create", "make", "send", "delete", "remove", "set", "turn",
    "save", "load", "run", "execute", "schedule", "remind",
    "weather", "forecast", "check", "system", "battery", "cpu", "ram", "disk",
    "note", "notes", "memo", "timer", "alarm", "countdown", "cancel",
    "record", "recording", "macro", "replay",
    "email", "emails", "mail", "inbox", "unread", "read", "send",
    "goodnight", "goodbye", "shutdown", "shut",
}


def _looks_actionable(command: str) -> bool:
    if not command:
        return False
    words = command.lower().split()
    return any(w in ACTION_VERBS for w in words[:5])


def _needs_follow_up(response_text: str) -> bool:
    """Check if the LLM response expects a follow-up from the user."""
    return bool(FOLLOW_UP_INDICATORS.search(response_text))


class AurixEngine:
    """
    Main orchestrator for the AURIX system.
    Coordinates all modules and manages the event loop.
    """

    def __init__(self, config: dict, mode: str = "speech"):
        self.config = config
        self.mode = mode  # "speech" or "silent"
        self.ollama_manager = OllamaManager()

        self.wake_word = WakeWordDetector(
            wake_word=config.get("wake_word", "hey_aurix"),
            model_path=config.get("wakeword_model_path"),
            threshold=config.get("wakeword_threshold", 0.5),
        )
        self.stt = SpeechToText(
            language=config.get("stt_language", "en-US"),
            device_index=config.get("stt_mic_index"),
        )
        self.tts = TextToSpeech(
            rate=config.get("tts_rate", 175),
            volume=config.get("tts_volume", 0.9),
        )

        self.memory = GraphMemory()
        self.state = SystemState()
        self.llm = ClaudeInterface()
        self.tools = ToolExecutor()

        self.gui = OrbGUI(enabled=False)

        sphere_enabled = config.get("sphere_enabled", False)
        self.sphere = SphereController() if sphere_enabled else None
        self.hud = HUDPanel(enabled=sphere_enabled)

        if self.sphere is not None:
            self.sphere.set_click_handler(self._on_sphere_click)
            self.tts.set_audio_callback(self._on_tts_audio)

        system_control.register_shutdown_callback(self._graceful_shutdown)

        self._pending_command: Optional[str] = None
        self._command_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.running = False

    def _init_hud_mics(self) -> None:
        """Populate the HUD mic selector with available devices."""
        try:
            mics = list_microphones()
            self.hud.set_mic_list(mics, self.stt.device_index)
            self.hud.set_mic_change_callback(self._on_mic_change)
        except Exception as e:
            logger.warning(f"Could not list microphones for HUD: {e}")

    def _on_mic_change(self, new_index: int) -> None:
        """Called from HUD when user clicks to cycle microphone."""
        self.stt.device_index = new_index
        logger.info(f"Microphone switched to index {new_index}")

    def _on_sphere_click(self) -> None:
        self.hud.toggle()

    def _on_tts_audio(self, low: float, mid: float, high: float, amp: float) -> None:
        if self.sphere is not None:
            self.sphere.send_audio(low, mid, high, amp)

    def _set_state(self, state: str) -> None:
        self.gui.set_state(state)
        self.hud.set_state(state)
        if self.sphere is not None:
            self.sphere.set_state(state)

    def _show_hud_briefly(self) -> None:
        """Show HUD for the auto-hide duration after a command."""
        self.hud.show(temporary=True)

    async def start(self) -> None:
        self.running = True
        self._loop = asyncio.get_event_loop()
        self._command_event = asyncio.Event()
        logger.info(f"AURIX starting in {self.mode.upper()} mode...")

        os.makedirs(
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"),
            exist_ok=True,
        )

        if not self.ollama_manager.ensure_running():
            logger.error("Ollama is not available — LLM features will fail")

        if self.sphere is not None:
            self.sphere.start()
            self.hud.start()
            if self.mode == "speech":
                self._init_hud_mics()

        if self.mode == "silent":
            self.hud.set_silent_mode(True)
            self.hud.set_command_callback(self._on_silent_command)
            if not self.hud._running and self.hud.enabled:
                self.hud.start()
            self.hud.pin()

        main_loop = (
            self._silent_main_loop() if self.mode == "silent"
            else self._main_loop()
        )

        tasks = [
            asyncio.create_task(main_loop),
            asyncio.create_task(self._state_monitor_loop()),
        ]

        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("Shutting down AURIX...")
        finally:
            self.running = False
            logger.info("Cleaning up all subsystems...")
            for name, cleanup in [
                ("HUD", lambda: self.hud.stop()),
                ("GUI", lambda: self.gui.stop()),
                ("Sphere", lambda: self.sphere.stop() if self.sphere else None),
                ("Wake word", lambda: self.wake_word.cleanup()),
                ("Ollama", lambda: self.ollama_manager.shutdown()),
            ]:
                try:
                    cleanup()
                except Exception as e:
                    logger.warning(f"Error stopping {name}: {e}")
            logger.info("All subsystems stopped")

    def _update_memory_stats(self) -> None:
        total = len(self.memory.node_index)
        shortcuts = sum(1 for n in self.memory.node_index.values() if n.type == "MACRO")
        edges = self.memory.graph.number_of_edges()
        stats = f"Memory: {total} nodes | {shortcuts} shortcuts | {edges} edges"
        self.hud.set_memory_stats(stats)

    def _is_goodnight(self, command: str) -> bool:
        return bool(GOODNIGHT_PATTERN.search(command))

    def _is_pause(self, command: str) -> bool:
        return bool(PAUSE_PATTERN.match(command))

    def _is_show_hud(self, command: str) -> bool:
        return bool(SHOW_HUD_PATTERN.search(command))

    def _is_hide_hud(self, command: str) -> bool:
        return bool(HIDE_HUD_PATTERN.search(command))

    async def _try_fast_path(self, command: str) -> Optional[dict]:
        """Short-circuit common commands to skip the LLM round-trip.

        Returns a dict with keys {tool_calls, results, summary, response}
        when the fast path handled the command, or None to fall through
        to the LLM. Saves ~700-1500ms per matched command.
        """
        # 1. Arithmetic: "what is 2+2", "10 times 5"
        math = _try_quick_math(command)
        if math is not None:
            return {
                "tool_calls": [],
                "results": [],
                "summary": math,
                "response": math,
            }

        # 2. Direct "open X" / "launch X" where X resolves to a known app.
        m = OPEN_APP_RE.match(command)
        if m:
            from tools import app_control
            target = m.group(2).strip().rstrip(".?!").strip()
            # Strip trailing filler words the regex didn't catch
            for suffix in (" browser", " app", " application", " program"):
                if target.lower().endswith(suffix):
                    base = target[: -len(suffix)].strip()
                    if app_control._resolve_binary(base):
                        target = base
                        break
            if app_control._resolve_binary(target):
                try:
                    result = await app_control.open_application(target)
                    summary = _format_tool_summary("open_application", result)
                    tool_calls = [{"tool": "open_application", "params": {"app_name": target}}]
                    self.memory.add_interaction(
                        intent=command,
                        actions=tool_calls,
                        result=summary,
                        success=True,
                    )
                    return {
                        "tool_calls": tool_calls,
                        "results": [{"tool": "open_application", "result": result, "success": True}],
                        "summary": summary,
                        "response": summary,
                    }
                except Exception as e:
                    logger.warning(f"Fast-path open failed, falling back to LLM: {e}")

        # 3. Direct "close X"
        m = CLOSE_APP_RE.match(command)
        if m:
            from tools import app_control
            target = m.group(2).strip().rstrip(".?!").strip()
            if target.lower() in {"it", "this", "that", "everything", "all"}:
                return None  # Too ambiguous; let the LLM figure it out
            try:
                result = await app_control.close_application(target)
                summary = _format_tool_summary("close_application", result)
                tool_calls = [{"tool": "close_application", "params": {"app_name": target}}]
                self.memory.add_interaction(
                    intent=command,
                    actions=tool_calls,
                    result=summary,
                    success=True,
                )
                return {
                    "tool_calls": tool_calls,
                    "results": [{"tool": "close_application", "result": result, "success": True}],
                    "summary": summary,
                    "response": summary,
                }
            except Exception as e:
                logger.debug(f"Fast-path close failed, falling back to LLM: {e}")

        return None

    async def _graceful_shutdown(self) -> None:
        logger.info("Graceful shutdown initiated")

        self._set_state("speaking")
        self.hud.set_action("Shutting down...")

        if self.sphere is not None:
            self.sphere.send_goodbye()

        if self.mode == "speech":
            try:
                await self.tts.speak("Goodnight. Shutting down now.")
            except Exception as e:
                logger.warning(f"TTS failed during shutdown: {e}")

        graph_path = self.config.get("graph_path", "data/graph.pkl")
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), graph_path)
        try:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            self.memory.save(full_path)
            logger.info(f"Memory graph saved to {full_path}")
        except Exception as e:
            logger.error(f"Failed to save memory graph: {e}")

        await asyncio.sleep(1.5)
        self.running = False
        logger.info("Graceful shutdown complete")

    async def _process_single_command(self, command: str) -> str:
        """Process one command end-to-end. Returns response text."""
        self.state.record_command(command)
        self.hud.clear_summary()
        self.hud.set_command(command)
        self._show_hud_briefly()

        # Goodnight
        if self._is_goodnight(command):
            logger.info(f"Goodnight command detected: '{command}'")
            self.hud.set_response("Goodnight!")
            await self._graceful_shutdown()
            return ""

        # Pause / hold on
        if self._is_pause(command):
            logger.info(f"Pause command: '{command}'")
            self._set_state("speaking")
            await self.tts.speak("Standing by.")
            self.hud.set_response("Standing by.")
            return ""

        # Show/hide HUD
        if self._is_show_hud(command):
            self.hud.pin()
            self._set_state("speaking")
            resp = "HUD is now pinned."
            self.hud.set_response(resp)
            await self.tts.speak("Here you go.")
            return resp
        if self._is_hide_hud(command):
            self.hud.hide()
            self._set_state("speaking")
            resp = "HUD hidden."
            self.hud.set_response(resp)
            await self.tts.speak("Hidden.")
            return resp

        # Shortcut
        shortcut = self.memory.find_shortcut(command)
        if shortcut:
            logger.info(f"Using shortcut: {shortcut['macro_id']}")
            self.hud.set_action(f"Shortcut: {shortcut['macro_id'][:12]}...")
            await self.tools.execute_sequence(shortcut["sequence"])
            self._set_state("speaking")
            resp = "Done"
            self.hud.set_response(resp)
            await self.tts.speak(resp)
            self._update_memory_stats()
            return resp

        # Fast path: skip LLM for arithmetic + direct app launches
        fast = await self._try_fast_path(command)
        if fast is not None:
            logger.info(f"Fast path handled '{command[:50]}' (no LLM call)")
            self._set_state("speaking")
            if fast["summary"]:
                self.hud.set_summary(fast["summary"])
            self.hud.set_response(fast["response"])
            self.hud.set_action("")
            self._update_memory_stats()
            await self.tts.speak(fast["response"])
            return fast["response"]

        # LLM processing
        self._set_state("thinking")
        self.hud.set_action("Thinking...")

        context = self.memory.retrieve_context(command)
        state_str = self.state.to_context_string()
        context_payload = [n.to_dict() for n in context]

        llm_response = await self.llm.process_command(
            command, context_payload, state_str,
        )
        query_type = llm_response.get("query_type", "ACTION")
        logger.info(
            f"Query type: {query_type} | "
            f"model={llm_response.get('model_used')} "
            f"tools={len(llm_response.get('tool_calls', []))}"
        )

        if query_type == "CONVERSATIONAL":
            if llm_response["tool_calls"]:
                logger.info(
                    f"Dropping {len(llm_response['tool_calls'])} tool call(s) "
                    f"for conversational query '{command}'"
                )
                llm_response["tool_calls"] = []
        else:
            if (
                not llm_response["tool_calls"]
                and _looks_actionable(command)
                and llm_response.get("model_used") != self.llm.smart_model
            ):
                logger.info(
                    f"Escalating to {self.llm.smart_model}: "
                    f"fast model returned no tools for '{command}'"
                )
                llm_response = await self.llm.escalate(
                    command, context_payload, state_str,
                )

        tool_summary = ""
        if llm_response["tool_calls"]:
            tool_names = ", ".join(
                c.get("tool", "?") for c in llm_response["tool_calls"]
            )
            self.hud.set_action(f"Executing: {tool_names}")

            has_shutdown = any(
                c.get("tool") == "shutdown_aurix"
                for c in llm_response["tool_calls"]
            )
            if has_shutdown:
                self.hud.set_response("Goodnight!")
                await self._graceful_shutdown()
                return ""

            results = await self.tools.execute_tools(
                llm_response["tool_calls"], self.state
            )
            self.memory.add_interaction(
                intent=command,
                actions=llm_response["tool_calls"],
                result=results.get("summary", ""),
                success=results.get("success", True),
            )

            for r in results.get("results", []):
                res = r.get("result")
                tool_name = r.get("tool", "")
                if not r.get("success"):
                    err = r.get("error") or ""
                    if err:
                        tool_summary = err
                    continue
                s = _format_tool_summary(tool_name, res) if isinstance(res, dict) else ""
                if s:
                    tool_summary = s
                    break

        self._set_state("speaking")
        response_text = _format_response_text(
            command, llm_response.get("response", ""),
            tool_summary, llm_response["tool_calls"],
        )
        spoken_text = response_text

        if tool_summary:
            self.hud.set_summary(tool_summary)
        elif not llm_response["tool_calls"]:
            math = _try_quick_math(command)
            if math:
                self.hud.set_summary(math)

        word_count = len(spoken_text.split())
        if word_count > 150:
            self.hud.set_response(spoken_text[:80] + "...")
            if not tool_summary:
                self.hud.set_summary(spoken_text)
            self.hud.set_action("")
            self._update_memory_stats()
            await self.tts.speak("Here's what I found. I've put the full details on the HUD.")
        else:
            self.hud.set_response(spoken_text)
            self.hud.set_action("")
            self._update_memory_stats()
            await self.tts.speak(spoken_text)

        return response_text

    def _on_silent_command(self, text: str) -> None:
        """Called from HUD thread when user presses Enter in text input."""
        self._pending_command = text
        if self._loop is not None and self._command_event is not None:
            self._loop.call_soon_threadsafe(self._command_event.set)

    async def _silent_main_loop(self) -> None:
        """Event loop for silent (text-only) mode."""
        logger.info("Silent mode active — waiting for text input via HUD")
        self._set_state("idle")

        while self.running:
            try:
                self._set_state("idle")
                self.hud.set_action("")

                self._command_event.clear()
                await self._command_event.wait()

                command = self._pending_command
                self._pending_command = None
                if not command:
                    continue

                response = await self._process_silent_command(command)
                if not self.running:
                    return

            except Exception as e:
                logger.exception(f"Error in silent loop: {e}")
                self._set_state("error")
                self.hud.set_response("Something went wrong.")

    async def _process_silent_command(self, command: str) -> str:
        """Process a command in silent mode (no TTS, text-only responses).

        In silent mode the HUD's text entry already appended the user's
        message to the chat log, so we must NOT call set_command again here
        — that would duplicate it. Speech mode still uses set_command
        because there's no HUD entry path in that flow.
        """
        self.state.record_command(command)
        self.hud.clear_summary()
        self._show_hud_briefly()

        if self._is_goodnight(command):
            logger.info(f"Goodnight command detected: '{command}'")
            self.hud.set_response("Goodnight!")
            await self._graceful_shutdown()
            return ""

        if self._is_show_hud(command):
            self.hud.pin()
            self.hud.set_response("HUD is now pinned.")
            return "HUD is now pinned."
        if self._is_hide_hud(command):
            self.hud.hide()
            self.hud.set_response("HUD hidden.")
            return "HUD hidden."

        shortcut = self.memory.find_shortcut(command)
        if shortcut:
            logger.info(f"Using shortcut: {shortcut['macro_id']}")
            self.hud.set_action(f"Shortcut: {shortcut['macro_id'][:12]}...")
            await self.tools.execute_sequence(shortcut["sequence"])
            self._set_state("idle")
            self.hud.set_response("Done")
            self.hud.set_action("")
            self._update_memory_stats()
            return "Done"

        fast = await self._try_fast_path(command)
        if fast is not None:
            logger.info(f"Fast path handled '{command[:50]}' (no LLM call)")
            self._set_state("idle")
            if fast["summary"]:
                self.hud.set_summary(fast["summary"])
            self.hud.set_response(fast["response"])
            self.hud.set_action("")
            self._update_memory_stats()
            return fast["response"]

        self._set_state("thinking")
        self.hud.set_action("Thinking...")

        context = self.memory.retrieve_context(command)
        state_str = self.state.to_context_string()
        context_payload = [n.to_dict() for n in context]

        llm_response = await self.llm.process_command(
            command, context_payload, state_str,
        )
        query_type = llm_response.get("query_type", "ACTION")
        logger.info(
            f"Query type: {query_type} | "
            f"model={llm_response.get('model_used')} "
            f"tools={len(llm_response.get('tool_calls', []))}"
        )

        if query_type == "CONVERSATIONAL":
            if llm_response["tool_calls"]:
                llm_response["tool_calls"] = []
        else:
            if (
                not llm_response["tool_calls"]
                and _looks_actionable(command)
                and llm_response.get("model_used") != self.llm.smart_model
            ):
                llm_response = await self.llm.escalate(
                    command, context_payload, state_str,
                )

        tool_summary = ""
        if llm_response["tool_calls"]:
            tool_names = ", ".join(
                c.get("tool", "?") for c in llm_response["tool_calls"]
            )
            self.hud.set_action(f"Executing: {tool_names}")

            has_shutdown = any(
                c.get("tool") == "shutdown_aurix"
                for c in llm_response["tool_calls"]
            )
            if has_shutdown:
                self.hud.set_response("Goodnight!")
                await self._graceful_shutdown()
                return ""

            results = await self.tools.execute_tools(
                llm_response["tool_calls"], self.state
            )
            self.memory.add_interaction(
                intent=command,
                actions=llm_response["tool_calls"],
                result=results.get("summary", ""),
                success=results.get("success", True),
            )

            for r in results.get("results", []):
                res = r.get("result")
                tool_name = r.get("tool", "")
                if not r.get("success"):
                    err = r.get("error") or ""
                    if err:
                        tool_summary = err
                    continue
                s = _format_tool_summary(tool_name, res) if isinstance(res, dict) else ""
                if s:
                    tool_summary = s
                    break

        self._set_state("idle")
        response_text = _format_response_text(
            command, llm_response.get("response", ""),
            tool_summary, llm_response["tool_calls"],
        )

        self.hud.set_response(response_text)
        self.hud.set_action("")
        if tool_summary:
            self.hud.set_summary(tool_summary)
        elif not llm_response["tool_calls"]:
            math = _try_quick_math(command)
            if math:
                self.hud.set_summary(math)
        self._update_memory_stats()

        return response_text

    async def _main_loop(self) -> None:
        while self.running:
            try:
                self._set_state("idle")
                self.hud.set_action("")

                detected = await self.wake_word.detect()
                if not detected:
                    continue

                self._set_state("listening")
                command = await self.stt.listen(timeout=5)

                if not command:
                    self._set_state("speaking")
                    await self.tts.speak("I didn't catch that")
                    continue

                response = await self._process_single_command(command)
                if not self.running:
                    return

                # Follow-up loop: if response indicates a question, keep listening
                while self.running and response and _needs_follow_up(response):
                    logger.info("Follow-up expected, listening again...")
                    self._set_state("listening")
                    follow_up = await self.stt.listen(timeout=8)

                    if not follow_up:
                        logger.info("No follow-up heard, returning to idle")
                        break

                    if self._is_pause(follow_up):
                        self._set_state("speaking")
                        await self.tts.speak("Standing by.")
                        break

                    response = await self._process_single_command(follow_up)
                    if not self.running:
                        return

            except Exception as e:
                logger.exception(f"Error in main loop: {e}")
                self._set_state("error")
                try:
                    await self.tts.speak("Sorry, something went wrong")
                except Exception:
                    pass

    async def _state_monitor_loop(self) -> None:
        while self.running:
            self.state.update_active_app()
            await asyncio.sleep(1.0)
