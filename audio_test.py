"""Graba ~2.5s con AUDIO DEL SISTEMA (loopback WASAPI) y verifica que el video
final tiene pista de audio y que no quedan temporales."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from capturapro import ffmpeg_utils
from capturapro.audio_capture import AVAILABLE, AudioCapture
from capturapro.monitors import primary_monitor, set_dpi_awareness
from capturapro.recorder import Recorder

set_dpi_awareness()
if not AVAILABLE:
    print("FAIL: soundcard no disponible")
    sys.exit(1)

ff = ffmpeg_utils.find_ffmpeg("")
mon = primary_monitor()
work = tempfile.gettempdir()
out = str(Path(work) / "capturapro_audiotest.mp4")
log = out + ".log"
Path(out).unlink(missing_ok=True)
enc = ffmpeg_utils.resolve_encoder("auto", ffmpeg_utils.list_encoders(ff))


def make_cmd(seg: str) -> list[str]:
    return ffmpeg_utils.build_record_command(
        ffmpeg_path=ff, region=mon.region, fps=30, encoder=enc,
        quality_key="media", capture_cursor=True, output_path=seg)


rec = Recorder()
audio = AudioCapture(system=True, mic_name=None, work_dir=work)
rec.start(make_cmd, out, work, ff, log, audio=audio)
rec.check_started(1.0)
print("grabando 2.5s con audio del sistema (loopback)...")
time.sleep(2.5)
path = rec.stop()
print("stop ->", path)
if not path:
    print("FAIL: no se genero video")
    print(Path(log).read_text(errors="replace")[-600:])
    sys.exit(1)

ffprobe = ffmpeg_utils.ffprobe_from(ff)
info = subprocess.run(
    [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,codec_name",
     "-of", "default=noprint_wrappers=1", path],
    capture_output=True, text=True, **ffmpeg_utils.subprocess_kwargs())
print(info.stdout.strip())

has_video = "codec_type=video" in info.stdout
has_audio = "codec_type=audio" in info.stdout
leftovers = (list(Path(work).glob(".capturapro_*.wav"))
             + list(Path(work).glob(".capturapro_video*"))
             + list(Path(work).glob(".capturapro_seg_*")))
print("temporales restantes (debe ser []):", [p.name for p in leftovers])
print(f"video={has_video}  audio={has_audio}")

ok = has_video and has_audio and not leftovers
print("RESULTADO:", "OK" if ok else "FAIL")
sys.exit(0 if ok else 1)
