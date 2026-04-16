"""Holographic HUD panel — transparent overlay displaying AURIX state.

Renders a frameless tkinter window positioned to the right of the Electron
sphere.  Starts hidden; shown on sphere click or command execution.
Auto-hides after 10 seconds of inactivity unless pinned.
Runs in its own daemon thread.

Silent mode: always visible, text entry at bottom for typed commands.
"""
import json
import math
import os
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__)

# ── Default layout ────────────────────────────────────────────────────
SPHERE_RIGHT_EDGE = 400
HUD_GAP = 20
DEFAULT_X = SPHERE_RIGHT_EDGE + HUD_GAP
DEFAULT_W = 400
DEFAULT_H = 420
MIN_W = 300
MIN_H = 250
MAX_W = 800
MAX_H = 600
CORNER_R = 15
MARGIN = 14
LINE_H = 16
AUTO_HIDE_SECONDS = 10
FADE_FRAMES = 10
TITLE_BAR_H = 30       # top area used for dragging
RESIZE_GRIP = 14       # bottom-right corner resize zone

# ── Colors ────────────────────────────────────────────────────────────
CYAN = "#00ffff"
CYAN_DIM = "#007777"
CYAN_DARK = "#003333"
GRID_COLOR = "#071e1e"
PANEL_BG = "#001428"
TEXT_DIM = "#4a8888"
WHITE = "#c0e8e8"
ENTRY_BG = "#011e2e"
ENTRY_FG = "#00ffff"
PLACEHOLDER_COLOR = "#2a6666"

_SETTINGS_PATH = (
    Path(os.path.dirname(os.path.dirname(__file__))) / "config" / "hud_settings.json"
)

STATE_COLORS = {
    "idle": "#00aaff",
    "listening": "#00ff88",
    "thinking": "#ffaa00",
    "speaking": "#ff44aa",
    "error": "#ff3333",
}
STATE_LABELS = {
    "idle": "IDLE",
    "listening": "LISTENING",
    "thinking": "THINKING",
    "speaking": "SPEAKING",
    "error": "ERROR",
}

PLACEHOLDER_TEXT = "Type command and press Enter..."


class HUDPanel:
    """Holographic HUD overlay rendered with tkinter Canvas."""

    def __init__(self, orb=None, enabled: bool = True):
        self.enabled = enabled
        self._lock = threading.Lock()
        self._state = "idle"
        self._chat_log: List[dict] = []
        self._current_action = ""
        self._summary_text = ""
        self._memory_stats = ""
        self._mic_list: List[Tuple[int, str]] = []
        self._current_mic_idx: Optional[int] = None
        self._mic_change_callback: Optional[Callable] = None
        self._scroll_offset = 0
        self._frame = 0
        self._scanline_y = 0.0

        # Silent mode
        self._silent_mode = False
        self._text_input_var = None
        self._text_entry = None
        self._command_callback: Optional[Callable] = None
        self._typing = False
        self._entry_has_focus = False
        self._entry_packed = False

        # Visibility / fade
        self._visible = False
        self._pinned = False
        self._fade_alpha = 0.0
        self._target_alpha = 0.0
        self._last_activity = 0.0

        # Window
        self._root = None
        self._canvas = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Drag / resize state
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._dragging = False
        self._resizing = False
        self._resize_start_w = 0
        self._resize_start_h = 0

        # Geometry (loaded from settings or defaults)
        self._hud_x = DEFAULT_X
        self._hud_y: Optional[int] = None
        self._hud_w = DEFAULT_W
        self._hud_h = DEFAULT_H
        self._load_position()

    # ─── Thread-safe setters (called from engine) ─────────────────────

    def set_state(self, state: str) -> None:
        with self._lock:
            self._state = state

    def set_command(self, text: str) -> None:
        with self._lock:
            self._chat_log.append({"role": "you", "text": text})
            if len(self._chat_log) > 20:
                self._chat_log = self._chat_log[-20:]
            self._last_activity = time.time()
            self._scroll_offset = 0

    def set_response(self, text: str) -> None:
        with self._lock:
            self._chat_log.append({"role": "aurix", "text": text})
            if len(self._chat_log) > 20:
                self._chat_log = self._chat_log[-20:]
            self._last_activity = time.time()
            self._scroll_offset = 0

    def set_action(self, text: str) -> None:
        with self._lock:
            self._current_action = text
            if text:
                self._last_activity = time.time()

    def set_summary(self, text: str) -> None:
        with self._lock:
            self._summary_text = text or ""
            self._last_activity = time.time()

    def clear_summary(self) -> None:
        """Reset the Summary section so the next command starts blank."""
        with self._lock:
            self._summary_text = ""

    def set_memory_stats(self, text: str) -> None:
        with self._lock:
            self._memory_stats = text

    def set_mic_list(
        self, mics: List[Tuple[int, str]], current_idx: Optional[int] = None
    ) -> None:
        with self._lock:
            self._mic_list = mics
            self._current_mic_idx = current_idx

    def set_mic_change_callback(self, callback: Callable) -> None:
        self._mic_change_callback = callback

    def attach_orb(self, orb) -> None:
        pass

    def update(self) -> None:
        pass

    def set_silent_mode(self, enabled: bool) -> None:
        with self._lock:
            self._silent_mode = enabled
        if enabled:
            self.pin()

    def set_command_callback(self, callback: Callable) -> None:
        self._command_callback = callback

    def set_typing(self, typing: bool) -> None:
        with self._lock:
            self._typing = typing

    # ─── Position persistence ─────────────────────────────────────────

    def _load_position(self) -> None:
        try:
            if _SETTINGS_PATH.exists():
                data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
                self._hud_x = data.get("x") or DEFAULT_X
                self._hud_y = data.get("y")
                w = data.get("width") or DEFAULT_W
                h = data.get("height") or DEFAULT_H
                self._hud_w = max(MIN_W, min(w, MAX_W))
                self._hud_h = max(MIN_H, min(h, MAX_H))
                logger.debug(
                    f"HUD position loaded: x={self._hud_x} y={self._hud_y} "
                    f"w={self._hud_w} h={self._hud_h}"
                )
        except Exception as e:
            logger.warning(f"Could not load HUD settings: {e}")

    def _save_position(self) -> None:
        try:
            if self._root is not None:
                try:
                    self._hud_x = self._root.winfo_x()
                    self._hud_y = self._root.winfo_y()
                    self._hud_w = self._root.winfo_width()
                    self._hud_h = self._root.winfo_height()
                except Exception:
                    pass
            data = {
                "x": self._hud_x,
                "y": self._hud_y,
                "width": self._hud_w,
                "height": self._hud_h,
            }
            _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            _SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.debug(f"HUD position saved: {data}")
        except Exception as e:
            logger.warning(f"Could not save HUD settings: {e}")

    # ─── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if not self.enabled:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="aurix-hud"
        )
        self._thread.start()
        logger.info("HUD panel thread started")

    def stop(self) -> None:
        self._running = False
        # Try to persist position BEFORE touching the Tk root — position
        # save uses Tk calls that must happen on the HUD thread.
        root = self._root
        if root is not None:
            try:
                # Schedule both save+quit+destroy on the HUD thread's mainloop,
                # then let the thread exit cleanly.
                root.after(0, self._safe_shutdown)
            except Exception:
                # If after() fails (loop already gone), fall back to best-effort.
                try:
                    root.quit()
                except Exception:
                    pass
                try:
                    root.destroy()
                except Exception:
                    pass
                self._root = None
                self._canvas = None
        else:
            # No Tk root — just persist whatever geometry we have cached.
            self._save_position()

        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)
        logger.info("HUD panel stopped")

    def _safe_shutdown(self) -> None:
        """Runs on the HUD thread — save settings, quit mainloop, destroy root."""
        try:
            self._save_position()
        except Exception:
            pass
        root = self._root
        self._root = None
        self._canvas = None
        if root is None:
            return
        try:
            root.quit()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass

    # Back-compat alias in case anything still calls the old name.
    _safe_destroy = _safe_shutdown

    def show(self, temporary: bool = True) -> None:
        logger.debug(f"HUD show() called, temporary={temporary}")
        with self._lock:
            self._visible = True
            self._target_alpha = 0.95
            self._last_activity = time.time()
            if not temporary:
                self._pinned = True

    def hide(self) -> None:
        logger.debug("HUD hide() called")
        with self._lock:
            self._visible = False
            self._pinned = False
            self._target_alpha = 0.0

    def toggle(self) -> None:
        with self._lock:
            if self._visible:
                logger.debug("HUD toggle() -> hiding")
                self._visible = False
                self._pinned = False
                self._target_alpha = 0.0
            else:
                logger.debug("HUD toggle() -> showing")
                self._visible = True
                self._target_alpha = 0.95
                self._last_activity = time.time()

    def pin(self) -> None:
        with self._lock:
            self._visible = True
            self._pinned = True
            self._target_alpha = 0.95
            self._last_activity = time.time()

    def unpin(self) -> None:
        with self._lock:
            self._pinned = False
            self._last_activity = time.time()

    # ─── Window build ─────────────────────────────────────────────────

    def _run(self) -> None:
        try:
            import tkinter as tk
        except ImportError:
            logger.warning("tkinter not available, HUD disabled")
            self.enabled = False
            return

        self._tk = tk
        root = tk.Tk()
        self._root = root
        root.title("AURIX HUD")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.0)
        root.configure(bg=PANEL_BG)

        screen_h = root.winfo_screenheight()
        hud_y = (
            self._hud_y
            if self._hud_y is not None
            else (screen_h - self._hud_h - 60)
        )
        self._hud_y = hud_y
        root.geometry(f"{self._hud_w}x{self._hud_h}+{self._hud_x}+{hud_y}")

        # Main frame holds canvas + entry
        main_frame = tk.Frame(root, bg=PANEL_BG)
        main_frame.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(
            main_frame,
            bg=PANEL_BG,
            highlightthickness=0,
            bd=0,
        )
        self._canvas.pack(fill="both", expand=True)

        # ── Text entry (silent mode) ──────────────────────────────────
        entry_frame = tk.Frame(main_frame, bg=PANEL_BG)
        self._entry_frame = entry_frame

        self._text_input_var = tk.StringVar()
        self._text_entry = tk.Entry(
            entry_frame,
            textvariable=self._text_input_var,
            font=("Consolas", 11),
            bg=ENTRY_BG,
            fg=ENTRY_FG,
            insertbackground=CYAN,
            insertwidth=2,
            relief="flat",
            highlightthickness=2,
            highlightcolor=CYAN,
            highlightbackground=CYAN_DARK,
            selectbackground=CYAN_DIM,
            selectforeground=WHITE,
        )
        self._text_entry.pack(fill="x", padx=10, pady=(4, 10), ipady=4)

        self._text_entry.bind("<Return>", self._on_text_submit)
        self._text_entry.bind("<FocusIn>", self._on_entry_focus_in)
        self._text_entry.bind("<FocusOut>", self._on_entry_focus_out)
        self._text_entry.bind("<KeyRelease>", self._on_key_release)

        # Start with placeholder
        self._show_placeholder()

        # ── Canvas bindings ───────────────────────────────────────────
        self._canvas.bind("<Button-1>", self._on_canvas_click)
        self._canvas.bind("<B1-Motion>", self._on_canvas_b1_motion)
        self._canvas.bind("<ButtonRelease-1>", self._on_canvas_b1_release)
        self._canvas.bind("<MouseWheel>", self._on_scroll)

        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._render_tick()
        try:
            root.mainloop()
        except Exception as e:
            logger.debug(f"HUD mainloop exited with: {e}")
        finally:
            self._running = False
            try:
                if self._root is not None:
                    self._root.destroy()
            except Exception:
                pass
            self._root = None
            self._canvas = None

    # ─── Placeholder helpers ──────────────────────────────────────────

    def _show_placeholder(self) -> None:
        if self._text_entry is None:
            return
        if not self._text_input_var.get() and not self._entry_has_focus:
            self._text_entry.config(fg=PLACEHOLDER_COLOR)
            self._text_input_var.set(PLACEHOLDER_TEXT)

    def _clear_placeholder(self) -> None:
        if self._text_entry is None:
            return
        if self._text_input_var.get() == PLACEHOLDER_TEXT:
            self._text_input_var.set("")
        self._text_entry.config(fg=ENTRY_FG)

    # ─── Entry events ─────────────────────────────────────────────────

    def _on_entry_focus_in(self, event) -> None:
        self._entry_has_focus = True
        self._clear_placeholder()
        try:
            self._text_entry.config(highlightcolor=CYAN)
        except Exception:
            pass

    def _on_entry_focus_out(self, event) -> None:
        self._entry_has_focus = False
        self._show_placeholder()
        try:
            self._text_entry.config(highlightcolor=CYAN_DARK)
        except Exception:
            pass

    def _on_text_submit(self, event) -> None:
        raw = self._text_input_var.get().strip()
        if not raw or raw == PLACEHOLDER_TEXT:
            return
        self._text_input_var.set("")
        logger.debug(f"HUD command sent: '{raw}'")
        self.set_command(raw)
        if self._command_callback:
            self._command_callback(raw)

    def _on_key_release(self, event) -> None:
        text = self._text_input_var.get().strip()
        is_typing = bool(text) and text != PLACEHOLDER_TEXT
        with self._lock:
            self._typing = is_typing

    # ─── Canvas mouse: drag (title bar) + resize (grip) + click ──────

    def _on_canvas_click(self, event) -> None:
        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()

        # Bottom-right resize grip
        if event.x > cw - RESIZE_GRIP and event.y > ch - RESIZE_GRIP:
            self._resizing = True
            self._dragging = False
            self._drag_start_x = event.x_root
            self._drag_start_y = event.y_root
            self._resize_start_w = self._root.winfo_width()
            self._resize_start_h = self._root.winfo_height()
            return

        # Title bar area — start drag
        if event.y < TITLE_BAR_H:
            self._dragging = True
            self._resizing = False
            self._drag_start_x = event.x_root
            self._drag_start_y = event.y_root
            return

        # Mic click zone (bottom bar, not in silent mode)
        with self._lock:
            silent = self._silent_mode
        if not silent:
            bar_top = ch - 48
            if event.y >= bar_top and self._mic_list:
                self._cycle_mic()

    def _on_canvas_b1_motion(self, event) -> None:
        if self._dragging:
            dx = event.x_root - self._drag_start_x
            dy = event.y_root - self._drag_start_y
            self._drag_start_x = event.x_root
            self._drag_start_y = event.y_root
            try:
                nx = self._root.winfo_x() + dx
                ny = self._root.winfo_y() + dy
                self._root.geometry(f"+{nx}+{ny}")
            except Exception:
                pass

        elif self._resizing:
            dx = event.x_root - self._drag_start_x
            dy = event.y_root - self._drag_start_y
            nw = max(MIN_W, min(self._resize_start_w + dx, MAX_W))
            nh = max(MIN_H, min(self._resize_start_h + dy, MAX_H))
            try:
                x = self._root.winfo_x()
                y = self._root.winfo_y()
                self._root.geometry(f"{nw}x{nh}+{x}+{y}")
            except Exception:
                pass

    def _on_canvas_b1_release(self, event) -> None:
        if self._dragging or self._resizing:
            self._dragging = False
            self._resizing = False
            self._save_position()

    def _cycle_mic(self) -> None:
        with self._lock:
            mics = list(self._mic_list)
            current = self._current_mic_idx
        if not mics:
            return
        pos = 0
        for i, (idx, _) in enumerate(mics):
            if idx == current:
                pos = i
                break
        nxt = (pos + 1) % len(mics)
        new_idx, new_name = mics[nxt]
        with self._lock:
            self._current_mic_idx = new_idx
        logger.info(f"HUD mic switched to [{new_idx}]: {new_name}")
        if self._mic_change_callback:
            try:
                self._mic_change_callback(new_idx)
            except Exception as e:
                logger.error(f"Mic change callback failed: {e}")

    def _on_scroll(self, event) -> None:
        with self._lock:
            total = len(self._chat_log)
        if total <= 6:
            return
        delta = -1 if event.delta > 0 else 1
        mx = max(0, total - 6)
        with self._lock:
            self._scroll_offset = max(0, min(self._scroll_offset + delta, mx))

    def _on_close(self) -> None:
        self._running = False
        self._safe_shutdown()

    # ─── Render loop ──────────────────────────────────────────────────

    def _render_tick(self) -> None:
        if not self._running or self._root is None or self._canvas is None:
            return

        with self._lock:
            state = self._state
            chat_log = list(self._chat_log)
            action = self._current_action
            summary = self._summary_text
            mem_stats = self._memory_stats
            target_alpha = self._target_alpha
            visible = self._visible
            pinned = self._pinned
            last_activity = self._last_activity
            scroll_offset = self._scroll_offset
            mic_list = list(self._mic_list)
            current_mic = self._current_mic_idx
            silent_mode = self._silent_mode
            typing = self._typing

        # Show / hide entry frame
        try:
            if silent_mode and not self._entry_packed:
                self._entry_frame.pack(side="bottom", fill="x")
                self._entry_packed = True
                self._text_entry.focus_set()
            elif not silent_mode and self._entry_packed:
                self._entry_frame.pack_forget()
                self._entry_packed = False
        except Exception:
            pass

        # Auto-hide (disabled in silent mode or when pinned)
        if visible and not pinned and not silent_mode and last_activity > 0:
            if time.time() - last_activity > AUTO_HIDE_SECONDS:
                with self._lock:
                    self._visible = False
                    self._target_alpha = 0.0
                    visible = False
                    target_alpha = 0.0

        # Smooth fade
        step = 1.0 / max(FADE_FRAMES, 1)
        if self._fade_alpha < target_alpha:
            self._fade_alpha = min(self._fade_alpha + step, target_alpha)
        elif self._fade_alpha > target_alpha:
            self._fade_alpha = max(self._fade_alpha - step, target_alpha)

        try:
            self._root.attributes("-alpha", self._fade_alpha)
        except Exception:
            pass

        self._frame += 1

        # Read live canvas size
        try:
            cw = self._canvas.winfo_width()
            ch = self._canvas.winfo_height()
            if cw > 1:
                self._hud_w = cw
            if ch > 1:
                self._hud_h = ch
        except Exception:
            pass

        w = self._hud_w
        h = self._hud_h
        self._scanline_y = (self._scanline_y + 1.2) % max(h, 1)

        canvas = self._canvas
        canvas.delete("all")

        if self._fade_alpha > 0.01:
            self._draw_rounded_border(canvas, w, h)

            y = MARGIN + 2
            y = self._draw_state_indicator(canvas, state, y, w)
            y = self._draw_separator(canvas, y, w)

            y = self._draw_section_header(canvas, "COMMANDS", y)
            y = self._draw_chat_log(canvas, chat_log, y, scroll_offset, w)
            y = self._draw_separator(canvas, y, w)

            if action:
                y = self._draw_action(canvas, action, y)
                y = self._draw_separator(canvas, y, w)

            if summary:
                y = self._draw_section_header(canvas, "SUMMARY", y)
                y = self._draw_summary(canvas, summary, y, w)
                y = self._draw_separator(canvas, y, w)

            if silent_mode and typing:
                y = self._draw_typing_indicator(canvas, y)

            self._draw_bottom_bar(canvas, mic_list, current_mic, mem_stats, w, h, silent_mode)
            self._draw_scanline(canvas, w, h)
            self._draw_resize_grip(canvas, w, h)

        try:
            self._root.after(33, self._render_tick)
        except Exception:
            pass

    # ─── Drawing helpers ──────────────────────────────────────────────

    def _rounded_rect_pts(self, x1, y1, x2, y2, r):
        pts = []
        for cx, cy, a0 in [
            (x2 - r, y1 + r, -math.pi / 2),
            (x2 - r, y2 - r, 0),
            (x1 + r, y2 - r, math.pi / 2),
            (x1 + r, y1 + r, math.pi),
        ]:
            for i in range(9):
                a = a0 + (math.pi / 2) * i / 8
                pts.extend([cx + r * math.cos(a), cy + r * math.sin(a)])
        return pts

    def _draw_rounded_border(self, c, w, h) -> None:
        pulse = 0.6 + 0.4 * math.sin(self._frame * 0.05)
        v = int(255 * pulse)
        color = f"#00{v:02x}{v:02x}"

        pts = self._rounded_rect_pts(1, 1, w - 1, h - 1, CORNER_R)
        c.create_polygon(pts, fill="", outline=color, width=2, smooth=False)

        pts2 = self._rounded_rect_pts(3, 3, w - 3, h - 3, max(1, CORNER_R - 2))
        c.create_polygon(pts2, fill="", outline=CYAN_DARK, width=1, smooth=False)

    def _draw_scanline(self, c, w, h) -> None:
        y = int(self._scanline_y)
        if CORNER_R < y < h - CORNER_R:
            c.create_line(CORNER_R, y, w - CORNER_R, y, fill=CYAN_DARK, width=1)

    def _draw_resize_grip(self, c, w, h) -> None:
        for i in range(3):
            off = 6 + i * 4
            c.create_line(
                w - off, h - 3,
                w - 3, h - off,
                fill=CYAN_DIM, width=1,
            )

    def _draw_state_indicator(self, c, state: str, y: int, w: int) -> int:
        color = STATE_COLORS.get(state, CYAN)
        label = STATE_LABELS.get(state, state.upper())

        pulse = 0.7 + 0.3 * math.sin(self._frame * 0.08)
        dot_r = int(5 * pulse)
        dot_x = MARGIN + 8
        dot_y = y + 10
        c.create_oval(
            dot_x - dot_r, dot_y - dot_r,
            dot_x + dot_r, dot_y + dot_r,
            fill=color, outline="",
        )
        c.create_oval(
            dot_x - dot_r - 4, dot_y - dot_r - 4,
            dot_x + dot_r + 4, dot_y + dot_r + 4,
            outline=color, width=1,
        )

        c.create_text(
            dot_x + 18, dot_y,
            text=label, fill=color,
            font=("Consolas", 12, "bold"), anchor="w",
        )

        with self._lock:
            pin_text = "PINNED" if self._pinned else "AURIX"
        c.create_text(
            w - MARGIN - 4, dot_y,
            text=pin_text, fill=CYAN_DIM,
            font=("Consolas", 9), anchor="e",
        )
        return y + 26

    def _draw_section_header(self, c, title: str, y: int) -> int:
        c.create_text(
            MARGIN + 8, y + 1,
            text=title, fill=CYAN_DIM,
            font=("Consolas", 8, "bold"), anchor="nw",
        )
        return y + 14

    def _draw_separator(self, c, y: int, w: int) -> int:
        mid = w // 2
        xl = MARGIN + 4
        xr = w - MARGIN - 4
        c.create_line(xl, y, mid - 20, y, fill=CYAN_DARK, width=1)
        c.create_line(mid - 15, y, mid + 15, y, fill=CYAN_DIM, width=1)
        c.create_line(mid + 20, y, xr, y, fill=CYAN_DARK, width=1)
        return y + 5

    def _draw_chat_log(
        self, c, chat_log: list, y: int, scroll_offset: int, w: int,
    ) -> int:
        max_visible = 6
        max_chars = max(20, (w - 80) // 8)
        total = len(chat_log)

        if not chat_log:
            c.create_text(
                MARGIN + 8, y + 2,
                text="Awaiting commands...", fill=TEXT_DIM,
                font=("Consolas", 9), anchor="nw",
            )
            return y + LINE_H * max_visible + 4

        start = max(0, total - max_visible - scroll_offset)
        end = min(total, start + max_visible)
        visible = chat_log[start:end]

        if total > max_visible:
            bar_h = max(8, int((max_visible / total) * (max_visible * LINE_H)))
            bar_top = y + int((start / total) * (max_visible * LINE_H))
            bx = w - MARGIN - 2
            c.create_line(bx, y, bx, y + max_visible * LINE_H, fill=CYAN_DARK, width=1)
            c.create_line(bx, bar_top, bx, bar_top + bar_h, fill=CYAN_DIM, width=2)

        for entry in visible:
            role = entry["role"]
            text = entry["text"]
            if len(text) > max_chars:
                text = text[: max_chars - 3] + "..."

            if role == "you":
                prefix, pcol, tcol = "YOU:", CYAN, WHITE
            else:
                prefix, pcol, tcol = "AURIX:", STATE_COLORS.get("speaking", CYAN), "#88cccc"

            c.create_text(
                MARGIN + 8, y + 1, text=prefix, fill=pcol,
                font=("Consolas", 9, "bold"), anchor="nw",
            )
            pw = 40 if role == "you" else 52
            c.create_text(
                MARGIN + 8 + pw, y + 1, text=text, fill=tcol,
                font=("Consolas", 9), anchor="nw",
            )
            y += LINE_H

        y += (max_visible - len(visible)) * LINE_H
        return y + 2

    def _draw_action(self, c, action: str, y: int) -> int:
        pulse = 0.5 + 0.5 * math.sin(self._frame * 0.15)
        rv = int(255 * pulse)
        gv = int(170 * pulse)
        bolt = f"#{rv:02x}{gv:02x}00"

        c.create_text(
            MARGIN + 8, y + 1, text="\u26a1", fill=bolt,
            font=("Consolas", 10), anchor="nw",
        )
        disp = action[:33] + "..." if len(action) > 33 else action
        c.create_text(
            MARGIN + 24, y + 1, text=disp, fill=CYAN,
            font=("Consolas", 9, "bold"), anchor="nw",
        )
        return y + LINE_H + 4

    def _draw_summary(self, c, summary: str, y: int, w: int) -> int:
        max_chars = max(20, (w - 40) // 8)
        lines: list[str] = []
        cur = ""
        for word in summary.split():
            test = (cur + " " + word).strip()
            if len(test) > max_chars:
                if cur:
                    lines.append(cur)
                cur = word
            else:
                cur = test
        if cur:
            lines.append(cur)

        for line in lines[:4]:
            c.create_text(
                MARGIN + 8, y + 1, text=line, fill="#66aaaa",
                font=("Consolas", 9), anchor="nw",
            )
            y += LINE_H
        return y + 2

    def _draw_typing_indicator(self, c, y: int) -> int:
        dots = "." * ((self._frame // 8) % 4)
        pulse = 0.5 + 0.5 * math.sin(self._frame * 0.12)
        v = int(200 * pulse)
        color = f"#00{v:02x}{v:02x}"
        c.create_text(
            MARGIN + 8, y + 1,
            text=f"Typing{dots}", fill=color,
            font=("Consolas", 9, "bold"), anchor="nw",
        )
        return y + LINE_H + 2

    def _draw_bottom_bar(
        self, c, mic_list, current_mic, mem_stats: str,
        w: int, h: int, silent_mode: bool = False,
    ) -> None:
        bar_y = h - 48
        xl = MARGIN + 4
        xr = w - MARGIN - 4
        c.create_line(xl, bar_y, xr, bar_y, fill=CYAN_DARK, width=1)
        bar_y += 6

        if silent_mode:
            pulse = 0.6 + 0.4 * math.sin(self._frame * 0.06)
            v = int(200 * pulse)
            mc = f"#00{v:02x}{max(0, v - 60):02x}"
            c.create_text(
                MARGIN + 8, bar_y, text="SILENT MODE", fill=mc,
                font=("Consolas", 9, "bold"), anchor="nw",
            )
            c.create_text(
                w - MARGIN - 8, bar_y, text="Enter to send", fill=TEXT_DIM,
                font=("Consolas", 7), anchor="ne",
            )
            bar_y += 16
        elif mic_list:
            mic_name = "Default"
            for idx, name in mic_list:
                if idx == current_mic:
                    mic_name = name[:28] + "..." if len(name) > 28 else name
                    break
            c.create_text(
                MARGIN + 8, bar_y, text="\U0001f3a4", fill=CYAN_DIM,
                font=("Consolas", 9), anchor="nw",
            )
            c.create_text(
                MARGIN + 24, bar_y, text=mic_name, fill=TEXT_DIM,
                font=("Consolas", 8), anchor="nw",
            )
            c.create_text(
                w - MARGIN - 8, bar_y, text="\u25bc click", fill=CYAN_DARK,
                font=("Consolas", 7), anchor="ne",
            )
            bar_y += 16

        if mem_stats:
            c.create_text(
                MARGIN + 8, bar_y, text=mem_stats, fill=TEXT_DIM,
                font=("Consolas", 8), anchor="nw",
            )
        else:
            c.create_text(
                MARGIN + 8, bar_y, text="Memory: --", fill=CYAN_DARK,
                font=("Consolas", 8), anchor="nw",
            )
