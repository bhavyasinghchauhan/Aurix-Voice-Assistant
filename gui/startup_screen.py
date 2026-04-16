"""AURIX startup screen — loading bar and mode selection.

Shows a holographic-themed loading screen that tracks initialization
progress, then presents Silent/Speech mode buttons. Runs as a blocking
tkinter dialog and returns the chosen mode string.
"""
import math
import threading
import time
import tkinter as tk
from typing import Callable, Optional


# ── Colors (matches HUD theme) ────────────────────────────────────────
CYAN = "#00ffff"
CYAN_DIM = "#007777"
CYAN_DARK = "#003333"
PANEL_BG = "#001428"
GRID_COLOR = "#071e1e"
TEXT_DIM = "#4a8888"
WHITE = "#c0e8e8"
GLOW_CYAN = "#00cccc"

WIN_W = 420
WIN_H = 340
CORNER_R = 18
BAR_H = 18
BAR_PAD = 40


class StartupScreen:
    """Blocking startup dialog. Call run() — returns 'speech' or 'silent'."""

    def __init__(self):
        self._chosen_mode: Optional[str] = None
        self._progress = 0.0
        self._status_text = "Initializing..."
        self._phase = "loading"  # loading | selecting
        self._frame = 0
        self._lock = threading.Lock()
        self._root: Optional[tk.Tk] = None
        self._canvas: Optional[tk.Canvas] = None
        self._ready_event = threading.Event()

    # ─── Public API ───────────────────────────────────────────────────

    def set_progress(self, pct: float, label: str) -> None:
        with self._lock:
            self._progress = max(0.0, min(pct, 100.0))
            self._status_text = label

    def finish_loading(self) -> None:
        with self._lock:
            self._progress = 100.0
            self._status_text = "Ready!"
            self._phase = "selecting"

    def run(self) -> str:
        """Show the startup screen (blocks until user picks a mode)."""
        self._build_window()
        self._tick()
        self._root.mainloop()
        return self._chosen_mode or "speech"

    def wait_for_window(self) -> None:
        self._ready_event.wait(timeout=5)

    # ─── Window setup ─────────────────────────────────────────────────

    def _build_window(self) -> None:
        self._root = tk.Tk()
        self._root.title("AURIX")
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.configure(bg="black")

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = (sw - WIN_W) // 2
        y = (sh - WIN_H) // 2
        self._root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")

        try:
            self._root.attributes("-transparentcolor", "black")
        except Exception:
            pass

        self._canvas = tk.Canvas(
            self._root, width=WIN_W, height=WIN_H,
            bg="black", highlightthickness=0, bd=0,
        )
        self._canvas.pack()
        self._ready_event.set()

    # ─── Render loop ──────────────────────────────────────────────────

    def _tick(self) -> None:
        if self._root is None:
            return

        self._frame += 1
        c = self._canvas
        c.delete("all")

        with self._lock:
            progress = self._progress
            status = self._status_text
            phase = self._phase

        self._draw_bg(c)
        self._draw_grid(c)
        self._draw_border(c)
        self._draw_corner_accents(c)
        self._draw_title(c)

        if phase == "loading":
            self._draw_progress_bar(c, progress)
            self._draw_status(c, status, progress)
        else:
            self._draw_mode_buttons(c)

        self._draw_scanline(c)

        try:
            self._root.after(33, self._tick)
        except Exception:
            pass

    # ─── Drawing ──────────────────────────────────────────────────────

    def _rounded_rect(self, x1, y1, x2, y2, r):
        pts = []
        steps = 8
        for cx, cy, a0 in [
            (x2 - r, y1 + r, -math.pi / 2),
            (x2 - r, y2 - r, 0),
            (x1 + r, y2 - r, math.pi / 2),
            (x1 + r, y1 + r, math.pi),
        ]:
            for i in range(steps + 1):
                a = a0 + (math.pi / 2) * i / steps
                pts.extend([cx + r * math.cos(a), cy + r * math.sin(a)])
        return pts

    def _draw_bg(self, c) -> None:
        pts = self._rounded_rect(2, 2, WIN_W - 2, WIN_H - 2, CORNER_R)
        c.create_polygon(pts, fill=PANEL_BG, outline="", smooth=False)

    def _draw_grid(self, c) -> None:
        for x in range(CORNER_R, WIN_W - CORNER_R, 24):
            c.create_line(x, CORNER_R, x, WIN_H - CORNER_R, fill=GRID_COLOR, width=1)
        for y in range(CORNER_R, WIN_H - CORNER_R, 24):
            c.create_line(CORNER_R, y, WIN_W - CORNER_R, y, fill=GRID_COLOR, width=1)

    def _draw_border(self, c) -> None:
        pulse = 0.6 + 0.4 * math.sin(self._frame * 0.05)
        v = int(255 * pulse)
        color = f"#00{v:02x}{v:02x}"
        pts = self._rounded_rect(1, 1, WIN_W - 1, WIN_H - 1, CORNER_R)
        c.create_polygon(pts, fill="", outline=color, width=2, smooth=False)

    def _draw_corner_accents(self, c) -> None:
        a = 22
        corners = [
            (CORNER_R, 3, CORNER_R + a, 3, 3, CORNER_R, 3, CORNER_R + a),
            (WIN_W - CORNER_R, 3, WIN_W - CORNER_R - a, 3, WIN_W - 3, CORNER_R, WIN_W - 3, CORNER_R + a),
            (CORNER_R, WIN_H - 3, CORNER_R + a, WIN_H - 3, 3, WIN_H - CORNER_R, 3, WIN_H - CORNER_R - a),
            (WIN_W - CORNER_R, WIN_H - 3, WIN_W - CORNER_R - a, WIN_H - 3, WIN_W - 3, WIN_H - CORNER_R, WIN_W - 3, WIN_H - CORNER_R - a),
        ]
        for hx1, hy1, hx2, hy2, vx1, vy1, vx2, vy2 in corners:
            c.create_line(hx1, hy1, hx2, hy2, fill=CYAN, width=2)
            c.create_line(vx1, vy1, vx2, vy2, fill=CYAN, width=2)

    def _draw_scanline(self, c) -> None:
        y = int((self._frame * 1.5) % WIN_H)
        if CORNER_R < y < WIN_H - CORNER_R:
            c.create_line(CORNER_R, y, WIN_W - CORNER_R, y, fill=CYAN_DARK, width=1)

    def _draw_title(self, c) -> None:
        pulse = 0.8 + 0.2 * math.sin(self._frame * 0.04)
        v = int(255 * pulse)
        color = f"#00{v:02x}{v:02x}"
        c.create_text(
            WIN_W // 2, 45,
            text="A U R I X", fill=color,
            font=("Consolas", 22, "bold"), anchor="center",
        )
        c.create_text(
            WIN_W // 2, 72,
            text="PERSONAL AI ASSISTANT", fill=CYAN_DIM,
            font=("Consolas", 9), anchor="center",
        )
        c.create_line(BAR_PAD, 88, WIN_W - BAR_PAD, 88, fill=CYAN_DARK, width=1)

    def _draw_progress_bar(self, c, pct: float) -> None:
        bar_y = 130
        x1 = BAR_PAD
        x2 = WIN_W - BAR_PAD
        bar_w = x2 - x1

        c.create_rectangle(x1, bar_y, x2, bar_y + BAR_H, outline=CYAN_DIM, width=1)

        fill_w = int(bar_w * pct / 100.0)
        if fill_w > 0:
            glow_pulse = 0.7 + 0.3 * math.sin(self._frame * 0.1)
            v = int(255 * glow_pulse)
            bar_color = f"#00{v:02x}{v:02x}"
            c.create_rectangle(
                x1 + 1, bar_y + 1, x1 + fill_w, bar_y + BAR_H - 1,
                fill=bar_color, outline="",
            )
            c.create_rectangle(
                x1 + 1, bar_y + 1, x1 + fill_w, bar_y + BAR_H // 2,
                fill=CYAN, outline="", stipple="gray50",
            )

    def _draw_status(self, c, status: str, pct: float) -> None:
        bar_y = 130

        blocks_total = 10
        blocks_filled = int(blocks_total * pct / 100.0)
        bar_text = "\u2593" * blocks_filled + "\u2591" * (blocks_total - blocks_filled)
        pct_str = f"{bar_text} {int(pct)}%"

        c.create_text(
            WIN_W // 2, bar_y + BAR_H + 18,
            text=pct_str, fill=CYAN,
            font=("Consolas", 10), anchor="center",
        )
        c.create_text(
            WIN_W // 2, bar_y + BAR_H + 38,
            text=status, fill=WHITE,
            font=("Consolas", 10), anchor="center",
        )

        dots = "." * ((self._frame // 10) % 4)
        c.create_text(
            WIN_W // 2, bar_y + BAR_H + 70,
            text=f"Please wait{dots}", fill=TEXT_DIM,
            font=("Consolas", 9), anchor="center",
        )

    def _draw_mode_buttons(self, c) -> None:
        c.create_text(
            WIN_W // 2, 110,
            text="SELECT MODE", fill=CYAN,
            font=("Consolas", 12, "bold"), anchor="center",
        )

        btn_w = 150
        btn_h = 60
        gap = 20
        total = btn_w * 2 + gap
        left_x = (WIN_W - total) // 2
        right_x = left_x + btn_w + gap
        btn_y = 150

        hover_pulse = 0.6 + 0.4 * math.sin(self._frame * 0.08)
        v = int(180 * hover_pulse)

        # Silent mode button
        silent_color = f"#00{v:02x}{max(0, v - 40):02x}"
        c.create_rectangle(
            left_x, btn_y, left_x + btn_w, btn_y + btn_h,
            outline=CYAN_DIM, width=2, fill="#001a22",
        )
        c.create_text(
            left_x + btn_w // 2, btn_y + 22,
            text="Silent Mode", fill=silent_color,
            font=("Consolas", 11, "bold"), anchor="center",
        )
        c.create_text(
            left_x + btn_w // 2, btn_y + 43,
            text="Text Input", fill=TEXT_DIM,
            font=("Consolas", 8), anchor="center",
        )

        # Speech mode button
        speech_color = f"#00{v:02x}{v:02x}"
        c.create_rectangle(
            right_x, btn_y, right_x + btn_w, btn_y + btn_h,
            outline=CYAN, width=2, fill="#001a22",
        )
        c.create_text(
            right_x + btn_w // 2, btn_y + 22,
            text="Speech Mode", fill=speech_color,
            font=("Consolas", 11, "bold"), anchor="center",
        )
        c.create_text(
            right_x + btn_w // 2, btn_y + 43,
            text="Voice Control", fill=TEXT_DIM,
            font=("Consolas", 8), anchor="center",
        )

        # Status text
        c.create_text(
            WIN_W // 2, btn_y + btn_h + 30,
            text="Click to select your interaction mode", fill=TEXT_DIM,
            font=("Consolas", 8), anchor="center",
        )

        # Bind click regions
        self._btn_silent_bounds = (left_x, btn_y, left_x + btn_w, btn_y + btn_h)
        self._btn_speech_bounds = (right_x, btn_y, right_x + btn_w, btn_y + btn_h)
        self._canvas.bind("<Button-1>", self._on_click)

    def _on_click(self, event) -> None:
        with self._lock:
            if self._phase != "selecting":
                return

        x, y = event.x, event.y

        if hasattr(self, "_btn_silent_bounds"):
            bx1, by1, bx2, by2 = self._btn_silent_bounds
            if bx1 <= x <= bx2 and by1 <= y <= by2:
                self._chosen_mode = "silent"
                self._close()
                return

        if hasattr(self, "_btn_speech_bounds"):
            bx1, by1, bx2, by2 = self._btn_speech_bounds
            if bx1 <= x <= bx2 and by1 <= y <= by2:
                self._chosen_mode = "speech"
                self._close()
                return

    def _close(self) -> None:
        try:
            if self._root is not None:
                self._root.destroy()
        except Exception:
            pass


def run_startup_with_steps(
    steps: list,
    on_complete: Optional[Callable] = None,
) -> str:
    """Run the startup screen with simulated loading steps.

    *steps* is a list of (pct, label) tuples.  Returns chosen mode string.
    The loading animation runs in a background thread that feeds the GUI.
    """
    screen = StartupScreen()

    def _feed():
        screen.wait_for_window()
        for pct, label in steps:
            screen.set_progress(pct, label)
            time.sleep(0.45)
        screen.finish_loading()
        if on_complete:
            on_complete()

    feeder = threading.Thread(target=_feed, daemon=True)
    feeder.start()

    return screen.run()
