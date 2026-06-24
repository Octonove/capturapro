"""Atajos de teclado globales para Windows (RegisterHotKey via ctypes).

Funcionan aunque la app no tenga el foco. Un hilo dedicado registra los atajos
y corre su propio bucle de mensajes; las pulsaciones se encolan y se despachan
en el hilo de Tk (seguro) mediante un sondeo con root.after.
"""

from __future__ import annotations

import ctypes
import logging
import queue
import threading
import tkinter as tk
from ctypes import wintypes

logger = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


class GlobalHotkeys:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        # cada binding: (id, modifiers, vk, callback, nombre)
        self._bindings: list[tuple[int, int, int, object, str]] = []
        self._queue: queue.Queue[int] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._started = threading.Event()  # senal: el hilo ya publico su id
        self._next_id = 1
        self._running = False

    def add(self, modifiers: int, vk: int, callback, name: str = "") -> None:
        hid = self._next_id
        self._next_id += 1
        self._bindings.append((hid, modifiers | MOD_NOREPEAT, vk, callback, name))

    def start(self) -> None:
        if self._running or not self._bindings:
            return
        self._running = True
        self._started.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._poll()

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        self._started.set()  # publica el id ANTES de registrar/bloquear
        registered: list[int] = []
        for hid, mod, vk, _cb, name in self._bindings:
            if user32.RegisterHotKey(None, hid, mod, vk):
                registered.append(hid)
            else:
                logger.warning("No se pudo registrar el atajo %s (en uso por otra app).", name)
        msg = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret in (0, -1):
                break
            if msg.message == WM_HOTKEY:
                self._queue.put(int(msg.wParam))
        for hid in registered:
            user32.UnregisterHotKey(None, hid)

    def _poll(self) -> None:
        try:
            while True:
                hid = self._queue.get_nowait()
                self._dispatch(hid)
        except queue.Empty:
            pass
        if self._running:
            try:
                self.root.after(120, self._poll)
            except tk.TclError:
                pass

    def _dispatch(self, hid: int) -> None:
        for b in self._bindings:
            if b[0] == hid:
                try:
                    b[3]()
                except Exception:  # noqa: BLE001
                    logger.exception("Error ejecutando el atajo %s", b[4])
                return

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        # Espera a que el hilo haya publicado su id, para no perder el WM_QUIT
        # (si no, el bucle GetMessageW quedaria colgado y los atajos sin liberar).
        self._started.wait(timeout=2.0)
        if self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except OSError:
                pass
