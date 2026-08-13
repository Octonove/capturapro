# CapturaPro

Aplicación de escritorio para **Windows** que permite hacer **capturas de pantalla (imagen)** y **grabaciones de vídeo** —a pantalla completa, por monitor o por área seleccionada— con **editor de anotaciones** y grabación a **calidad nativa** mediante FFmpeg.

## ⬇️ Descargar (Windows 10/11)

### ➡️ [**Descargar CapturaPro (instalador .exe)**](https://github.com/Octonove/capturapro/releases/latest/download/CapturaPro-Setup.exe)

Descarga **directa** del instalador, sin registro. También puedes ver la [última versión y notas](https://github.com/Octonove/capturapro/releases/latest).

> Si Windows muestra *"Windows protegió tu PC"* (es normal en programas nuevos sin firma): pulsa **Más información → Ejecutar de todas formas**. Se instala sin permisos de administrador.

---

## Funciones

### Captura de imagen
- **Pantalla completa** (todo el escritorio, incluido multimonitor).
- **Elegir pantalla** (seleccionar un monitor concreto).
- **Área seleccionada** (arrastrar un rectángulo sobre cualquier pantalla).
- **Editor** integrado tras cada captura:
  - Flechas, líneas, rectángulos, elipses, lápiz libre, **resaltador**, **texto** y
    **difuminado** (censura datos sensibles arrastrando un rectángulo; la intensidad
    se controla con el Grosor).
  - Color y grosor configurables, tamaño de fuente para el texto.
  - Deshacer / rehacer (Ctrl+Z / Ctrl+Y).
  - **Guardar** (PNG o JPG a resolución original, sin perder calidad) o **copiar al portapapeles** (Ctrl+C).
- Retardo opcional antes de capturar (0–10 s).

### Grabación de vídeo
- **Pantalla completa**, **monitor concreto** o **área seleccionada**.
- **Presets de calidad**:
  - **Alta** — casi sin pérdida (CRF 16). Recomendado para "que se vea igual que en pantalla".
  - **Media** — equilibrado (CRF 23).
  - **Baja** — archivo pequeño (CRF 30).
- FPS configurable (15 / 24 / 30 / 60).
- **Codificador**: **GPU** (NVIDIA NVENC / AMD AMF / Intel QSV) por defecto si está disponible —ideal para grabar a alta resolución sin perder fotogramas— o CPU `libx264` (máxima calidad). Se detectan automáticamente.
- **Pausar / reanudar** la grabación: cada pausa cierra un segmento y al detener se unen sin recodificar en **un único vídeo final sin pérdida** (la pausa se excluye del tiempo grabado).
- Captura del puntero del ratón (opcional).
- **Audio de micrófono** opcional (dispositivos detectados automáticamente).
- Control flotante mientras grabas: cronómetro + **Pausar** + **Detener**. El vídeo se finaliza correctamente (no se corrompe) al detener.

### Exportar a GIF
- Botón **"Convertir vídeo a GIF…"**: convierte cualquier vídeo a un **GIF optimizado** (dos pasadas con paleta de color para máxima calidad). Permite elegir FPS y anchura.

### Atajos de teclado globales
Funcionan aunque la app no tenga el foco (se pueden desactivar en Ajustes):
| Atajo | Acción |
|---|---|
| `Ctrl+Shift+1` | Captura de pantalla completa |
| `Ctrl+Shift+2` | Captura de área seleccionada |
| `Ctrl+Shift+3` | Captura: elegir pantalla |
| `Ctrl+Shift+R` | Iniciar / detener grabación |
| `Ctrl+Shift+P` | Pausar / reanudar grabación |

> **Audio del sistema**: requiere un dispositivo *loopback* (p. ej. "Stereo Mix" o un cable de audio virtual). Este equipo no tiene uno, por lo que solo se ofrece micrófono. Si instalas uno, aparecerá en la lista.

---

## Requisitos
- Windows 10/11.
- **FFmpeg** (ya detectado en tu equipo). Si construyes el `.exe`, FFmpeg se empaqueta dentro y la app es portable.

---

## Ejecutar en modo desarrollo
```powershell
# Desde la carpeta del proyecto
./run.ps1
```
o directamente:
```powershell
.\.venv\Scripts\python.exe CapturaPro.py
```

## Construir el ejecutable (.exe)
```powershell
./build/build.ps1
```
El ejecutable quedará en:
```
dist\CapturaPro\CapturaPro.exe
```
La carpeta `dist\CapturaPro\` es **portable**: cópiala completa a cualquier PC con Windows y ejecuta `CapturaPro.exe` (no requiere instalar Python ni FFmpeg).

> Para un icono personalizado, coloca `build\icon.ico` antes de compilar.

## Crear el instalador único (para compartir)
Para generar **un solo archivo `.exe`** que instala la app en otro PC (con acceso directo en el menú Inicio, escritorio opcional y desinstalador):
```powershell
./build/build-installer.ps1
```
El instalador quedará en:
```
installer\CapturaPro-Setup-1.0.0.exe
```
Ese archivo es lo único que necesitas enviar a otra persona. Al ejecutarlo:
- Instala **sin permisos de administrador** (por usuario).
- No requiere Python ni FFmpeg en el PC de destino (van incluidos).
- Crea accesos directos y un desinstalador estándar de Windows.

> Requiere [Inno Setup](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup --source winget`). El script lo localiza automáticamente.

---

## Estructura del proyecto
```
CapturaPro/
├─ CapturaPro.py            # lanzador / entrada de PyInstaller
├─ run.ps1                  # ejecutar en desarrollo
├─ requirements.txt
├─ capturapro/              # paquete principal
│  ├─ app.py                # ventana principal y orquestación
│  ├─ config.py             # ajustes y presets de calidad
│  ├─ ffmpeg_utils.py       # detección de FFmpeg/encoders y comandos
│  ├─ monitors.py           # monitores + DPI awareness
│  ├─ screenshot.py         # captura de imagen (mss → Pillow)
│  ├─ region_selector.py    # overlay de selección de área
│  ├─ recorder.py           # control de FFmpeg (segmentos, pausa/reanudar, concat)
│  ├─ editor.py             # editor de anotaciones
│  ├─ hotkeys.py            # atajos de teclado globales (Win32)
│  └─ clipboard.py          # copiar imagen al portapapeles
└─ build/
   ├─ CapturaPro.spec       # configuración de PyInstaller
   ├─ build.ps1             # compila el ejecutable (carpeta portable)
   ├─ CapturaPro.iss        # script del instalador (Inno Setup)
   ├─ build-installer.ps1   # genera el instalador .exe único
   └─ gen_icon.py           # genera build/icon.ico
```

## Notas técnicas
- **Calidad sin pérdida**: el vídeo se captura con `gdigrab` a resolución y FPS nativos y se codifica con CRF bajo (16 en "Alta"), prácticamente indistinguible del original. Para máxima nitidez de texto, "Alta" usa el menor CRF razonable.
- **Coordenadas exactas**: el proceso es *per-monitor DPI aware*, de modo que la selección de área y los recortes coinciden píxel a píxel en pantallas con escalado.
- **Exportación de imagen**: las anotaciones se rasterizan con Pillow sobre la imagen **original** (no sobre la vista escalada), por lo que el archivo guardado conserva la resolución completa.
- **Pausa sin pérdida**: al pausar se cierra un segmento `.mp4` y al reanudar se abre otro; al detener se concatenan con `-c copy` (sin recodificar) en un único vídeo.
- **GIF de calidad**: conversión en dos pasadas (`palettegen` + `paletteuse`) para evitar el bandeado de color típico de los GIF.
- **Atajos globales**: implementados con `RegisterHotKey` de Win32 (sin dependencias externas); se ejecutan en el hilo de Tk de forma segura.
- Configuración y registro en `%APPDATA%\CapturaPro\`.
