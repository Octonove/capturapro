"""Captura la ventana real de la app (con el tema aplicado) a un PNG para revision visual."""
import sys
import time
import tkinter as tk

import mss
from PIL import Image

from capturapro.app import App
from capturapro.config import load_config
from capturapro.monitors import set_dpi_awareness

set_dpi_awareness()
cfg = load_config()
cfg.hotkeys_enabled = False
root = tk.Tk()
App(root, cfg)
root.geometry("+140+120")
root.attributes("-topmost", True)
root.lift()
root.focus_force()
root.update_idletasks()
root.update()
time.sleep(0.8)
root.update()
x, y = root.winfo_rootx(), root.winfo_rooty()
w, h = root.winfo_width(), root.winfo_height()
region = {"left": x - 12, "top": y - 42, "width": w + 24, "height": h + 54}
with mss.mss() as sct:
    shot = sct.grab(region)
img = Image.frombytes("RGB", shot.size, shot.rgb)
out = sys.argv[1] if len(sys.argv) > 1 else "ui_capturapro.png"
img.save(out)
print("saved", out, img.size)
root.destroy()
