"""Overlay a pantalla completa para seleccionar un area con el raton.

Cubre todo el escritorio virtual (multimonitor). Devuelve la region en
coordenadas fisicas absolutas, listas para mss y FFmpeg/gdigrab.
"""

from __future__ import annotations

import logging
import tkinter as tk

from .monitors import get_virtual_screen, primary_monitor

logger = logging.getLogger(__name__)

DIM = 0.35
ACCENT = "#28c2ff"


class RegionSelector:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.result: tuple[int, int, int, int] | None = None
        self._start: tuple[int, int] | None = None
        self._rect = None
        self._label = None

    def select(self) -> tuple[int, int, int, int] | None:
        vx, vy, vw, vh = get_virtual_screen()
        self._vx, self._vy = vx, vy

        top = tk.Toplevel(self.root)
        self.top = top
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        try:
            top.attributes("-alpha", DIM)
        except tk.TclError:
            pass
        top.geometry(f"{vw}x{vh}+{vx}+{vy}")
        top.configure(bg="black", cursor="crosshair")

        cv = tk.Canvas(top, bg="black", highlightthickness=0, cursor="crosshair")
        cv.pack(fill="both", expand=True)
        self.cv = cv

        # Instrucciones centradas sobre el MONITOR PRINCIPAL (no sobre el centro
        # del escritorio virtual, que en multimonitor cae en otra pantalla).
        try:
            pm = primary_monitor()
            cx = (pm.left - vx) + pm.width // 2
            cy = max(40, (pm.top - vy) + 40)
        except Exception:  # noqa: BLE001
            cx, cy = vw // 2, 40
        cv.create_text(
            cx, cy,
            text="Arrastra para seleccionar el area    -    Esc o clic derecho para cancelar",
            fill="white", font=("Segoe UI", 16, "bold"),
        )

        cv.bind("<Button-1>", self._on_press)
        cv.bind("<B1-Motion>", self._on_drag)
        cv.bind("<ButtonRelease-1>", self._on_release)
        top.bind("<Escape>", lambda e: self._cancel())
        cv.bind("<Button-3>", lambda e: self._cancel())

        top.focus_force()
        top.grab_set()
        self.root.wait_window(top)
        return self.result

    def _on_press(self, event: tk.Event) -> None:
        self._start = (event.x, event.y)
        if self._rect:
            self.cv.delete(self._rect)
        self._rect = self.cv.create_rectangle(
            event.x, event.y, event.x, event.y, outline=ACCENT, width=2
        )

    def _on_drag(self, event: tk.Event) -> None:
        if not self._start:
            return
        x0, y0 = self._start
        self.cv.coords(self._rect, x0, y0, event.x, event.y)
        w, h = abs(event.x - x0), abs(event.y - y0)
        if self._label:
            self.cv.delete(self._label)
        lx = min(x0, event.x) + w // 2
        ly = max(min(y0, event.y) - 14, 10)
        self._label = self.cv.create_text(
            lx, ly, text=f"{w} x {h}", fill=ACCENT, font=("Segoe UI", 12, "bold")
        )

    def _on_release(self, event: tk.Event) -> None:
        if not self._start:
            self._cancel()
            return
        x0, y0 = self._start
        x1, y1 = event.x, event.y
        left = min(x0, x1) + self._vx
        top = min(y0, y1) + self._vy
        width = abs(x1 - x0)
        height = abs(y1 - y0)
        self.top.grab_release()
        self.top.destroy()
        if width < 8 or height < 8:
            self.result = None
        else:
            self.result = (left, top, width, height)

    def _cancel(self) -> None:
        self.result = None
        try:
            self.top.grab_release()
            self.top.destroy()
        except tk.TclError:
            pass
