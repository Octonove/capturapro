"""Copiar una imagen PIL al portapapeles de Windows (formato CF_DIB)."""

from __future__ import annotations

import ctypes
import io
import logging
from ctypes import wintypes

from PIL import Image

logger = logging.getLogger(__name__)

CF_DIB = 8
GMEM_MOVEABLE = 0x0002


def copy_image(image: Image.Image) -> bool:
    """Coloca `image` en el portapapeles. Devuelve True si tuvo exito."""
    try:
        output = io.BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]  # quitar cabecera BITMAPFILEHEADER (14 bytes)
        output.close()
    except (OSError, ValueError) as exc:
        logger.error("No se pudo convertir la imagen a DIB: %s", exc)
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

    if not user32.OpenClipboard(None):
        logger.error("No se pudo abrir el portapapeles")
        return False
    try:
        user32.EmptyClipboard()
        h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h_global:
            return False
        ptr = kernel32.GlobalLock(h_global)
        if not ptr:
            kernel32.GlobalFree(h_global)
            return False
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(h_global)
        if not user32.SetClipboardData(CF_DIB, h_global):
            kernel32.GlobalFree(h_global)
            return False
        return True
    finally:
        user32.CloseClipboard()
