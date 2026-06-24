"""Sistema de diseno compartido (estilo SimplificaconIA).

Paleta moderna "IA / tech" (azul + neutros limpios) y helpers para una interfaz
Tkinter coherente entre las herramientas: cabecera de marca, botones, tarjetas,
pestanas y barra de estado. Mantener identico en las 3 apps.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# --- Paleta ---------------------------------------------------------------
PRIMARY = "#2563EB"        # azul de marca (botones/acentos)
PRIMARY_DARK = "#1D4ED8"   # hover
PRIMARY_PRESS = "#1E40AF"  # pressed
PRIMARY_DIS = "#A8C2F4"    # primary deshabilitado
HEAD_SUB = "#DCE7FF"       # subtitulo sobre cabecera
ACCENT = "#6D5BF5"         # indigo (toques "IA")
TEXT = "#0F172A"           # texto principal (slate-900)
MUTED = "#64748B"          # texto secundario (slate-500)
BG = "#FFFFFF"
SURFACE = "#EEF2F8"        # fondos sutiles / pestanas inactivas
CARD = "#F8FAFC"           # tarjetas / labelframes
BORDER = "#E2E8F0"         # bordes
SUCCESS = "#16A34A"
DANGER = "#DC2626"
DANGER_DIM = "#7F1D1D"
WHITE = "#FFFFFF"

FONT = "Segoe UI"
F_TITLE = (FONT, 19, "bold")
F_SUB = (FONT, 10)
F_H = (FONT, 11, "bold")
F_BODY = (FONT, 10)
F_BTN = (FONT, 10, "bold")
F_SMALL = (FONT, 9)


def apply(root: tk.Misc) -> None:
    """Aplica el tema (basado en 'clam', que permite control total de color)."""
    try:
        root.configure(bg=BG)
    except tk.TclError:
        pass
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass

    st.configure(".", background=BG, foreground=TEXT, font=F_BODY,
                 focuscolor=PRIMARY, bordercolor=BORDER)
    st.configure("TFrame", background=BG)
    st.configure("Card.TFrame", background=CARD)
    st.configure("TLabel", background=BG, foreground=TEXT, font=F_BODY)
    st.configure("Muted.TLabel", background=BG, foreground=MUTED, font=F_SMALL)
    st.configure("H.TLabel", background=BG, foreground=TEXT, font=F_H)
    st.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=F_SMALL)

    # Tarjetas (LabelFrame)
    st.configure("TLabelframe", background=CARD, bordercolor=BORDER,
                 relief="solid", borderwidth=1)
    st.configure("TLabelframe.Label", background=CARD, foreground=PRIMARY, font=F_H)

    # Botones
    st.configure("TButton", font=F_BODY, padding=(12, 7), relief="flat",
                 background=SURFACE, foreground=TEXT, bordercolor=BORDER)
    st.map("TButton",
           background=[("active", "#E2E8F0"), ("pressed", "#CBD5E1"),
                       ("disabled", "#F1F5F9")],
           foreground=[("disabled", "#94A3B8")])
    st.configure("Primary.TButton", font=F_BTN, padding=(16, 9), relief="flat",
                 background=PRIMARY, foreground=WHITE, bordercolor=PRIMARY)
    st.map("Primary.TButton",
           background=[("active", PRIMARY_DARK), ("pressed", PRIMARY_PRESS),
                       ("disabled", PRIMARY_DIS)],
           foreground=[("disabled", "#EDF2FE")])

    # Controles
    for s in ("TRadiobutton", "TCheckbutton"):
        st.configure(s, background=CARD, foreground=TEXT, font=F_BODY)
        st.map(s, background=[("active", CARD)],
               indicatorcolor=[("selected", PRIMARY)])
    st.configure("TCombobox", padding=5, arrowsize=14)
    st.configure("TSpinbox", padding=4, arrowsize=12)
    st.configure("TEntry", padding=4)

    # Pestanas
    st.configure("TNotebook", background=BG, bordercolor=BORDER, tabmargins=(6, 6, 6, 0))
    st.configure("TNotebook.Tab", background=SURFACE, foreground=MUTED,
                 padding=(18, 9), font=F_BODY)
    st.map("TNotebook.Tab",
           background=[("selected", BG)],
           foreground=[("selected", PRIMARY)],
           expand=[("selected", [1, 1, 1, 0])])

    # Progreso
    st.configure("TProgressbar", background=PRIMARY, troughcolor=SURFACE,
                 bordercolor=SURFACE, lightcolor=PRIMARY, darkcolor=PRIMARY)

    # Barra de estado
    st.configure("Status.TLabel", background=SURFACE, foreground=MUTED,
                 font=F_SMALL, padding=(12, 6))


def header(parent: tk.Misc, title: str, subtitle: str = "") -> tk.Frame:
    """Cabecera de marca: banda de color con titulo claro."""
    bar = tk.Frame(parent, bg=PRIMARY)
    bar.pack(fill="x")
    inner = tk.Frame(bar, bg=PRIMARY)
    inner.pack(fill="x", padx=18, pady=(13, 13))
    tk.Label(inner, text=title, bg=PRIMARY, fg=WHITE, font=F_TITLE).pack(side="left")
    if subtitle:
        tk.Label(inner, text=subtitle, bg=PRIMARY, fg=HEAD_SUB,
                 font=F_SUB).pack(side="left", padx=(12, 0), pady=(6, 0))
    return bar


def status_bar(parent: tk.Misc, text: str = "") -> ttk.Label:
    lbl = ttk.Label(parent, text=text, style="Status.TLabel", anchor="w")
    lbl.pack(fill="x", side="bottom")
    return lbl
