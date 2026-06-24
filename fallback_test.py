"""Simula el caso de la compañera: un encoder que NO arranca -> la app debe
reintentar con libx264 (CPU) y grabar igualmente."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

from capturapro import ffmpeg_utils
from capturapro.monitors import primary_monitor, set_dpi_awareness
from capturapro.recorder import Recorder, RecorderError

set_dpi_awareness()
ff = ffmpeg_utils.find_ffmpeg("")
mon = primary_monitor()
work = tempfile.gettempdir()
out = str(Path(work) / "capturapro_fallback.mp4")
log = out + ".log"
Path(out).unlink(missing_ok=True)


def make_bad(seg: str) -> list[str]:
    cmd = ffmpeg_utils.build_record_command(
        ffmpeg_path=ff, region=mon.region, fps=30, encoder="libx264",
        quality_key="media", capture_cursor=True, output_path=seg)
    i = cmd.index("-c:v")              # rompe el encoder para forzar el fallo
    cmd[i + 1] = "encoder_inexistente"
    return cmd


def make_good(seg: str) -> list[str]:
    return ffmpeg_utils.build_record_command(
        ffmpeg_path=ff, region=mon.region, fps=30, encoder="libx264",
        quality_key="media", capture_cursor=True, output_path=seg)


rec = Recorder()
ok_detected = False

# 1) Intento con encoder roto -> debe detectarse el fallo
rec.start(make_bad, out, work, ff, log)
try:
    rec.check_started(1.2)
    print("[FAIL] el encoder roto deberia haber fallado")
except RecorderError:
    ok_detected = True
    print("[OK ] encoder roto detectado por check_started")

# 2) Fallback: limpiar y reintentar con libx264
rec.stop()
rec.start(make_good, out, work, ff, log)
rec.check_started(1.0)
print("[OK ] reintento con libx264 arranco")
time.sleep(1.5)
path = rec.stop()

ok_video = bool(path) and Path(path).is_file() and Path(path).stat().st_size > 1000
leftovers = list(Path(work).glob(".capturapro_seg_*"))
print(f"[{'OK ' if ok_video else 'FAIL'}] video del fallback: {path} ({'existe' if ok_video else 'NO'})")
print(f"segmentos temporales restantes: {[p.name for p in leftovers]}")

result = ok_detected and ok_video and not leftovers
print("RESULTADO:", "OK" if result else "FAIL")
sys.exit(0 if result else 1)
