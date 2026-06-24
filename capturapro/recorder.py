"""Controlador del proceso FFmpeg para grabacion de video.

Soporta pausa/reanudar grabando en segmentos: cada pausa finaliza el segmento
actual y cada reanudacion abre uno nuevo. Al detener, los segmentos se unen sin
recodificar (concat -c copy), produciendo un unico video final sin perdida.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from .ffmpeg_utils import build_concat_command, build_mux_command, subprocess_kwargs

logger = logging.getLogger(__name__)


class RecorderError(Exception):
    pass


class Recorder:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._log_file = None
        self._make_cmd = None            # callable(seg_path) -> list[str]
        self._final_output: str = ""
        self._work_dir: str = ""
        self._ffmpeg: str = ""
        self._log_path: str = ""
        self._segments: list[str] = []   # segmentos finalizados (validos)
        self._cur_seg: str = ""
        self._seg_index: int = 0
        self._accumulated: float = 0.0   # segundos grabados acumulados
        self._seg_start: float = 0.0
        self._paused: bool = False
        self._active: bool = False
        self._audio = None               # AudioCapture opcional
        self._lock = threading.Lock()

    # --------------------------------------------------------------- estado
    @property
    def is_active(self) -> bool:
        """Hay una sesion de grabacion en curso (incluye estado en pausa)."""
        return self._active

    @property
    def is_recording(self) -> bool:
        return self._active

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_process_alive(self) -> bool:
        """True si el proceso FFmpeg del segmento actual sigue vivo (watchdog)."""
        p = self._proc
        return p is not None and p.poll() is None

    @property
    def output_path(self) -> str:
        return self._final_output

    @property
    def elapsed(self) -> float:
        with self._lock:
            t = self._accumulated
            if self._active and not self._paused and self._seg_start:
                t += time.monotonic() - self._seg_start
            return t

    # --------------------------------------------------------------- helpers
    def _seg_path(self, i: int) -> str:
        ext = Path(self._final_output).suffix or ".mp4"
        return str(Path(self._work_dir) / f".capturapro_seg_{i}{ext}")

    def _start_segment(self) -> None:
        seg = self._seg_path(self._seg_index)
        cmd = self._make_cmd(seg)
        logger.info("FFmpeg seg %d: %s", self._seg_index, " ".join(cmd))
        try:
            log_file = open(self._log_path, "wb")
        except OSError as exc:
            raise RecorderError(
                f"No se puede escribir en la carpeta de videos: {exc}") from exc
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=log_file, **subprocess_kwargs(),
            )
        except OSError as exc:
            log_file.close()
            raise RecorderError(f"No se pudo iniciar FFmpeg: {exc}") from exc
        with self._lock:
            self._proc = proc
            self._log_file = log_file
            self._cur_seg = seg
            self._seg_start = time.monotonic()

    def _finalize_current(self) -> None:
        """Detiene el ffmpeg del segmento actual y lo registra si es valido."""
        with self._lock:
            proc = self._proc
            log_file = self._log_file
            seg = self._cur_seg
            seg_start = self._seg_start
            self._proc = None
            self._log_file = None
            self._cur_seg = ""
            self._seg_start = 0.0
            if seg_start:
                self._accumulated += max(0.0, time.monotonic() - seg_start)
        if proc is None:
            return
        if proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.write(b"q")
                    proc.stdin.flush()
                    proc.stdin.close()
            except (OSError, ValueError):
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("FFmpeg no respondio a 'q', terminando.")
                try:
                    proc.terminate()
                    proc.wait(timeout=4)
                except (subprocess.TimeoutExpired, OSError):
                    try:
                        proc.kill()
                    except OSError:
                        pass
        if log_file is not None:
            try:
                log_file.close()
            except OSError:
                pass
        if seg and Path(seg).is_file() and Path(seg).stat().st_size > 0:
            with self._lock:
                self._segments.append(seg)

    # ----------------------------------------------------------- ciclo de vida
    def start(self, make_cmd, final_output: str, work_dir: str,
              ffmpeg_path: str, log_path: str, audio=None) -> None:
        if self._active:
            raise RecorderError("Ya hay una grabacion en curso.")
        self._make_cmd = make_cmd
        self._final_output = final_output
        self._work_dir = work_dir
        self._ffmpeg = ffmpeg_path
        self._log_path = log_path
        self._segments = []
        self._seg_index = 0
        self._accumulated = 0.0
        self._paused = False
        self._active = True
        self._audio = audio
        try:
            Path(work_dir).mkdir(parents=True, exist_ok=True)
            self._start_segment()
        except (OSError, RecorderError) as exc:
            # Rollback: deja el recorder inactivo para no bloquear futuros intentos.
            self._active = False
            self._audio = None
            if isinstance(exc, RecorderError):
                raise
            raise RecorderError(f"No se pudo iniciar la grabacion: {exc}") from exc
        if audio is not None:
            try:
                audio.start()  # captura de audio en paralelo (best-effort)
            except Exception as exc:  # noqa: BLE001
                logger.warning("No se pudo iniciar la captura de audio: %s", exc)

    def check_started(self, settle: float = 1.2) -> None:
        if self._proc is None:
            raise RecorderError("Proceso no iniciado.")
        time.sleep(settle)
        code = self._proc.poll()
        if code is not None:
            raise RecorderError(self._tail_log() or f"FFmpeg termino con codigo {code}.")

    def pause(self) -> None:
        if not self._active or self._paused:
            return
        self._finalize_current()
        if self._audio is not None:
            self._audio.pause()
        self._paused = True

    def resume(self) -> None:
        if not self._active or not self._paused:
            return
        self._seg_index += 1
        self._paused = False
        if self._audio is not None:
            self._audio.resume()
        self._start_segment()

    def stop(self) -> str | None:
        """Detiene la sesion: une los segmentos de video y mezcla el audio."""
        with self._lock:
            if not self._active:
                return None
            self._active = False
            was_paused = self._paused
        if not was_paused:
            self._finalize_current()
        self._paused = False

        # Detener la captura de audio (best-effort: no debe afectar al video)
        audio = self._audio
        self._audio = None
        audio_wavs: list[str] = []
        if audio is not None:
            try:
                audio_wavs = audio.stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fallo al detener el audio: %s", exc)

        with self._lock:
            segs = list(self._segments)
        final = self._final_output
        if not segs:
            logger.error("Sin segmentos validos. Log: %s", self._tail_log())
            self._cleanup_orphan_segments()
            if audio is not None:
                audio.cleanup()
            return None

        # 1) Producir el video (sin audio) en un temporal
        ext = Path(final).suffix or ".mp4"
        video_tmp = str(Path(self._work_dir) / f".capturapro_video{ext}")
        try:
            Path(video_tmp).unlink(missing_ok=True)
            if len(segs) == 1:
                os.replace(segs[0], video_tmp)
            else:
                self._concat(segs, video_tmp)
                for s in segs:
                    try:
                        Path(s).unlink(missing_ok=True)
                    except OSError:
                        pass
        except (OSError, subprocess.SubprocessError) as exc:
            # Conservamos los segmentos (contienen la grabacion) para no perder datos.
            logger.error("Fallo al unir el video: %s. Segmentos conservados en %s",
                         exc, self._work_dir)
            if audio is not None:
                audio.cleanup()
            return None

        # 2) Mezclar con el audio; si falla, entregar el video sin audio (nunca
        #    se pierde el video por un problema de audio).
        try:
            Path(final).unlink(missing_ok=True)
            if audio_wavs:
                self._mux(video_tmp, audio_wavs, final)
                Path(video_tmp).unlink(missing_ok=True)
            else:
                os.replace(video_tmp, final)
        except (OSError, subprocess.SubprocessError) as exc:
            logger.warning("Fallo al mezclar el audio (%s); se guarda el video sin sonido.", exc)
            try:
                if Path(video_tmp).is_file():
                    Path(final).unlink(missing_ok=True)
                    os.replace(video_tmp, final)
            except OSError:
                pass
        finally:
            if audio is not None:
                audio.cleanup()

        if Path(final).is_file() and Path(final).stat().st_size > 0:
            return final
        logger.error("El video final no se genero. Log: %s", self._tail_log())
        return None

    def _concat(self, segs: list[str], output: str) -> None:
        list_file = str(Path(self._work_dir) / ".capturapro_concat.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for s in segs:
                p = str(Path(s).resolve()).replace("'", "'\\''")
                f.write(f"file '{p}'\n")
        cmd = build_concat_command(self._ffmpeg, list_file, output)
        Path(output).unlink(missing_ok=True)
        log_file = open(self._log_path, "ab")
        try:
            subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=log_file, timeout=180, **subprocess_kwargs())
        finally:
            try:
                log_file.close()
            except OSError:
                pass
            try:
                Path(list_file).unlink(missing_ok=True)
            except OSError:
                pass
        if not (Path(output).is_file() and Path(output).stat().st_size > 0):
            raise subprocess.SubprocessError("La union de segmentos no genero salida")

    def _mux(self, video: str, wavs: list[str], output: str) -> None:
        cmd = build_mux_command(self._ffmpeg, video, wavs, output)
        log_file = open(self._log_path, "ab")
        try:
            subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=log_file, timeout=300, **subprocess_kwargs())
        finally:
            try:
                log_file.close()
            except OSError:
                pass
        if not (Path(output).is_file() and Path(output).stat().st_size > 0):
            raise subprocess.SubprocessError("El mux de audio no genero salida")

    def _cleanup_orphan_segments(self) -> None:
        """Borra segmentos temporales huerfanos (p. ej. de un encoder que fallo)."""
        try:
            for f in Path(self._work_dir).glob(".capturapro_seg_*"):
                try:
                    f.unlink(missing_ok=True)
                except OSError:
                    pass
        except OSError:
            pass

    def _tail_log(self, lines: int = 8) -> str:
        try:
            text = Path(self._log_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        tail = [ln for ln in text.splitlines() if ln.strip()][-lines:]
        return "\n".join(tail)
