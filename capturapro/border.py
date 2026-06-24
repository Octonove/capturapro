"""Marco visual que rodea el area que se esta grabando.

Las barras se dibujan JUSTO FUERA del area capturada (gdigrab captura solo el
rectangulo [left, top, width, height]), por lo que el marco es visible para el
usuario pero NO aparece en el video. Las ventanas son click-through.
"""

from __future__ import annotations

import ctypes
import logging
import tkinter as tk

from .theme import DANGER, DANGER_DIM

logger = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000


class RecordingBorder:
    def __init__(self, root: tk.Misc):
        self.root = root
        self._bars: list[tk.Toplevel] = []
        self._after = None
        self._on = True

    def show(self, left: int, top: int, width: int, height: int, thickness: int = 3) -> None:
        self.hide()
        b = thickness
        # 4 barras justo FUERA del area [left, top, width, height]
        rects = [
            (left - b, top - b, width + 2 * b, b),       # arriba
            (left - b, top + height, width + 2 * b, b),  # abajo
            (left - b, top, b, height),                  # izquierda
            (left + width, top, b, height),              # derecha
        ]
        for (x, y, w, h) in rects:
            try:
                win = tk.Toplevel(self.root)
                win.overrideredirect(True)
                win.attributes("-topmost", True)
                win.configure(bg=DANGER)
                win.geometry(f"{max(1, w)}x{max(1, h)}+{int(x)}+{int(y)}")
                self._click_through(win)
                self._bars.append(win)
            except tk.TclError as exc:
                logger.debug("No se pudo crear barra del marco: %s", exc)
        self._on = True
        self._blink()

    def _click_through(self, win: tk.Toplevel) -> None:
        try:
            win.update_idletasks()
            hwnd = win.winfo_id()
            u = ctypes.windll.user32
            ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u.SetWindowLongW(hwnd, GWL_EXSTYLE,
                             ex | WS_EX_LAYERED | WS_EX_TRANSPARENT
                             | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)
        except (OSError, AttributeError, tk.TclError):
            pass

    def _blink(self) -> None:
        if not self._bars:
            return
        self._on = not self._on
        col = DANGER if self._on else DANGER_DIM
        for w in self._bars:
            try:
                w.configure(bg=col)
            except tk.TclError:
                pass
        try:
            self._after = self.root.after(650, self._blink)
        except tk.TclError:
            pass

    def hide(self) -> None:
        if self._after is not None:
            try:
                self.root.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None
        for w in self._bars:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self._bars = []
