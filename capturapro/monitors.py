"""Deteccion de monitores y geometria del escritorio virtual.

Trabajamos siempre en pixeles fisicos (DPI-aware) para que las coordenadas
coincidan entre Tkinter, mss y FFmpeg/gdigrab.
"""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass

import mss

logger = logging.getLogger(__name__)


def set_dpi_awareness() -> None:
    """Hace el proceso 'per-monitor DPI aware' para coordenadas fisicas.

    Debe llamarse antes de crear la ventana Tk.
    """
    try:
        # Windows 10 1703+: PER_MONITOR_AWARE_V2 = -4
        ctx = ctypes.c_void_p(-4)
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctx):
            return
    except (AttributeError, OSError):
        pass
    try:
        # Windows 8.1+: PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass


@dataclass
class Monitor:
    index: int          # 1..N (1 = primer monitor)
    left: int
    top: int
    width: int
    height: int
    primary: bool

    @property
    def label(self) -> str:
        if self.index == 0:
            return f"Todo el escritorio: {self.width}x{self.height} (todas las pantallas)"
        tag = " (principal)" if self.primary else ""
        return f"Pantalla {self.index}: {self.width}x{self.height}{tag}"

    @property
    def region(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.width, self.height)


def list_monitors() -> list[Monitor]:
    """Devuelve la lista de monitores fisicos (sin el monitor 'virtual')."""
    out: list[Monitor] = []
    with mss.mss() as sct:
        # sct.monitors[0] = escritorio virtual completo; [1:] = cada pantalla
        for i, mon in enumerate(sct.monitors[1:], start=1):
            primary = mon["left"] == 0 and mon["top"] == 0
            out.append(
                Monitor(
                    index=i,
                    left=mon["left"],
                    top=mon["top"],
                    width=mon["width"],
                    height=mon["height"],
                    primary=primary,
                )
            )
    if not out:
        # Fallback: un solo monitor segun metricas del sistema
        vx, vy, vw, vh = get_virtual_screen()
        out.append(Monitor(1, vx, vy, vw, vh, True))
    return out


def primary_monitor() -> Monitor:
    """Devuelve el monitor principal (su esquina superior izquierda es 0,0)."""
    mons = list_monitors()
    for m in mons:
        if m.primary:
            return m
    # Defensa: si ninguno quedo marcado, elige el que contiene el origen (0,0)
    # del escritorio (el principal en Windows), no el primero que enumere mss.
    for m in mons:
        if m.left <= 0 < m.left + m.width and m.top <= 0 < m.top + m.height:
            return m
    return mons[0]


def virtual_monitor() -> Monitor:
    """Monitor sintetico que representa todo el escritorio virtual."""
    vx, vy, vw, vh = get_virtual_screen()
    return Monitor(index=0, left=vx, top=vy, width=vw, height=vh, primary=False)


def get_virtual_screen() -> tuple[int, int, int, int]:
    """(left, top, width, height) del escritorio virtual completo."""
    try:
        u = ctypes.windll.user32
        SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
        SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
        x = u.GetSystemMetrics(SM_XVIRTUALSCREEN)
        y = u.GetSystemMetrics(SM_YVIRTUALSCREEN)
        w = u.GetSystemMetrics(SM_CXVIRTUALSCREEN)
        h = u.GetSystemMetrics(SM_CYVIRTUALSCREEN)
        if w and h:
            return x, y, w, h
    except (AttributeError, OSError) as exc:
        logger.warning("get_virtual_screen fallo: %s", exc)
    with mss.mss() as sct:
        m = sct.monitors[0]
        return m["left"], m["top"], m["width"], m["height"]
