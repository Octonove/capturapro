"""Captura de imagenes con mss -> PIL.Image."""

from __future__ import annotations

import logging

import mss
from PIL import Image

logger = logging.getLogger(__name__)


def _grab(region: dict) -> Image.Image:
    # mss no es seguro entre hilos: instancia nueva en cada captura.
    with mss.mss() as sct:
        shot = sct.grab(region)
    return Image.frombytes("RGB", shot.size, shot.rgb)


def capture_region(left: int, top: int, width: int, height: int) -> Image.Image:
    return _grab({"left": left, "top": top, "width": width, "height": height})


def capture_monitor(left: int, top: int, width: int, height: int) -> Image.Image:
    return _grab({"left": left, "top": top, "width": width, "height": height})


def capture_virtual() -> Image.Image:
    """Captura todo el escritorio virtual (todas las pantallas)."""
    with mss.mss() as sct:
        m = sct.monitors[0]
        shot = sct.grab(m)
    return Image.frombytes("RGB", shot.size, shot.rgb)
