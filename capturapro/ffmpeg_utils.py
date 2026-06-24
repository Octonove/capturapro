"""Localizacion de FFmpeg, deteccion de dispositivos/encoders y construccion
de comandos de grabacion."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .config import VIDEO_QUALITY

logger = logging.getLogger(__name__)

# Evita que aparezcan ventanas de consola al lanzar subprocesos en la app GUI.
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _subprocess_kwargs() -> dict:
    kw: dict = {}
    if os.name == "nt":
        kw["creationflags"] = CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kw["startupinfo"] = si
    return kw


def _decode(raw) -> str:
    """Decodifica la salida de FFmpeg de forma robusta.

    FFmpeg en Windows emite a veces UTF-8 y a veces la pagina de codigos ANSI
    (cp1252) segun el contexto. Probamos UTF-8 y, si no es valido, caemos a la
    pagina ANSI del sistema ('mbcs'), de modo que los nombres con acentos
    (p. ej. "Microfono") salgan siempre correctos.
    """
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("mbcs")
        except (UnicodeDecodeError, LookupError):
            return raw.decode("utf-8", errors="replace")


def _app_dir() -> Path:
    """Directorio donde vive el ejecutable/script (para FFmpeg empaquetado)."""
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: el .exe esta en dist/CapturaPro/
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _candidate_paths() -> list[Path]:
    cands: list[Path] = []
    app = _app_dir()
    # FFmpeg empaquetado junto a la app
    for sub in ("", "ffmpeg", "_internal", "bin"):
        cands.append((app / sub / "ffmpeg.exe") if sub else (app / "ffmpeg.exe"))
    # Carpeta temporal de PyInstaller onefile
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        cands.append(Path(meipass) / "ffmpeg.exe")
    # Instalacion winget de Gyan FFmpeg
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        winget = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if winget.is_dir():
            cands.extend(winget.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"))
    return cands


def find_ffmpeg(override: str = "") -> str | None:
    """Devuelve la ruta a ffmpeg.exe o None si no se encuentra."""
    if override and Path(override).is_file():
        return override
    for c in _candidate_paths():
        try:
            if c.is_file():
                return str(c)
        except OSError:
            continue
    found = shutil.which("ffmpeg")
    if found:
        return found
    return None


def ffprobe_from(ffmpeg_path: str) -> str | None:
    p = Path(ffmpeg_path).with_name("ffprobe.exe")
    if p.is_file():
        return str(p)
    return shutil.which("ffprobe")


# ---------------------------------------------------------------------------
# Deteccion de capacidades
# ---------------------------------------------------------------------------
def list_encoders(ffmpeg_path: str) -> set[str]:
    """Conjunto de encoders de video H.264/H.265 disponibles."""
    wanted = {
        "libx264", "libx265", "h264_nvenc", "hevc_nvenc",
        "h264_amf", "h264_qsv", "libvpx-vp9",
    }
    try:
        out = _decode(subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            capture_output=True, timeout=20, **_subprocess_kwargs(),
        ).stdout)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("No se pudieron listar encoders: %s", exc)
        return {"libx264"}
    found = set()
    for name in wanted:
        if re.search(rf"\b{name}\b", out):
            found.add(name)
    found.add("libx264")  # asumimos siempre disponible como fallback
    return found


def list_audio_devices(ffmpeg_path: str) -> list[str]:
    """Lista de microfonos/dispositivos de audio dshow."""
    try:
        proc = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-list_devices", "true",
             "-f", "dshow", "-i", "dummy"],
            capture_output=True, timeout=20, **_subprocess_kwargs(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("No se pudieron listar dispositivos de audio: %s", exc)
        return []
    text = _decode(proc.stderr) + _decode(proc.stdout)
    devices: list[str] = []
    for m in re.finditer(r'"([^"]+)"\s*\((audio)\)', text):
        name = m.group(1)
        if name not in devices:
            devices.append(name)
    return devices


def best_default_encoder(available: set[str]) -> str:
    """Para 'auto' preferimos codificacion por hardware fiable (NVENC/AMF) y, si
    no hay, libx264 (CPU). Excluimos QSV de la autoseleccion porque es el mas
    fragil entre equipos (suele fallar al abrir el encoder); sigue disponible si
    el usuario lo elige manualmente. Ademas hay fallback automatico a libx264."""
    for enc in ("h264_nvenc", "h264_amf"):
        if enc in available:
            return enc
    return "libx264"


# ---------------------------------------------------------------------------
# Construccion del comando de grabacion
# ---------------------------------------------------------------------------
def _even(n: int) -> int:
    """libx264 (yuv420p) requiere dimensiones pares."""
    return n if n % 2 == 0 else n - 1


def resolve_encoder(name: str, available: set[str]) -> str:
    if name == "auto" or name not in available:
        return best_default_encoder(available)
    return name


def _quality_args(encoder: str, quality_key: str) -> list[str]:
    q = VIDEO_QUALITY.get(quality_key, VIDEO_QUALITY["alta"])
    if encoder in ("libx264", "libx265"):
        return ["-preset", q["x264_preset"], "-crf", str(q["x264_crf"])]
    if encoder in ("h264_nvenc", "hevc_nvenc"):
        # VBR guiado por calidad constante (CQ). -b:v 0 deja mandar al CQ.
        return ["-preset", q["nvenc_preset"], "-rc", "vbr",
                "-cq", str(q["nvenc_cq"]), "-b:v", "0"]
    if encoder == "h264_amf":
        # AMF: calidad por quanti. Aproximamos con qp_i/qp_p.
        cq = q["nvenc_cq"]
        return ["-quality", "quality", "-rc", "cqp",
                "-qp_i", str(cq), "-qp_p", str(cq)]
    if encoder == "h264_qsv":
        # Preset rapido: captura en tiempo real, evita perdida de fotogramas.
        return ["-global_quality", str(q["nvenc_cq"]), "-preset", "veryfast"]
    # fallback
    return ["-crf", str(VIDEO_QUALITY[quality_key]["x264_crf"])]


def build_record_command(
    *,
    ffmpeg_path: str,
    region: tuple[int, int, int, int],   # left, top, width, height (px fisicos)
    fps: int,
    encoder: str,
    quality_key: str,
    capture_cursor: bool,
    output_path: str,
) -> list[str]:
    """Comando de captura de VIDEO (sin audio). El audio se captura aparte
    (audio_capture.py) y se mezcla despues con build_mux_command()."""
    left, top, width, height = region
    width, height = _even(width), _even(height)

    cmd: list[str] = [ffmpeg_path, "-y", "-hide_banner", "-loglevel", "warning"]
    cmd += [
        "-f", "gdigrab",
        "-framerate", str(fps),
        "-draw_mouse", "1" if capture_cursor else "0",
        "-thread_queue_size", "1024",
        "-offset_x", str(left),
        "-offset_y", str(top),
        "-video_size", f"{width}x{height}",
        "-i", "desktop",
    ]
    is_hevc = encoder in ("libx265", "hevc_nvenc")
    cmd += ["-c:v", encoder]
    cmd += _quality_args(encoder, quality_key)
    cmd += ["-pix_fmt", "yuv420p", "-r", str(fps)]
    if is_hevc and output_path.lower().endswith(".mp4"):
        cmd += ["-tag:v", "hvc1"]  # compatibilidad HEVC en mp4
    cmd += ["-movflags", "+faststart", output_path]
    return cmd


def build_mux_command(ffmpeg_path: str, video_path: str, audio_paths: list[str],
                      output_path: str) -> list[str]:
    """Combina un video (sin audio) con una o varias pistas WAV -> mp4 (video
    copiado sin recodificar + audio AAC). Si hay varias pistas, las mezcla."""
    cmd = [ffmpeg_path, "-y", "-hide_banner", "-loglevel", "warning", "-i", video_path]
    for w in audio_paths:
        cmd += ["-i", w]
    if len(audio_paths) == 1:
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    else:
        mix = "".join(f"[{i + 1}:a]" for i in range(len(audio_paths)))
        mix += f"amix=inputs={len(audio_paths)}:duration=longest:normalize=0[a]"
        cmd += ["-filter_complex", mix, "-map", "0:v:0", "-map", "[a]"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", output_path]
    return cmd


def build_concat_command(ffmpeg_path: str, list_file: str, output_path: str) -> list[str]:
    """Une varios segmentos de video (mismo codec) sin recodificar."""
    return [
        ffmpeg_path, "-y", "-hide_banner", "-loglevel", "warning",
        "-f", "concat", "-safe", "0", "-i", list_file,
        "-c", "copy", "-movflags", "+faststart", output_path,
    ]


def convert_to_gif(ffmpeg_path: str, input_path: str, output_path: str,
                   fps: int = 15, width: int = 720,
                   log_path: str | None = None) -> tuple[bool, str]:
    """Convierte un video a GIF optimizado (dos pasadas con paleta)."""
    vf = f"[0:v]fps={fps},scale={width}:-1:flags=lanczos"
    palette = str(Path(output_path).with_suffix(".palette.png"))
    kw = _subprocess_kwargs()
    logf = open(log_path, "wb") if log_path else None
    err_target = logf if logf else subprocess.DEVNULL
    try:
        gen = subprocess.run(
            [ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
             "-i", input_path, "-vf", f"{vf},palettegen=stats_mode=diff", palette],
            stdout=subprocess.DEVNULL, stderr=err_target, timeout=600, **kw,
        )
        if gen.returncode != 0 or not Path(palette).is_file():
            return False, "No se pudo generar la paleta de color."
        use = subprocess.run(
            [ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
             "-i", input_path, "-i", palette,
             "-lavfi", f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
             output_path],
            stdout=subprocess.DEVNULL, stderr=err_target, timeout=600, **kw,
        )
        if use.returncode != 0 or not Path(output_path).is_file():
            return False, "No se pudo crear el GIF."
        return True, ""
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    finally:
        if logf is not None:
            try:
                logf.close()
            except OSError:
                pass
        try:
            Path(palette).unlink(missing_ok=True)
        except OSError:
            pass


def subprocess_kwargs() -> dict:
    return _subprocess_kwargs()
