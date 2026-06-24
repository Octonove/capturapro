"""Ventana principal y orquestacion de CapturaPro."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import APP_NAME, APP_VERSION
from . import audio_capture, ffmpeg_utils, screenshot, theme
from .border import RecordingBorder
from .config import AppConfig, VIDEO_QUALITY, QUALITY_ORDER, LOG_PATH, save_config
from .editor import EditorWindow
from .hotkeys import GlobalHotkeys, MOD_CONTROL, MOD_SHIFT
from .monitors import (
    Monitor, list_monitors, get_virtual_screen, primary_monitor, virtual_monitor,
)
from .recorder import Recorder, RecorderError
from .region_selector import RegionSelector

logger = logging.getLogger(__name__)

# Atajos globales: (modificadores, virtual-key, metodo de App, etiqueta)
HOTKEYS = [
    (MOD_CONTROL | MOD_SHIFT, 0x31, "shot_full", "Ctrl+Shift+1"),
    (MOD_CONTROL | MOD_SHIFT, 0x32, "shot_region", "Ctrl+Shift+2"),
    (MOD_CONTROL | MOD_SHIFT, 0x33, "shot_monitor", "Ctrl+Shift+3"),
    (MOD_CONTROL | MOD_SHIFT, 0x52, "_toggle_recording", "Ctrl+Shift+R"),
    (MOD_CONTROL | MOD_SHIFT, 0x50, "_toggle_pause", "Ctrl+Shift+P"),
]
HOTKEY_HELP = [
    ("Ctrl+Shift+1", "Captura de pantalla completa"),
    ("Ctrl+Shift+2", "Captura de area seleccionada"),
    ("Ctrl+Shift+3", "Captura: elegir pantalla"),
    ("Ctrl+Shift+R", "Iniciar / detener grabacion"),
    ("Ctrl+Shift+P", "Pausar / reanudar grabacion"),
]


def timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def run_async(root: tk.Misc, func, on_done) -> None:
    """Ejecuta `func` en un hilo y llama `on_done(value, error)` en el hilo de Tk."""
    box: dict = {}

    def worker():
        try:
            box["value"] = func()
        except Exception as exc:  # noqa: BLE001 - se reporta al usuario
            box["error"] = exc

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def poll():
        if t.is_alive():
            try:
                root.after(100, poll)
            except tk.TclError:
                pass  # la ventana se destruyo mientras corria el worker
            return
        on_done(box.get("value"), box.get("error"))

    try:
        root.after(100, poll)
    except tk.TclError:
        pass


def pick_monitor(root: tk.Tk, monitors: list[Monitor],
                 include_all: bool = True) -> Monitor | None:
    options = list(monitors)
    if include_all and len(monitors) > 1:
        options.append(virtual_monitor())
    if len(options) == 1:
        return options[0]
    monitors = options
    dlg = tk.Toplevel(root)
    dlg.title("Elegir pantalla")
    dlg.transient(root)
    dlg.resizable(False, False)
    chosen = {"value": None}
    var = tk.IntVar(value=monitors[0].index)
    ttk.Label(dlg, text="Selecciona la pantalla:", padding=10).pack(anchor="w")
    for m in monitors:
        ttk.Radiobutton(dlg, text=m.label, value=m.index, variable=var).pack(
            anchor="w", padx=16
        )
    btns = ttk.Frame(dlg, padding=10)
    btns.pack(fill="x")

    def ok():
        for m in monitors:
            if m.index == var.get():
                chosen["value"] = m
        dlg.destroy()

    ttk.Button(btns, text="Aceptar", command=ok).pack(side="right", padx=4)
    ttk.Button(btns, text="Cancelar", command=dlg.destroy).pack(side="right")
    dlg.grab_set()
    dlg.update_idletasks()
    x = root.winfo_rootx() + 60
    y = root.winfo_rooty() + 60
    dlg.geometry(f"+{x}+{y}")
    root.wait_window(dlg)
    return chosen["value"]


class App:
    def __init__(self, root: tk.Tk, config: AppConfig):
        self.root = root
        self.config = config
        self.recorder = Recorder()
        self._rec_control: tk.Toplevel | None = None
        self._stopping = False          # parada en curso (re-entrancia)
        self._pausing = False           # pausa/reanudacion en curso
        self._closing = False           # la app se esta cerrando
        self._timer_after = None        # id del after() del cronometro
        self._saved_geometry = None     # geometria previa al grabar
        self._rec_mode = None           # modo de la grabacion en curso
        self._rec_region = None         # region grabada (para el marcador)
        self.border = RecordingBorder(self.root)
        self.hotkeys = GlobalHotkeys(self.root)

        self.ffmpeg_path = ffmpeg_utils.find_ffmpeg(config.ffmpeg_path)
        self.encoders: set[str] = set()
        self.audio_devices: list[str] = []
        if self.ffmpeg_path:
            self.encoders = ffmpeg_utils.list_encoders(self.ffmpeg_path)

        self._build_ui()
        self._setup_hotkeys()
        # Lista de microfonos (soundcard) en segundo plano
        if audio_capture.AVAILABLE:
            run_async(self.root, audio_capture.list_microphones, self._on_audio_loaded)

    # ============================================================== UI build
    def _build_ui(self) -> None:
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        theme.apply(self.root)
        theme.header(self.root, APP_NAME, "Capturas e imagen + grabacion de video")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=12, pady=8)
        self._build_image_tab(nb)
        self._build_video_tab(nb)
        self._build_settings_tab(nb)

        self.status = theme.status_bar(self.root)

        # Ajusta la ventana a su contenido real para que nada quede cortado
        # (clave con el escalado DPI de pantallas 4K: las fuentes son mas grandes).
        self.root.update_idletasks()
        req_w = max(700, self.root.winfo_reqwidth() + 24)
        req_h = self.root.winfo_reqheight() + 12
        req_w = min(req_w, self.root.winfo_screenwidth() - 80)
        req_h = min(req_h, self.root.winfo_screenheight() - 80)
        self.root.geometry(f"{req_w}x{req_h}")
        self.root.minsize(min(req_w, 700), min(req_h, 600))

        if not self.ffmpeg_path:
            self._set_status("FFmpeg no encontrado: la grabacion de video esta desactivada.")
        else:
            self._set_status("Listo.")

    def _build_image_tab(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb, padding=16)
        nb.add(tab, text="  Captura de imagen  ")

        ttk.Label(tab, text="Tipo de captura", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=10)
        ttk.Button(row, text="Pantalla completa", width=18, style="Primary.TButton",
                   command=lambda: self.shot_full()).pack(side="left", padx=4)
        ttk.Button(row, text="Elegir pantalla", width=18, style="Primary.TButton",
                   command=lambda: self.shot_monitor()).pack(side="left", padx=4)
        ttk.Button(row, text="Area seleccionada", width=18, style="Primary.TButton",
                   command=lambda: self.shot_region()).pack(side="left", padx=4)

        opts = ttk.LabelFrame(tab, text="Opciones", padding=12)
        opts.pack(fill="x", pady=14)
        ttk.Label(opts, text="Retardo (segundos):").grid(row=0, column=0, sticky="w", pady=4)
        self.delay_var = tk.IntVar(value=self.config.screenshot_delay)
        ttk.Spinbox(opts, from_=0, to=10, width=5, textvariable=self.delay_var).grid(
            row=0, column=1, sticky="w", padx=8)

        ttk.Label(opts, text="Formato:").grid(row=1, column=0, sticky="w", pady=4)
        self.imgfmt_var = tk.StringVar(value=self.config.image_format)
        ttk.Combobox(opts, textvariable=self.imgfmt_var, values=["png", "jpg"],
                     width=6, state="readonly").grid(row=1, column=1, sticky="w", padx=8)

        ttk.Label(tab, text="Tras capturar se abre el editor (flechas, texto, formas, "
                            "resaltador) y puedes guardar o copiar al portapapeles.",
                  foreground="#666", wraplength=600, justify="left").pack(anchor="w", pady=8)

    def _build_video_tab(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb, padding=16)
        nb.add(tab, text="  Grabacion de video  ")

        area = ttk.LabelFrame(tab, text="Que grabar", padding=12)
        area.pack(fill="x")
        self.vmode_var = tk.StringVar(value="full")
        ttk.Radiobutton(area, text="Pantalla completa (monitor principal)",
                        value="full", variable=self.vmode_var).pack(anchor="w")
        ttk.Radiobutton(area, text="Elegir pantalla (o todo el escritorio)",
                        value="monitor", variable=self.vmode_var).pack(anchor="w")
        ttk.Radiobutton(area, text="Area seleccionada",
                        value="region", variable=self.vmode_var).pack(anchor="w")

        grid = ttk.LabelFrame(tab, text="Calidad y formato", padding=12)
        grid.pack(fill="x", pady=12)

        ttk.Label(grid, text="Calidad:").grid(row=0, column=0, sticky="w", pady=4)
        self.quality_var = tk.StringVar(value=self.config.video_quality)
        qbox = ttk.Combobox(grid, textvariable=self.quality_var, width=34, state="readonly",
                            values=[VIDEO_QUALITY[k]["label"] for k in QUALITY_ORDER])
        qbox.grid(row=0, column=1, sticky="w", padx=8, columnspan=3)
        qbox.set(VIDEO_QUALITY[self.config.video_quality]["label"])
        self._qbox = qbox

        ttk.Label(grid, text="FPS:").grid(row=1, column=0, sticky="w", pady=4)
        self.fps_var = tk.IntVar(value=self.config.fps)
        ttk.Combobox(grid, textvariable=self.fps_var, values=[15, 24, 30, 60],
                     width=6, state="readonly").grid(row=1, column=1, sticky="w", padx=8)

        ttk.Label(grid, text="Codificador:").grid(row=1, column=2, sticky="w", padx=(16, 0))
        enc_values = self._encoder_choices()
        self._enc_map = {v[0]: v[1] for v in enc_values}
        self.enc_box = ttk.Combobox(grid, width=24, state="readonly",
                                    values=[v[0] for v in enc_values])
        self.enc_box.grid(row=1, column=3, sticky="w", padx=8)
        # Selecciona el codificador guardado si coincide; si no, el primero
        # (= el recomendado por hardware cuando esta disponible).
        default_idx = 0
        for i, (_, key) in enumerate(enc_values):
            if key == self.config.encoder:
                default_idx = i
                break
        self.enc_box.current(default_idx)

        self.cursor_var = tk.BooleanVar(value=self.config.capture_cursor)
        ttk.Checkbutton(grid, text="Capturar puntero del raton",
                        variable=self.cursor_var).grid(row=2, column=0, columnspan=2,
                                                       sticky="w", pady=4)

        audio = ttk.LabelFrame(tab, text="Audio (opcional)", padding=12)
        audio.pack(fill="x")
        self._audio_modes = [
            ("Sin audio", "none"),
            ("Audio del sistema (lo que suena en el PC)", "system"),
            ("Microfono", "mic"),
            ("Sistema + microfono", "both"),
        ]
        ttk.Label(audio, text="Fuente:").grid(row=0, column=0, sticky="w")
        self.audio_mode_box = ttk.Combobox(audio, width=42, state="readonly",
                                           values=[m[0] for m in self._audio_modes])
        self.audio_mode_box.grid(row=0, column=1, sticky="w", padx=8)
        keys = [m[1] for m in self._audio_modes]
        cur = self.config.audio_mode if self.config.audio_mode in keys else "none"
        self.audio_mode_box.current(keys.index(cur))

        ttk.Label(audio, text="Microfono:").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.audio_box = ttk.Combobox(audio, width=42, state="readonly", values=[])
        self.audio_box.grid(row=1, column=1, sticky="w", padx=8, pady=(6, 0))

        if not audio_capture.AVAILABLE:
            self.audio_mode_box.set("Sin audio")
            self.audio_mode_box.state(["disabled"])
            ttk.Label(audio, text="(Captura de audio no disponible en este equipo.)",
                      foreground="#888", wraplength=560).grid(
                row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        actions = ttk.Frame(tab)
        actions.pack(fill="x", pady=16)
        self.rec_btn = ttk.Button(actions, text="Iniciar grabacion",
                                  style="Primary.TButton", command=self.start_recording)
        self.rec_btn.pack(side="left")
        self.gif_btn = ttk.Button(actions, text="Convertir video a GIF...",
                                  command=self.convert_video_to_gif)
        self.gif_btn.pack(side="left", padx=8)
        if not self.ffmpeg_path:
            self.rec_btn.state(["disabled"])
            self.gif_btn.state(["disabled"])

        ttk.Label(tab, text="Mientras grabas puedes pausar/reanudar y detener desde "
                            "el control flotante o con los atajos globales.",
                  foreground="#666", wraplength=600, justify="left").pack(anchor="w")

    def _build_settings_tab(self, nb: ttk.Notebook) -> None:
        tab = ttk.Frame(nb, padding=16)
        nb.add(tab, text="  Ajustes  ")

        f1 = ttk.Frame(tab)
        f1.pack(fill="x", pady=6)
        ttk.Label(f1, text="Carpeta de imagenes:", width=22).pack(side="left")
        self.imgdir_var = tk.StringVar(value=self.config.images_dir)
        ttk.Entry(f1, textvariable=self.imgdir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(f1, text="...", width=3,
                   command=lambda: self._choose_dir(self.imgdir_var)).pack(side="left")

        f2 = ttk.Frame(tab)
        f2.pack(fill="x", pady=6)
        ttk.Label(f2, text="Carpeta de videos:", width=22).pack(side="left")
        self.viddir_var = tk.StringVar(value=self.config.videos_dir)
        ttk.Entry(f2, textvariable=self.viddir_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(f2, text="...", width=3,
                   command=lambda: self._choose_dir(self.viddir_var)).pack(side="left")

        info = ttk.LabelFrame(tab, text="Estado", padding=12)
        info.pack(fill="x", pady=14)
        ff = self.ffmpeg_path or "NO ENCONTRADO"
        ttk.Label(info, text=f"FFmpeg: {ff}", wraplength=600, justify="left").pack(anchor="w")
        gpu = "Si" if ("h264_nvenc" in self.encoders or "h264_amf" in self.encoders
                       or "h264_qsv" in self.encoders) else "No"
        ttk.Label(info, text=f"Codificacion por GPU disponible: {gpu}").pack(anchor="w")
        ttk.Label(info, text=f"Registro: {LOG_PATH}", wraplength=600,
                  justify="left").pack(anchor="w")

        keys = ttk.LabelFrame(tab, text="Atajos de teclado globales", padding=12)
        keys.pack(fill="x", pady=(0, 8))
        self.hotkeys_var = tk.BooleanVar(value=self.config.hotkeys_enabled)
        ttk.Checkbutton(keys, text="Activar atajos globales (requiere reiniciar la app)",
                        variable=self.hotkeys_var).pack(anchor="w")
        for combo, desc in HOTKEY_HELP:
            ttk.Label(keys, text=f"   {combo}  ->  {desc}",
                      font=("Consolas", 9)).pack(anchor="w")

        ttk.Button(tab, text="Guardar ajustes", command=self._save_settings).pack(
            anchor="w", pady=8)

    # ============================================================ utilidades
    def _encoder_choices(self) -> list[tuple[str, str]]:
        # Hardware primero: es lo mejor para grabar a alta resolucion en tiempo
        # real sin caidas de fotogramas.
        choices: list[tuple[str, str]] = []
        if "h264_nvenc" in self.encoders:
            choices.append(("GPU NVIDIA - NVENC (recomendado, fluido)", "h264_nvenc"))
        if "h264_amf" in self.encoders:
            choices.append(("GPU AMD - AMF (fluido)", "h264_amf"))
        if "h264_qsv" in self.encoders:
            choices.append(("Intel Quick Sync - QSV (fluido)", "h264_qsv"))
        choices.append(("CPU - libx264 (maxima calidad)", "libx264"))
        if "hevc_nvenc" in self.encoders:
            choices.append(("GPU NVIDIA - HEVC (menor tamano)", "hevc_nvenc"))
        if "libx265" in self.encoders:
            choices.append(("CPU - libx265 / HEVC (menor tamano)", "libx265"))
        return choices

    def _quality_key(self) -> str:
        label = self._qbox.get()
        for k in QUALITY_ORDER:
            if VIDEO_QUALITY[k]["label"] == label:
                return k
        return "alta"

    def _audio_mode_key(self) -> str:
        label = self.audio_mode_box.get()
        for lbl, key in self._audio_modes:
            if lbl == label:
                return key
        return "none"

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _choose_dir(self, var: tk.StringVar) -> None:
        d = filedialog.askdirectory(initialdir=var.get() or str(Path.home()))
        if d:
            var.set(d)

    def _on_audio_loaded(self, devices, error) -> None:
        self.audio_devices = devices or []
        if not self.audio_devices:
            try:
                self.audio_box.set("(sin microfonos detectados)")
                self.audio_box.state(["disabled"])
            except tk.TclError:
                pass
            return
        try:
            self.audio_box.configure(values=self.audio_devices)
            target = (self.config.audio_device
                      if self.config.audio_device in self.audio_devices
                      else self.audio_devices[0])
            self.audio_box.set(target)
        except tk.TclError:
            pass

    def _sync_config(self) -> None:
        self.config.screenshot_delay = self.delay_var.get()
        self.config.image_format = self.imgfmt_var.get()
        self.config.video_quality = self._quality_key()
        self.config.fps = int(self.fps_var.get())
        self.config.encoder = self._enc_map.get(self.enc_box.get(), "libx264")
        self.config.capture_cursor = self.cursor_var.get()
        self.config.audio_mode = self._audio_mode_key()
        dev = self.audio_box.get()
        if dev and not dev.startswith("("):
            self.config.audio_device = dev
        self.config.images_dir = self.imgdir_var.get()
        self.config.videos_dir = self.viddir_var.get()
        if hasattr(self, "hotkeys_var"):
            self.config.hotkeys_enabled = self.hotkeys_var.get()

    def _save_settings(self) -> None:
        self._sync_config()
        self.config.ensure_dirs()
        save_config(self.config)
        self._set_status("Ajustes guardados.")

    # ============================================================== capturas
    def shot_full(self) -> None:
        mon = primary_monitor()
        self._do_screenshot(lambda: screenshot.capture_monitor(*mon.region))

    def shot_monitor(self) -> None:
        monitors = list_monitors()
        mon = pick_monitor(self.root, monitors)
        if mon is None:
            return
        self._do_screenshot(lambda: screenshot.capture_monitor(*mon.region))

    def shot_region(self) -> None:
        self.root.withdraw()
        self.root.update()
        time.sleep(0.15)
        try:
            region = RegionSelector(self.root).select()
        finally:
            self.root.deiconify()  # restaura la ventana pase lo que pase
        if region is None:
            self._set_status("Seleccion cancelada.")
            return
        self._do_screenshot(lambda: screenshot.capture_region(*region), withdraw=True)

    def _do_screenshot(self, grab_fn, withdraw: bool = True) -> None:
        delay = max(0, self.delay_var.get())
        if withdraw:
            self.root.withdraw()
            self.root.update()

        def capture():
            try:
                img = grab_fn()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Fallo la captura")
                if withdraw:
                    self.root.deiconify()
                messagebox.showerror(APP_NAME, f"No se pudo capturar:\n{exc}")
                return
            if withdraw:
                self.root.deiconify()
            EditorWindow(self.root, img, self.config,
                         suggested_name=f"captura_{timestamp()}")
            self._set_status("Captura realizada. Editala y guardala.")

        # Retardo + breve pausa para que la ventana desaparezca antes de capturar
        self.root.after(int((delay + 0.2) * 1000), capture)

    # ============================================================== grabacion
    def _resolve_region(self) -> tuple[int, int, int, int] | None:
        mode = self.vmode_var.get()
        if mode == "full":
            return primary_monitor().region
        if mode == "monitor":
            mon = pick_monitor(self.root, list_monitors())
            return mon.region if mon else None
        if mode == "region":
            self.root.withdraw()
            self.root.update()
            time.sleep(0.15)
            try:
                region = RegionSelector(self.root).select()
            finally:
                self.root.deiconify()
            return region
        return None

    def start_recording(self) -> None:
        if not self.ffmpeg_path:
            messagebox.showerror(APP_NAME, "FFmpeg no esta disponible.")
            return
        if self.recorder.is_recording:
            return
        region = self._resolve_region()
        if region is None:
            self._set_status("Grabacion cancelada.")
            return
        self._rec_mode = self.vmode_var.get()
        self._rec_region = region

        self._sync_config()
        encoder = ffmpeg_utils.resolve_encoder(self.config.encoder, self.encoders)
        container = self.config.video_container
        out_name = f"{APP_NAME}_{timestamp()}.{container}"
        out_path = str(Path(self.config.videos_dir) / out_name)
        Path(self.config.videos_dir).mkdir(parents=True, exist_ok=True)
        log_path = str(Path(self.config.videos_dir) / f".{out_name}.log")

        # Audio: captura best-effort EN PARALELO (no es input de FFmpeg), por lo
        # que un fallo de audio nunca tumba el video. Se mezcla al detener.
        mode = self.config.audio_mode
        want_system = mode in ("system", "both")
        mic_name = None
        if mode in ("mic", "both"):
            dev = self.audio_box.get()
            mic_name = dev if dev and not dev.startswith("(") else None

        def build_audio():
            if not audio_capture.AVAILABLE or not (want_system or mic_name):
                return None
            return audio_capture.AudioCapture(system=want_system, mic_name=mic_name,
                                              work_dir=self.config.videos_dir)

        def make_cmd_for(enc: str):
            def _mk(seg_path: str) -> list[str]:
                return ffmpeg_utils.build_record_command(
                    ffmpeg_path=self.ffmpeg_path,
                    region=region,
                    fps=self.config.fps,
                    encoder=enc,
                    quality_key=self.config.video_quality,
                    capture_cursor=self.config.capture_cursor,
                    output_path=seg_path,
                )
            return _mk

        self.rec_btn.state(["disabled"])
        self._set_status("Iniciando grabacion...")
        self._used_encoder = encoder

        def do_start():
            try:
                self.recorder.start(make_cmd_for(encoder), out_path,
                                    self.config.videos_dir, self.ffmpeg_path, log_path,
                                    audio=build_audio())
                self.recorder.check_started()
                return out_path
            except RecorderError:
                self.recorder.stop()  # limpia el intento fallido (estado/orphans)
                if encoder == "libx264":
                    raise
                # El codificador por GPU no arranco; reintenta con libx264 (CPU),
                # que funciona en cualquier equipo.
                logger.warning("Encoder %s fallo al arrancar; reintento con libx264.", encoder)
                self._used_encoder = "libx264"
                try:
                    self.recorder.start(make_cmd_for("libx264"), out_path,
                                        self.config.videos_dir, self.ffmpeg_path, log_path,
                                        audio=build_audio())
                    self.recorder.check_started()
                    return out_path
                except RecorderError:
                    self.recorder.stop()
                    raise

        def on_started(value, error):
            if self._closing:
                return
            if error:
                self.rec_btn.state(["!disabled"])
                self._set_status("Error al iniciar la grabacion.")
                messagebox.showerror(APP_NAME, f"No se pudo grabar:\n{error}")
                return
            self._show_rec_control()
            # Marca el area que se esta grabando (solo en modo "area"; en pantalla
            # completa el marco saldria dentro del propio video).
            if (self._rec_control is not None and self._rec_mode == "region"
                    and self._rec_region):
                self.border.show(*self._rec_region)
            if self._used_encoder != encoder:
                # Hubo fallback a CPU: refleja el cambio en el desplegable y avisa.
                for label, key in self._enc_map.items():
                    if key == self._used_encoder:
                        self.enc_box.set(label)
                        break
                self.config.encoder = self._used_encoder
                self._set_status("Grabando con CPU (libx264): el codificador por GPU "
                                 "no funciono en este equipo.")
            else:
                self._set_status("Grabando...")

        run_async(self.root, do_start, on_started)

    def _show_rec_control(self) -> None:
        # Construye el control ANTES de minimizar: si algo falla, la ventana
        # principal no queda minimizada e inaccesible.
        try:
            ctrl = tk.Toplevel(self.root)
            ctrl.title("Grabando")
            ctrl.attributes("-topmost", True)
            ctrl.resizable(False, False)
            ctrl.configure(bg="#1e1e1e")
            ctrl.protocol("WM_DELETE_WINDOW", self.stop_recording)

            frame = tk.Frame(ctrl, bg="#1e1e1e", padx=14, pady=10)
            frame.pack()
            self._dot = tk.Label(frame, text="●", fg="#ff3b30", bg="#1e1e1e",
                                 font=("Segoe UI", 14))
            self._dot.pack(side="left", padx=(0, 8))
            self._timer_lbl = tk.Label(frame, text="00:00", fg="white", bg="#1e1e1e",
                                       font=("Consolas", 16, "bold"))
            self._timer_lbl.pack(side="left", padx=(0, 12))
            self._pause_btn = tk.Button(frame, text="Pausar", bg="#3a3a3a", fg="white",
                                        relief="flat", padx=12, command=self.toggle_pause)
            self._pause_btn.pack(side="left", padx=(0, 6))
            self._stop_btn = tk.Button(frame, text="Detener", bg="#ff3b30", fg="white",
                                       relief="flat", padx=12, command=self.stop_recording)
            self._stop_btn.pack(side="left")

            # Posicion: arriba al centro del MONITOR PRINCIPAL (donde mira el
            # usuario), no del escritorio virtual completo (multimonitor).
            mon = primary_monitor()
            ctrl.update_idletasks()
            w = ctrl.winfo_reqwidth()  # ancho natural del contenido (estable)
            ctrl.geometry(f"+{mon.left + max(0, (mon.width - w) // 2)}+{mon.top + 24}")
            ctrl.lift()
            ctrl.attributes("-topmost", True)
            self._rec_control = ctrl
        except tk.TclError as exc:
            logger.error("No se pudo crear el control de grabacion: %s", exc)
            self._rec_control = None
            self._restore_main_window()
            self.rec_btn.state(["!disabled"])
            self._set_status("Error mostrando el control; grabacion detenida.")
            run_async(self.root, self.recorder.stop, lambda v, e: None)
            return

        # Aparta la ventana principal SIN minimizarla: iconify() haria que
        # Windows ocultara tambien las ventanas que posee (este control).
        self._hide_main_window()
        self._blink = True
        self._update_timer()

    def _hide_main_window(self) -> None:
        """Mueve la ventana principal fuera de pantalla (sigue 'mapeada', por lo
        que el control flotante que posee permanece visible)."""
        try:
            self._saved_geometry = self.root.geometry()
            vx, vy, vw, vh = get_virtual_screen()
            self.root.geometry(f"+{vx}+{vy + vh + 80}")
        except tk.TclError:
            pass

    def _restore_main_window(self) -> None:
        try:
            if self._saved_geometry:
                self.root.geometry(self._saved_geometry)
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass

    def _update_timer(self) -> None:
        self._timer_after = None
        if not self.recorder.is_recording or self._rec_control is None:
            return
        # Watchdog: si FFmpeg murio de forma inesperada (no es una pausa ni una
        # transicion), finaliza y guarda lo grabado en vez de quedar colgado.
        if (not self.recorder.is_paused and not self._pausing
                and not self.recorder.is_process_alive):
            self._set_status("La grabacion se detuvo; guardando lo grabado...")
            self.stop_recording()
            return
        try:
            secs = int(self.recorder.elapsed)
            self._timer_lbl.configure(text=f"{secs // 60:02d}:{secs % 60:02d}")
            if self.recorder.is_paused:
                self._dot.configure(fg="#ffb020")  # naranja fijo = en pausa
            else:
                self._blink = not self._blink
                self._dot.configure(fg="#ff3b30" if self._blink else "#5a1410")
        except tk.TclError:
            return
        self._timer_after = self.root.after(500, self._update_timer)

    def stop_recording(self) -> None:
        # No detener mientras hay una pausa/reanudacion en vuelo: evita que
        # stop() y pause()/resume() corran a la vez sobre el mismo FFmpeg.
        if self._stopping or self._pausing or not self.recorder.is_recording:
            return
        self._stopping = True
        # Cancela el cronometro y neutraliza el cierre de la ventana flotante,
        # para que un segundo intento (boton X / Alt+F4) no relance la parada.
        if self._timer_after is not None:
            try:
                self.root.after_cancel(self._timer_after)
            except tk.TclError:
                pass
            self._timer_after = None
        if self._rec_control is not None:
            self._rec_control.protocol("WM_DELETE_WINDOW", lambda: None)
            try:
                self._stop_btn.configure(state="disabled", text="Finalizando...")
            except tk.TclError:
                pass
        self._set_status("Finalizando video...")

        def do_stop():
            return self.recorder.stop()

        def on_stopped(path, error):
            self._stopping = False
            self.border.hide()
            if self._rec_control is not None:
                try:
                    self._rec_control.destroy()
                except tk.TclError:
                    pass
                self._rec_control = None
            if self._closing:
                return
            self._restore_main_window()
            self.rec_btn.state(["!disabled"])
            if error or not path:
                self._set_status("La grabacion fallo.")
                messagebox.showerror(APP_NAME,
                                     f"No se genero el video.\n{error or ''}")
                return
            self._set_status(f"Video guardado: {path}")
            if messagebox.askyesno(APP_NAME, f"Video guardado en:\n{path}\n\n"
                                            "Abrir la carpeta?"):
                self._open_folder(path)

        run_async(self.root, do_stop, on_stopped)

    def toggle_pause(self) -> None:
        if not self.recorder.is_active or self._stopping or self._pausing:
            return
        self._pausing = True
        resuming = self.recorder.is_paused
        try:
            self._pause_btn.configure(state="disabled")
            self._stop_btn.configure(state="disabled")  # evita detener a mitad
        except (tk.TclError, AttributeError):
            pass

        def work():
            if resuming:
                self.recorder.resume()
                self.recorder.check_started(0.8)
            else:
                self.recorder.pause()
            return resuming

        def done(value, error):
            self._pausing = False
            if self._closing:
                return
            try:
                self._pause_btn.configure(state="normal")
                self._stop_btn.configure(state="normal")
            except (tk.TclError, AttributeError):
                pass
            if error:
                self._set_status(f"Error al pausar/reanudar: {error}")
                self.stop_recording()  # evita dejar la sesion en estado roto
                return
            try:
                if self.recorder.is_paused:
                    self._pause_btn.configure(text="Reanudar")
                    self._set_status("Grabacion en pausa.")
                else:
                    self._pause_btn.configure(text="Pausar")
                    self._set_status("Grabando...")
            except (tk.TclError, AttributeError):
                pass

        run_async(self.root, work, done)

    # ------------------------------------------------------------- atajos
    def _setup_hotkeys(self) -> None:
        if not self.config.hotkeys_enabled:
            return
        for mod, vk, method, label in HOTKEYS:
            cb = getattr(self, method, None)
            if cb is not None:
                self.hotkeys.add(mod, vk, cb, label)
        self.hotkeys.start()

    def _toggle_recording(self) -> None:
        if self.recorder.is_active:
            self.stop_recording()
        else:
            self.start_recording()

    def _toggle_pause(self) -> None:
        if self.recorder.is_active:
            self.toggle_pause()

    # --------------------------------------------------------------- GIF
    def convert_video_to_gif(self) -> None:
        if not self.ffmpeg_path:
            messagebox.showerror(APP_NAME, "FFmpeg no esta disponible.")
            return
        src = filedialog.askopenfilename(
            parent=self.root, initialdir=self.config.videos_dir,
            title="Elige el video a convertir a GIF",
            filetypes=[("Video", "*.mp4 *.mkv *.mov *.avi *.webm"), ("Todos", "*.*")],
        )
        if not src:
            return
        fps = simpledialog.askinteger(APP_NAME, "FPS del GIF (recomendado 10-15):",
                                      initialvalue=self.config.gif_fps,
                                      minvalue=2, maxvalue=50, parent=self.root)
        if not fps:
            return
        width = simpledialog.askinteger(APP_NAME, "Anchura del GIF en pixeles:",
                                        initialvalue=self.config.gif_width,
                                        minvalue=120, maxvalue=3840, parent=self.root)
        if not width:
            return
        out = filedialog.asksaveasfilename(
            parent=self.root, initialdir=self.config.videos_dir,
            initialfile=Path(src).stem + ".gif", defaultextension=".gif",
            filetypes=[("GIF", "*.gif")],
        )
        if not out:
            return
        self.config.gif_fps = fps
        self.config.gif_width = width
        self.gif_btn.state(["disabled"])
        self._set_status("Convirtiendo a GIF... (puede tardar)")
        log = str(Path(self.config.videos_dir) / ".gif.log")

        def work():
            return ffmpeg_utils.convert_to_gif(self.ffmpeg_path, src, out, fps, width, log)

        def done(result, error):
            try:
                self.gif_btn.state(["!disabled"])
            except tk.TclError:
                pass
            ok, msg = result if result else (False, str(error))
            if not ok:
                self._set_status("La conversion a GIF fallo.")
                messagebox.showerror(APP_NAME, f"No se pudo crear el GIF.\n{msg}")
                return
            self._set_status(f"GIF guardado: {out}")
            if messagebox.askyesno(APP_NAME, f"GIF guardado en:\n{out}\n\nAbrir la carpeta?"):
                self._open_folder(out)

        run_async(self.root, work, done)

    def _open_folder(self, file_path: str) -> None:
        try:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(file_path)])
        except OSError:
            try:
                os.startfile(str(Path(file_path).parent))  # type: ignore[attr-defined]
            except OSError:
                pass

    # ================================================================ cierre
    def on_close(self) -> None:
        if self.recorder.is_recording:
            if not messagebox.askyesno(APP_NAME,
                                       "Hay una grabacion en curso. Detener y salir?"):
                return
        self._closing = True
        self.border.hide()
        self.hotkeys.stop()
        if self._timer_after is not None:
            try:
                self.root.after_cancel(self._timer_after)
            except tk.TclError:
                pass
            self._timer_after = None
        if self.recorder.is_recording:
            self.recorder.stop()  # idempotente: seguro aunque haya un stop en curso
        if self._rec_control is not None:
            try:
                self._rec_control.destroy()
            except tk.TclError:
                pass
            self._rec_control = None
        self._sync_config()
        save_config(self.config)
        self.root.destroy()
