"""Prueba real de grabacion con pausa/reanudar (segmentos + concat)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from capturapro import ffmpeg_utils
from capturapro.monitors import primary_monitor, set_dpi_awareness
from capturapro.recorder import Recorder

set_dpi_awareness()

ff = ffmpeg_utils.find_ffmpeg("")
assert ff, "ffmpeg no encontrado"
encoders = ffmpeg_utils.list_encoders(ff)
enc = ffmpeg_utils.resolve_encoder("auto", encoders)
mon = primary_monitor()
work = tempfile.gettempdir()
out = str(Path(work) / "capturapro_rectest.mp4")
log = out + ".log"
Path(out).unlink(missing_ok=True)
print(f"Encoder: {enc}  Region: {mon.region}")


def make_cmd(seg: str) -> list[str]:
    return ffmpeg_utils.build_record_command(
        ffmpeg_path=ff, region=mon.region, fps=30, encoder=enc,
        quality_key="media", capture_cursor=True, output_path=seg,
    )


rec = Recorder()
rec.start(make_cmd, out, work, ff, log)
try:
    rec.check_started(1.0)
except Exception as exc:  # noqa: BLE001
    print("FALLO al iniciar:", exc)
    sys.exit(1)

print("segmento 1 (2s)...")
time.sleep(2.0)
print("PAUSA (2s de pausa, no se graba)...")
rec.pause()
assert rec.is_paused and rec.is_active
time.sleep(2.0)
print("REANUDAR -> segmento 2 (2s)...")
rec.resume()
rec.check_started(1.0)
assert not rec.is_paused
time.sleep(2.0)

path = rec.stop()
print("stop() ->", path)
if not path or not Path(path).is_file():
    print("FAIL: no se genero el video")
    print(Path(log).read_text(errors="replace")[-800:])
    sys.exit(1)

size = Path(path).stat().st_size
print(f"Tamano: {size/1024:.1f} KB")

# Comprobar que NO quedan segmentos temporales
leftovers = list(Path(work).glob(".capturapro_seg_*"))
print("Segmentos temporales restantes (debe ser []):", [p.name for p in leftovers])

ffprobe = ffmpeg_utils.ffprobe_from(ff)
dur = None
if ffprobe:
    info = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, **ffmpeg_utils.subprocess_kwargs(),
    )
    try:
        dur = float(info.stdout.strip())
    except ValueError:
        dur = None
    # Cada segmento graba ~3s (settle 1s de check_started + 2s de sleep); 2
    # segmentos = ~6s, con la pausa de 2s EXCLUIDA (si no, seria ~8s+).
    print(f"Duracion del video final: {dur} s (esperado ~6s = 2 segmentos, pausa de 2s excluida)")

ok = size > 1000 and not leftovers and (dur is None or 4.0 <= dur <= 8.0)
print("RESULTADO:", "OK" if ok else "FAIL")
sys.exit(0 if ok else 1)
