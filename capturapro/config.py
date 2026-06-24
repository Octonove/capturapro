"""Configuracion persistente y presets de calidad de CapturaPro."""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from dataclasses import dataclass, asdict, field
from pathlib import Path

from . import APP_NAME

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rutas de datos de la aplicacion
# ---------------------------------------------------------------------------
def get_data_dir() -> Path:
    """Carpeta de datos del usuario (config + logs).

    NUNCA lanza: se ejecuta en tiempo de import, y si %APPDATA% no fuera
    escribible (perfil temporal, permisos, antivirus) el .exe windowed moriria
    sin mensaje. Cae a HOME y, en ultimo extremo, a la carpeta temporal.
    """
    for base in (os.environ.get("APPDATA"), str(Path.home())):
        if not base:
            continue
        d = Path(base) / APP_NAME
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except OSError:
            continue
    d = Path(tempfile.gettempdir()) / APP_NAME
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def default_pictures_dir() -> Path:
    return Path.home() / "Pictures" / APP_NAME


def default_videos_dir() -> Path:
    return Path.home() / "Videos" / APP_NAME


CONFIG_PATH = get_data_dir() / "config.json"
LOG_PATH = get_data_dir() / "capturapro.log"


# ---------------------------------------------------------------------------
# Presets de calidad de video
#   - x264_crf: factor de calidad constante (mas bajo = mas calidad).
#     16 es practicamente sin perdida visual; 23 estandar; 30 ligero.
#   - nvenc_cq: equivalente para el encoder por GPU NVIDIA.
# ---------------------------------------------------------------------------
# Nota: los presets de libx264 son rapidos a proposito ("veryfast"/"superfast")
# para que la codificacion siga el ritmo de la captura en tiempo real (sobre todo
# a 4K) y NO se pierdan fotogramas. La calidad la fija el CRF (mas bajo = mejor);
# un preset mas lento solo reduciria el tamano del archivo, no mejora la calidad
# visual a igual CRF, y arriesga caidas de frames en pantallas grandes.
VIDEO_QUALITY = {
    "alta": {
        "label": "Alta - casi sin perdida (archivo grande)",
        "x264_crf": 16,
        "x264_preset": "veryfast",
        "nvenc_cq": 19,
        "nvenc_preset": "p5",
    },
    "media": {
        "label": "Media - equilibrado",
        "x264_crf": 23,
        "x264_preset": "veryfast",
        "nvenc_cq": 25,
        "nvenc_preset": "p4",
    },
    "baja": {
        "label": "Baja - archivo pequeno",
        "x264_crf": 30,
        "x264_preset": "superfast",
        "nvenc_cq": 32,
        "nvenc_preset": "p4",
    },
}
QUALITY_ORDER = ["alta", "media", "baja"]


@dataclass
class AppConfig:
    """Preferencias del usuario, serializables a JSON."""

    images_dir: str = field(default_factory=lambda: str(default_pictures_dir()))
    videos_dir: str = field(default_factory=lambda: str(default_videos_dir()))
    image_format: str = "png"          # png | jpg
    jpg_quality: int = 95
    screenshot_delay: int = 0          # segundos antes de capturar

    # Video
    video_quality: str = "alta"        # alta | media | baja
    fps: int = 30
    encoder: str = "auto"              # auto | libx264 | h264_nvenc | h264_amf | h264_qsv
    capture_cursor: bool = True
    audio_enabled: bool = False        # (obsoleto, se mantiene por compatibilidad)
    audio_mode: str = "none"           # none | system | mic | both
    audio_device: str = ""             # nombre del microfono (soundcard)
    video_container: str = "mp4"       # mp4 | mkv

    # Avanzado
    ffmpeg_path: str = ""              # override manual (vacio = autodeteccion)
    hotkeys_enabled: bool = True       # atajos de teclado globales

    # GIF
    gif_fps: int = 15
    gif_width: int = 720

    def ensure_dirs(self) -> None:
        for p in (self.images_dir, self.videos_dir):
            try:
                Path(p).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                logger.warning("No se pudo crear la carpeta %s: %s", p, exc)


def load_config() -> AppConfig:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("config.json no es un objeto JSON")
            known = {f for f in AppConfig().__dict__}
            clean = {k: v for k, v in data.items() if k in known}
            cfg = AppConfig(**clean)
            cfg.ensure_dirs()
            return cfg
        except (json.JSONDecodeError, TypeError, ValueError, AttributeError) as exc:
            logger.warning("Config corrupta, usando valores por defecto: %s", exc)
    cfg = AppConfig()
    cfg.ensure_dirs()
    return cfg


def save_config(cfg: AppConfig) -> None:
    try:
        CONFIG_PATH.write_text(
            json.dumps(asdict(cfg), indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        logger.error("No se pudo guardar la config: %s", exc)


def setup_logging() -> None:
    """Configura logging a archivo (la app es 'windowed': no hay consola)."""
    handlers: list[logging.Handler] = []
    try:
        handlers.append(logging.FileHandler(LOG_PATH, encoding="utf-8"))
    except OSError:
        try:  # fallback a la carpeta temporal si LOG_PATH no es escribible
            handlers.append(logging.FileHandler(
                Path(tempfile.gettempdir()) / "capturapro.log", encoding="utf-8"))
        except OSError:
            pass
    # Si hay consola (modo desarrollo) tambien escribimos ahi.
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    if not handlers:  # nunca dejar basicConfig sin handlers
        handlers.append(logging.NullHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
