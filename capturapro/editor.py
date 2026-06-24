"""Editor de anotaciones para capturas de imagen.

Las anotaciones se guardan en coordenadas de la imagen original; en pantalla
se dibujan escaladas, pero la exportacion se rasteriza con Pillow a resolucion
nativa (sin perdida de calidad).
"""

from __future__ import annotations

import logging
import math
import os
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk

from . import APP_NAME
from .clipboard import copy_image
from .config import AppConfig

logger = logging.getLogger(__name__)

TOOLS = [
    ("arrow", "Flecha"),
    ("rect", "Rectangulo"),
    ("ellipse", "Elipse"),
    ("line", "Linea"),
    ("pen", "Lapiz"),
    ("highlight", "Resaltador"),
    ("text", "Texto"),
]


@dataclass
class Annotation:
    kind: str
    color: str
    width: int
    points: list[tuple[float, float]] = field(default_factory=list)
    text: str = ""
    font_size: int = 24


def _find_font_file() -> str | None:
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in ("segoeui.ttf", "arial.ttf", "calibri.ttf", "tahoma.ttf", "verdana.ttf"):
        p = fonts_dir / name
        if p.is_file():
            return str(p)
    return None


_FONT_FILE = _find_font_file()


def _load_font(size: int) -> ImageFont.ImageFont:
    try:
        if _FONT_FILE:
            return ImageFont.truetype(_FONT_FILE, size)
    except OSError:
        pass
    try:
        # Pillow >= 10.1 respeta el tamano en el fallback (el proyecto fija >=11).
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _arrow_head(p0, p1, size):
    """Devuelve los tres vertices de la punta de flecha en p1."""
    x0, y0 = p0
    x1, y1 = p1
    ang = math.atan2(y1 - y0, x1 - x0)
    a = ang + math.radians(150)
    b = ang - math.radians(150)
    return [
        (x1, y1),
        (x1 + size * math.cos(a), y1 + size * math.sin(a)),
        (x1 + size * math.cos(b), y1 + size * math.sin(b)),
    ]


def render_annotations(base: Image.Image, anns: list[Annotation]) -> Image.Image:
    """Rasteriza las anotaciones sobre una copia de la imagen original."""
    img = base.convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for a in anns:
        w = max(1, a.width)
        col = a.color
        pts = a.points
        if a.kind == "arrow" and len(pts) >= 2:
            draw.line([pts[0], pts[1]], fill=col, width=w)
            head = _arrow_head(pts[0], pts[1], max(12, w * 4))
            draw.polygon(head, fill=col)
        elif a.kind == "line" and len(pts) >= 2:
            draw.line([pts[0], pts[1]], fill=col, width=w)
        elif a.kind == "rect" and len(pts) >= 2:
            draw.rectangle(_bbox(pts[0], pts[1]), outline=col, width=w)
        elif a.kind == "ellipse" and len(pts) >= 2:
            draw.ellipse(_bbox(pts[0], pts[1]), outline=col, width=w)
        elif a.kind == "pen" and len(pts) >= 2:
            draw.line(pts, fill=col, width=w, joint="curve")
        elif a.kind == "highlight" and len(pts) >= 2:
            r, g, b = _hex_rgb(col)
            draw.line(pts, fill=(r, g, b, 90), width=max(w, 14), joint="curve")
        elif a.kind == "text" and pts and a.text:
            font = _load_font(a.font_size)
            draw.text(pts[0], a.text, fill=col, font=font)

    return Image.alpha_composite(img, overlay).convert("RGB")


def _bbox(p0, p1):
    return [min(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[0], p1[0]), max(p0[1], p1[1])]


def _hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 255, 0, 0


class EditorWindow:
    def __init__(self, root: tk.Tk, image: Image.Image, config: AppConfig,
                 suggested_name: str = "captura"):
        self.root = root
        self.image = image.convert("RGB")
        self.config = config
        self.suggested_name = suggested_name

        self.annotations: list[Annotation] = []
        self.redo_stack: list[Annotation] = []
        self.tool = tk.StringVar(value="arrow")
        self.color = "#ff3b30"
        self.line_width = tk.IntVar(value=4)
        self.font_size = tk.IntVar(value=28)

        self._start = None
        self._preview_id = None
        self._cur_points: list[tuple[float, float]] = []
        self._text_entry = None

        self._build_window()

    # ------------------------------------------------------------------ UI
    def _build_window(self) -> None:
        self.win = tk.Toplevel(self.root)
        self.win.title(f"Editor - {APP_NAME}")
        self.win.configure(bg="#2b2b2b")

        # Escala de visualizacion para que quepa en pantalla
        sw = self.win.winfo_screenwidth() - 120
        sh = self.win.winfo_screenheight() - 220
        iw, ih = self.image.size
        self.scale = min(1.0, sw / iw, sh / ih)
        self.disp_w = max(1, int(iw * self.scale))
        self.disp_h = max(1, int(ih * self.scale))

        self._build_toolbar()

        self.canvas = tk.Canvas(
            self.win, width=self.disp_w, height=self.disp_h,
            highlightthickness=0, bg="#1e1e1e", cursor="crosshair",
        )
        self.canvas.pack(padx=10, pady=10)

        self.status = ttk.Label(self.win, text="Elige una herramienta y dibuja sobre la imagen.")
        self.status.pack(fill="x", padx=10, pady=(0, 8))

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.win.bind("<Control-z>", lambda e: self._kb(self.undo))
        self.win.bind("<Control-y>", lambda e: self._kb(self.redo))
        self.win.bind("<Control-s>", lambda e: self._kb(self.save))
        self.win.bind("<Control-c>", lambda e: self._kb(self.copy))

        self._redraw()

        self.win.update_idletasks()
        self.win.minsize(self.disp_w + 40, self.disp_h + 140)

    def _build_toolbar(self) -> None:
        bar = ttk.Frame(self.win, padding=6)
        bar.pack(fill="x")

        tools = ttk.Frame(bar)
        tools.pack(side="left")
        for key, label in TOOLS:
            ttk.Radiobutton(tools, text=label, value=key,
                            variable=self.tool).pack(side="left", padx=1)

        right = ttk.Frame(bar)
        right.pack(side="right")

        self.color_btn = tk.Button(right, text="Color", width=8, bg=self.color,
                                   fg="white", relief="flat", command=self._pick_color)
        self.color_btn.pack(side="left", padx=4)

        ttk.Label(right, text="Grosor").pack(side="left")
        ttk.Spinbox(right, from_=1, to=40, width=3,
                    textvariable=self.line_width).pack(side="left", padx=(2, 8))
        ttk.Label(right, text="Texto").pack(side="left")
        ttk.Spinbox(right, from_=8, to=120, width=3,
                    textvariable=self.font_size).pack(side="left", padx=(2, 8))

        ttk.Button(right, text="Deshacer", command=self.undo).pack(side="left", padx=2)
        ttk.Button(right, text="Rehacer", command=self.redo).pack(side="left", padx=2)
        ttk.Separator(right, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(right, text="Copiar", command=self.copy).pack(side="left", padx=2)
        ttk.Button(right, text="Guardar", command=self.save).pack(side="left", padx=2)

    def _pick_color(self) -> None:
        rgb, hexv = colorchooser.askcolor(color=self.color, parent=self.win)
        if hexv:
            self.color = hexv
            self.color_btn.configure(bg=hexv)

    # ----------------------------------------------------------- coordenadas
    def _to_image(self, x: float, y: float) -> tuple[float, float]:
        return (x / self.scale, y / self.scale)

    def _to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return (x * self.scale, y * self.scale)

    # ---------------------------------------------------------------- dibujo
    def _build_display(self) -> None:
        # Composita las anotaciones confirmadas con Pillow (mismo motor que la
        # exportacion) y las muestra escaladas: lo que ves es exactamente lo que
        # se guarda (WYSIWYG: sin discrepancias de fuente, posicion ni alfa).
        flat = render_annotations(self.image, self.annotations) if self.annotations \
            else self.image
        if self.scale != 1.0:
            flat = flat.resize((self.disp_w, self.disp_h), Image.LANCZOS)
        self._bg_photo = ImageTk.PhotoImage(flat)

    def _redraw(self) -> None:
        self._build_display()
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._bg_photo)

    def _kb(self, fn) -> None:
        # Ignora los atajos globales mientras se edita texto en el Entry,
        # para no interferir con Ctrl+C/Z nativos del campo de texto.
        if self._text_entry is not None:
            return
        fn()

    # -------------------------------------------------------------- eventos
    def _on_press(self, event: tk.Event) -> None:
        if self._text_entry is not None:
            self._commit_text()
        tool = self.tool.get()
        self._start = (event.x, event.y)
        if tool == "text":
            self._begin_text(event.x, event.y)
            self._start = None
            return
        self._cur_points = [(event.x, event.y)]

    def _on_drag(self, event: tk.Event) -> None:
        if self._start is None and self.tool.get() != "pen":
            return
        tool = self.tool.get()
        if self._preview_id is not None:
            self.canvas.delete(self._preview_id)
            self._preview_id = None
        w = max(1, int(self.line_width.get() * self.scale))
        if tool in ("pen", "highlight"):
            self._cur_points.append((event.x, event.y))
            flat = [c for p in self._cur_points for c in p]
            if len(flat) >= 4:
                if tool == "highlight":
                    self._preview_id = self.canvas.create_line(
                        *flat, fill=self.color,
                        width=max(w, int(14 * self.scale)),
                        stipple="gray50", capstyle="round")
                else:
                    self._preview_id = self.canvas.create_line(
                        *flat, fill=self.color, width=w,
                        smooth=True, capstyle="round")
            return
        x0, y0 = self._start
        x1, y1 = event.x, event.y
        if tool == "arrow":
            self._preview_id = self.canvas.create_line(
                x0, y0, x1, y1, fill=self.color, width=w,
                arrow=tk.LAST, arrowshape=(16, 20, 6))
        elif tool == "line":
            self._preview_id = self.canvas.create_line(
                x0, y0, x1, y1, fill=self.color, width=w)
        elif tool == "rect":
            self._preview_id = self.canvas.create_rectangle(
                x0, y0, x1, y1, outline=self.color, width=w)
        elif tool == "ellipse":
            self._preview_id = self.canvas.create_oval(
                x0, y0, x1, y1, outline=self.color, width=w)

    def _on_release(self, event: tk.Event) -> None:
        tool = self.tool.get()
        if tool == "text":
            return
        if self._preview_id is not None:
            self.canvas.delete(self._preview_id)
            self._preview_id = None
        if tool in ("pen", "highlight"):
            if len(self._cur_points) < 2:
                self._cur_points = []
                return
            pts = [self._to_image(x, y) for (x, y) in self._cur_points]
            self._commit(Annotation(tool, self.color, self.line_width.get(), pts))
            self._cur_points = []
            return
        if self._start is None:
            return
        x0, y0 = self._start
        x1, y1 = event.x, event.y
        if abs(x1 - x0) < 3 and abs(y1 - y0) < 3 and tool != "text":
            self._start = None
            return
        pts = [self._to_image(x0, y0), self._to_image(x1, y1)]
        self._commit(Annotation(tool, self.color, self.line_width.get(), pts))
        self._start = None

    # ----------------------------------------------------------------- texto
    def _begin_text(self, x: int, y: int) -> None:
        # Fuente en pixeles (tamano negativo en Tk) para que coincida con PIL,
        # y campo casi sin borde para minimizar el desfase de posicion.
        px = max(8, int(self.font_size.get() * self.scale))
        entry = tk.Entry(self.canvas, font=("Segoe UI", -px),
                         bd=0, relief="flat", highlightthickness=1,
                         highlightbackground=self.color, highlightcolor=self.color,
                         background="#ffffff", foreground=self.color,
                         insertbackground=self.color)
        self._text_entry = entry
        self._text_pos = (x, y)
        self._text_window = self.canvas.create_window(x, y, window=entry, anchor="nw")
        entry.focus_set()
        entry.bind("<Return>", lambda e: self._commit_text())
        entry.bind("<Escape>", lambda e: self._cancel_text())
        # Confirma el texto al perder el foco (clic en barra de herramientas,
        # dialogos, etc.), evitando perdida silenciosa del texto.
        entry.bind("<FocusOut>", lambda e: self._commit_text())
        self.status.configure(text="Escribe el texto y pulsa Enter (Esc para cancelar).")

    def _commit_text(self) -> None:
        if self._text_entry is None:
            return
        text = self._text_entry.get().strip()
        x, y = self._text_pos
        self._destroy_text_entry()
        if text:
            pts = [self._to_image(x, y)]
            self._commit(Annotation("text", self.color, self.line_width.get(),
                                    pts, text=text, font_size=self.font_size.get()))

    def _cancel_text(self) -> None:
        self._destroy_text_entry()

    def _destroy_text_entry(self) -> None:
        if self._text_entry is not None:
            self.canvas.delete(self._text_window)
            self._text_entry.destroy()
            self._text_entry = None
            self._text_window = None

    # ----------------------------------------------------------- operaciones
    def _commit(self, ann: Annotation) -> None:
        self.annotations.append(ann)
        self.redo_stack.clear()
        self._redraw()

    def undo(self) -> None:
        if self.annotations:
            self.redo_stack.append(self.annotations.pop())
            self._redraw()

    def redo(self) -> None:
        if self.redo_stack:
            self.annotations.append(self.redo_stack.pop())
            self._redraw()

    def _flatten(self) -> Image.Image:
        return render_annotations(self.image, self.annotations)

    def copy(self) -> None:
        if self._text_entry is not None:
            self._commit_text()
        if copy_image(self._flatten()):
            self.status.configure(text="Imagen copiada al portapapeles.")
        else:
            self.status.configure(text="No se pudo copiar al portapapeles.")

    def save(self) -> None:
        if self._text_entry is not None:
            self._commit_text()
        fmt = self.config.image_format.lower()
        ext = ".png" if fmt == "png" else ".jpg"
        path = filedialog.asksaveasfilename(
            parent=self.win,
            initialdir=self.config.images_dir,
            initialfile=f"{self.suggested_name}{ext}",
            defaultextension=ext,
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg;*.jpeg")],
        )
        if not path:
            return
        out = self._flatten()
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            if path.lower().endswith((".jpg", ".jpeg")):
                out.save(path, "JPEG", quality=self.config.jpg_quality, subsampling=0)
            else:
                out.save(path, "PNG")
            self.status.configure(text=f"Guardado: {path}")
        except (OSError, ValueError) as exc:
            messagebox.showerror(APP_NAME, f"No se pudo guardar:\n{exc}", parent=self.win)
