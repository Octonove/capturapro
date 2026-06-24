"""Construye la UI (ventana principal y editor) sin entrar en mainloop,
para detectar errores de construccion de widgets. No requiere interaccion."""

from __future__ import annotations

import sys
import tkinter as tk

from PIL import Image

from capturapro.app import App
from capturapro.config import load_config
from capturapro.editor import EditorWindow
from capturapro.monitors import set_dpi_awareness


def main() -> int:
    set_dpi_awareness()
    cfg = load_config()
    cfg.hotkeys_enabled = False  # no registrar atajos globales en el test de UI
    root = tk.Tk()
    root.withdraw()  # oculta: solo probamos construccion
    try:
        app = App(root, cfg)
        root.update_idletasks()
        print("[OK ] ventana principal construida")

        img = Image.new("RGB", (800, 600), (200, 210, 220))
        ed = EditorWindow(root, img, cfg, suggested_name="test")
        ed.win.withdraw()
        root.update_idletasks()
        print("[OK ] editor construido")

        # Ejercita el aplanado/exportacion interna del editor
        from capturapro.editor import Annotation
        ed.annotations.append(Annotation("arrow", "#ff0000", 5, [(10, 10), (200, 200)]))
        ed.annotations.append(Annotation("text", "#000000", 4, [(50, 50)],
                                         text="Prueba", font_size=30))
        ed.annotations.append(Annotation("highlight", "#ffff00", 14, [(20, 400), (700, 410)]))
        ed._redraw()  # composita anotaciones via Pillow (camino WYSIWYG nuevo)
        root.update_idletasks()
        flat = ed._flatten()
        assert flat.size == (800, 600)
        print("[OK ] composite + exportacion del editor")

        # Atajos ignorados mientras se edita texto (binding guard)
        ed._begin_text(100, 100)
        assert ed._text_entry is not None
        ed._kb(ed.undo)  # no debe hacer pop con el Entry activo
        assert len(ed.annotations) == 3, "undo no debe actuar durante edicion de texto"
        ed._cancel_text()
        assert ed._text_entry is None and ed._text_window is None
        print("[OK ] guard de atajos y ciclo de vida del Entry de texto")

        # Ciclo de vida de los atajos globales (alta/arranque/parada)
        from capturapro.hotkeys import GlobalHotkeys, MOD_CONTROL, MOD_ALT
        hk = GlobalHotkeys(root)
        hk.add(MOD_CONTROL | MOD_ALT, 0x7B, lambda: None, "Ctrl+Alt+F12")  # vk poco usado
        hk.start()
        root.update_idletasks()
        hk.stop()
        print("[OK ] atajos globales arrancan y se detienen sin error")
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("[FAIL]", exc)
        return 1
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass
    print("RESULTADO: UI OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
