"""Verifica que el control flotante de grabacion queda VISIBLE y en el
monitor principal (regresion del bug: iconify ocultaba el control)."""

from __future__ import annotations

import sys
import tkinter as tk

from capturapro.app import App
from capturapro.config import load_config
from capturapro.monitors import primary_monitor, set_dpi_awareness

set_dpi_awareness()
cfg = load_config()
cfg.hotkeys_enabled = False

root = tk.Tk()
app = App(root, cfg)
root.update()

# Crea el control flotante (sin grabacion real; el timer se auto-ignora)
app._show_rec_control()
root.update()
root.after(150, root.quit)
root.mainloop()

ctrl = app._rec_control
mon = primary_monitor()
if ctrl is None:
    print("FAIL: no se creo el control")
    sys.exit(1)

viewable = bool(ctrl.winfo_viewable())
x, y = ctrl.winfo_rootx(), ctrl.winfo_rooty()
on_primary = mon.left <= x < mon.left + mon.width and mon.top <= y < mon.top + mon.height
print(f"control viewable: {viewable}")
print(f"control pos: ({x},{y})")
print(f"monitor principal: left={mon.left} top={mon.top} {mon.width}x{mon.height}")
print(f"en monitor principal: {on_primary}")

# La ventana principal debe haberse apartado fuera de pantalla (no minimizada)
main_y = root.winfo_rooty()
print(f"ventana principal apartada a y={main_y} (deberia estar fuera de pantalla)")

try:
    ctrl.destroy()
except tk.TclError:
    pass
root.destroy()

ok = viewable and on_primary
print("RESULTADO:", "OK" if ok else "FAIL")
sys.exit(0 if ok else 1)
