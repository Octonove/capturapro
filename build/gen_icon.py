"""Genera build/icon.ico para CapturaPro (marco de captura + punto de grabacion)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def rounded(draw, box, r, fill):
    draw.rounded_rectangle(box, radius=r, fill=fill)


def make(size: int) -> Image.Image:
    s = size * 4  # supersampling
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Fondo degradado simulado (dos capas)
    rounded(d, [0, 0, s - 1, s - 1], int(s * 0.22), (52, 120, 246, 255))
    overlay = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    rounded(od, [0, int(s * 0.45), s - 1, s - 1], int(s * 0.22), (124, 77, 255, 130))
    img = Image.alpha_composite(img, overlay)
    d = ImageDraw.Draw(img)

    # Marco de recorte (esquinas blancas)
    m = int(s * 0.24)
    L = int(s * 0.20)   # longitud de cada esquina
    w = max(2, int(s * 0.045))
    white = (255, 255, 255, 255)
    # superior izq
    d.line([(m, m), (m + L, m)], fill=white, width=w)
    d.line([(m, m), (m, m + L)], fill=white, width=w)
    # superior der
    d.line([(s - m, m), (s - m - L, m)], fill=white, width=w)
    d.line([(s - m, m), (s - m, m + L)], fill=white, width=w)
    # inferior izq
    d.line([(m, s - m), (m + L, s - m)], fill=white, width=w)
    d.line([(m, s - m), (m, s - m - L)], fill=white, width=w)
    # inferior der
    d.line([(s - m, s - m), (s - m - L, s - m)], fill=white, width=w)
    d.line([(s - m, s - m), (s - m, s - m - L)], fill=white, width=w)

    # Punto de grabacion (centro)
    rr = int(s * 0.11)
    cx = cy = s // 2
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 59, 48, 255))

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    out = Path(__file__).with_name("icon.ico")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [make(sz) for sz in sizes]
    imgs[-1].save(out, format="ICO", sizes=[(sz, sz) for sz in sizes],
                  append_images=imgs[:-1])
    # PNG de previsualizacion
    make(256).save(Path(__file__).with_name("icon_preview.png"))
    print("Icono generado:", out)


if __name__ == "__main__":
    main()
