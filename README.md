# NV Asset Forge

Generador local de assets 2D y 3D para videojuegos usando los modelos de **NVIDIA Build** (build.nvidia.com).
Funciona en Windows, macOS y Linux. No usa tokens de Claude: toda la IA la ponen los modelos de NVIDIA (o tu router LLM local), y el render y el procesado se hacen en tu PC.

## Qué hace
| Paso | Dónde se ejecuta | Modelo |
|---|---|---|
| Optimizar tu prompt (escribe en español) | NVIDIA o LLM local (FreeLLMAPI) | `meta/llama-3.3-70b-instruct` (cambiable) |
| Imagen 2D | NVIDIA cloud o NIM local | FLUX.1-dev / FLUX.1-schnell |
| Variaciones con el mismo personaje (poses, vistas) | NVIDIA cloud o NIM local | FLUX.1-Kontext-dev |
| Modelo 3D (.glb) | NVIDIA cloud o NIM local | Microsoft TRELLIS |
| Quitar fondo, recortar, pixel art, texturas tileables, potencias de 2 | **Local** (navegador) | — |
| Visor 3D, render HD, sprite sheets de 4/8/16 direcciones, miniaturas | **Local** (three.js / WebGL) | — |

Tipos de asset: personaje, objeto/arma, icono, textura tileable, fondo, UI, VFX, concept art, 3D desde concept (★ mejor calidad) y 3D desde texto.

## Instalar (una sola vez)
1. Instala **Node.js 18 o superior** (LTS): https://nodejs.org
2. Consigue tu API key gratuita en https://build.nvidia.com (entra en cualquier modelo → *Get API Key*).

## Arrancar
- **Windows:** doble clic en `start.bat`
- **macOS:** doble clic en `start.command` (la primera vez: clic derecho → Abrir)
- **Linux:** `./start.sh`

Se abre `http://localhost:7860`. Pega la API key en **Ajustes** y listo.

## Biblioteca de assets (almacenamiento)
Los assets se guardan como archivos normales en tu disco, con una carpeta por asset:

```
library/
  MiJuego/
    2d/orc_knight_mx1a2b/   source.png · processed_01_64x171.png · meta.json
    3d/treasure_chest_mx1a3c/  model.glb · concept.png · thumb.png · spritesheet_8dir_256px_e30.png · meta.json
  _papelera/                (lo que borras; recupérable)
```

`meta.json` guarda el prompt original, el prompt optimizado, el modelo, la semilla y los tags, así que cualquier asset se puede reproducir.
Por qué así: Unity, Godot y Unreal importan carpetas directamente, Git/Git LFS lo versiona sin conversiones, y no hay base de datos que se pueda corromper.
En **Ajustes → Carpeta de la biblioteca** puedes apuntar a:
- la carpeta de arte de tu proyecto (p. ej. `.../MiProyectoUnity/Assets/Generated`), para que aparezcan en el motor al instante;
- una carpeta de OneDrive, Dropbox o Google Drive, para tener copia en la nube y en todos tus PCs.

## Ejecutar los modelos en tu propia GPU (opcional)
Con una GPU NVIDIA RTX y Docker (o WSL2 en Windows) puedes correr FLUX y TRELLIS en local como NVIDIA NIM, sin límites ni colas:

```bash
export NGC_API_KEY=nvapi-...
docker run -it --rm --gpus all -e NGC_API_KEY -p 8001:8000 \
  -e NIM_MODEL_VARIANT=large:text+large:image nvcr.io/nim/microsoft/trellis:latest
docker run -it --rm --gpus all -e NGC_API_KEY -e HF_TOKEN -p 8000:8000 \
  nvcr.io/nim/black-forest-labs/flux.1-dev:latest
```
Luego, en Ajustes, pon Imagen/3D en **NIM local** (`http://localhost:8000` y `http://localhost:8001`).

## LLM local (FreeLLMAPI)
En Ajustes → *LLM que optimiza los prompts* → **Local compatible OpenAI**. URL por defecto `http://localhost:31415/v1`, modelo `auto`. Si no responde, la app pasa sola al LLM de NVIDIA.

## Notas
- La nube de NVIDIA es un servicio de prueba con límites de uso. Revisa la licencia de cada modelo antes de un uso comercial (FLUX.1-dev pide licencia comercial a Black Forest Labs; TRELLIS es MIT).
- En la nube, el paso imagen→3D sube tu imagen a NVIDIA. Si ese servicio falla, la app pasa sola a texto→3D.
- El servidor solo escucha en `127.0.0.1`: nadie de tu red puede usarlo.
- Atajo: `Ctrl+Enter` en la descripción para generar.
