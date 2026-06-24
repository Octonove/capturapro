"""Pruebas headless de la logica que no requiere interfaz grafica."""

from __future__ import annotations

import sys

from PIL import Image

from capturapro import ffmpeg_utils, screenshot
from capturapro.config import load_config
from capturapro.editor import Annotation, render_annotations
from capturapro.monitors import get_virtual_screen, list_monitors, set_dpi_awareness

ok = True


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok
    mark = "OK " if cond else "FAIL"
    if not cond:
        ok = False
    print(f"[{mark}] {name} {detail}")


set_dpi_awareness()

# --- Config ---
cfg = load_config()
check("config carga", cfg is not None, f"img={cfg.image_format} q={cfg.video_quality}")

# --- FFmpeg ---
ff = ffmpeg_utils.find_ffmpeg(cfg.ffmpeg_path)
check("ffmpeg encontrado", bool(ff), f"-> {ff}")
encoders = ffmpeg_utils.list_encoders(ff) if ff else set()
check("encoders listados", "libx264" in encoders, f"-> {sorted(encoders)}")
audio = ffmpeg_utils.list_audio_devices(ff) if ff else []
print(f"      audio dshow: {audio}")

# --- Monitores ---
mons = list_monitors()
check("monitores detectados", len(mons) >= 1, f"-> {[m.label for m in mons]}")
vx, vy, vw, vh = get_virtual_screen()
check("escritorio virtual", vw > 0 and vh > 0, f"-> {vx},{vy} {vw}x{vh}")

# --- Comando de grabacion ---
if ff:
    cmd = ffmpeg_utils.build_record_command(
        ffmpeg_path=ff,
        region=(vx, vy, vw, vh),
        fps=30,
        encoder=ffmpeg_utils.resolve_encoder("auto", encoders),
        quality_key="alta",
        capture_cursor=True,
        output_path="salida_test.mp4",
    )
    check("comando gdigrab", "gdigrab" in cmd and ("-crf" in cmd or "-cq" in cmd), "")
    print("      cmd:", " ".join(cmd))

# --- Captura real de pantalla ---
try:
    img = screenshot.capture_virtual()
    check("captura virtual", img.size[0] > 0 and img.size[1] > 0, f"-> {img.size}")
except Exception as exc:  # noqa: BLE001
    check("captura virtual", False, f"ERROR: {exc}")

# --- Renderizado de anotaciones (exportacion sin perdida) ---
base = Image.new("RGB", (400, 300), (240, 240, 240))
anns = [
    Annotation("arrow", "#ff0000", 5, [(20, 20), (200, 150)]),
    Annotation("rect", "#0000ff", 3, [(50, 50), (300, 200)]),
    Annotation("ellipse", "#00aa00", 3, [(120, 120), (260, 240)]),
    Annotation("highlight", "#ffff00", 14, [(30, 250), (370, 255)]),
    Annotation("pen", "#aa00aa", 4, [(40, 80), (90, 60), (140, 90)]),
    Annotation("text", "#000000", 4, [(60, 30)], text="Hola mundo", font_size=28),
]
out = render_annotations(base, anns)
check("render anotaciones", out.size == (400, 300) and out.mode == "RGB", f"-> {out.size}")
out.save("render_test.png")
print("      guardado render_test.png")

print("\nRESULTADO:", "TODO OK" if ok else "HAY FALLOS")
sys.exit(0 if ok else 1)
