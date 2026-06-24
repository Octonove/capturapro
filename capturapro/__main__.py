"""Punto de entrada de CapturaPro."""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import messagebox

from . import APP_NAME
from .app import App
from .config import load_config, setup_logging
from .monitors import set_dpi_awareness

logger = logging.getLogger(__name__)


def _log_excepthook(exc_type, exc, tb) -> None:
    # En build windowed no hay stderr; registra las excepciones no controladas.
    logger.error("Excepcion no controlada", exc_info=(exc_type, exc, tb))


def main() -> None:
    try:
        setup_logging()
    except Exception:  # noqa: BLE001
        pass
    import sys
    sys.excepthook = _log_excepthook

    try:
        set_dpi_awareness()
        config = load_config()
        root = tk.Tk()
        app = App(root, config)
        root.protocol("WM_DELETE_WINDOW", app.on_close)
        root.mainloop()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo al iniciar CapturaPro")
        try:
            messagebox.showerror(APP_NAME, f"Error al iniciar CapturaPro:\n{exc}")
        except Exception:  # noqa: BLE001
            pass
        raise


if __name__ == "__main__":
    main()
