// NV Asset Forge · traducción de la interfaz (español ⇄ inglés).
// La interfaz está escrita en español; en inglés cada texto visible se traduce al vuelo
// (también lo que se añade después: avisos, registros, listas). Idioma: ajuste guardado o el del navegador.
(() => {
  let saved = null; try { saved = localStorage.getItem('nvf_lang'); } catch {}
  const LANG = saved || ((navigator.language || 'es').toLowerCase().startsWith('es') ? 'es' : 'en');
  window.NVF_LANG = LANG;
  window.setLang = (l) => { try { localStorage.setItem('nvf_lang', l); } catch {} location.reload(); };
  window.tr = (s) => s;
  if (LANG === 'es') return;

  const D = {
    // cabecera y paneles
    '2D · 3D game assets': '2D · 3D game assets', 'Proyecto': 'Project', 'Ajustes': 'Settings', '⚙ Ajustes': '⚙ Settings', '📁 Carpeta': '📁 Folder',
    'Abrir la carpeta de la biblioteca': 'Open the library folder', 'Sin API key': 'No API key', 'NVIDIA conectado': 'NVIDIA connected', 'Blender…': 'Blender…', 'Sin Blender': 'No Blender',
    'Blender se usa para optimizar modelos y renderizar': 'Blender is used to optimize models and render', '⚡ Trabajos': '⚡ Jobs', 'Trabajos': 'Jobs', 'Trabajos en curso': 'Running jobs',
    'Clic: ver su registro · ✕: cancelar': 'Click: view log · ✕: cancel', 'Cerrar': 'Close', 'Sin trabajos todavía.': 'No jobs yet.',
    'En curso': 'Running', 'Listo': 'Done', 'Error': 'Error', 'Cancelado': 'Cancelled', 'Cancelar': 'Cancel',
    'Nuevo asset': 'New asset', 'Receta de estudio (opcional)': 'Studio recipe (optional)', '— Escribir desde cero —': '— Write from scratch —',
    'Describe lo que necesitas (en español vale)': 'Describe what you need (any language)', 'Ej.: caballero orco con hacha a dos manos y armadura de cuero oxidada': 'E.g.: orc knight with a two-handed axe and rusty leather armor',
    'Tipo de asset': 'Asset type', 'Estilo': 'Style', 'Tamaño': 'Size', 'Calidad': 'Quality', 'Borrador': 'Draft', 'Normal': 'Normal', 'Alta': 'High', 'Variantes': 'Variants', 'Semilla': 'Seed', 'aleatoria': 'random',
    'Modelo de imagen': 'Image model', 'Modelo 3D': '3D model', 'Optimizar prompt con LLM': 'Optimize prompt with LLM', 'Limpieza automática (quitar fondo y recortar sprites)': 'Auto clean-up (remove background and crop sprites)',
    'Copiar el estilo de la imagen de referencia del proyecto': "Copy the style of the project's reference image", 'Ver / editar prompt optimizado': 'View / edit optimized prompt',
    'Prompt de imagen (FLUX)': 'Image prompt (FLUX)', 'Prompt 3D (TRELLIS, máx. 77)': '3D prompt (TRELLIS, max 77)', 'Nombre del asset': 'Asset name',
    'Si generas ahora se usará este prompt tal cual. Cambia la descripción para descartarlo.': 'If you generate now this prompt is used as is. Change the description to discard it.',
    'Generar asset': 'Generate asset',
    'Pack coherente ★': 'Coherent pack ★', 'Describe el juego o el tema del pack': 'Describe the game or the theme of the pack',
    'Ej.: roguelike de mazmorras élficas corruptas: héroe, 3 enemigos, cofre, pociones, iconos de habilidades, suelo de baldosas, fondo de cripta': 'E.g.: roguelike in corrupted elven dungeons: hero, 3 enemies, chest, potions, skill icons, tiled floor, crypt background',
    'Assets': 'Assets', 'Generar pack': 'Generate pack', 'El LLM diseña una biblia de estilo común y la lista de assets; FLUX los pinta todos con las mismas reglas visuales. Se etiquetan como': 'The LLM designs a shared style bible and the asset list; FLUX paints them all with the same visual rules. They are tagged as',
    'pack:nombre': 'pack:name',
    'Estilo del proyecto (colección)': 'Project style (collection)', 'Guía de estilo que heredan todos los assets': 'Style guide inherited by every asset',
    'Ej.: pixel art 32px, paleta fría de 16 colores, contorno negro de 1px, luz desde arriba a la izquierda, ambiente nórdico': 'E.g.: 32px pixel art, cold 16-color palette, 1px black outline, light from the top left, Nordic mood',
    'Sin imagen de referencia. Abre un asset y pulsa “Usar como referencia”.': 'No reference image. Open an asset and press “Use as reference”.',
    'Usar asset actual como referencia': 'Use current asset as reference', 'Quitar': 'Remove', 'Guardar estilo': 'Save style',
    'Diseñador de mundos': 'World designer', 'Partir de': 'Start from', 'Mundo nuevo desde cero': 'New world from scratch', 'Describe el mundo o los cambios': 'Describe the world or the changes',
    'Ej.: añade un volcán al este, un puerto pirata en la bahía del sur y un pantano con ruinas junto al río': 'E.g.: add a volcano in the east, a pirate port in the southern bay and a swamp with ruins by the river',
    'Hora del día': 'Time of day', 'Día': 'Day', 'Amanecer': 'Dawn', 'Atardecer': 'Dusk', 'Noche': 'Night', 'Vistas de juego': 'Gameplay shots',
    'Diseñar mundo': 'Design world', 'Modificar este': 'Modify this one', 'Aplica los cambios al mundo abierto': 'Apply the changes to the open world',
    'El LLM escribe la receta, Blender la construye con módulos de calidad y un director de arte la revisa. Requiere Blender.': 'The LLM writes the recipe, Blender builds it with quality modules and an art director reviews it. Requires Blender.',
    'Receta del mundo abierto (JSON editable)': 'Recipe of the open world (editable JSON)', 'Reconstruir con esta receta': 'Rebuild with this recipe',
    'Prototipo jugable': 'Playable prototype', 'Describe el juego': 'Describe the game',
    'Ej.: plataformas 2D donde el caballero orco salta entre rocas y esquiva murciélagos; 3 vidas; gana al llegar a 1000 puntos': 'E.g.: 2D platformer where the orc knight jumps between rocks and dodges bats; 3 lives; win at 1000 points',
    'Usará los 12 assets más recientes del proyecto. Ctrl+clic en la biblioteca para elegir cuáles.': 'Uses the 12 most recent assets of the project. Ctrl+click in the library to choose.',
    'Crear juego': 'Create game', 'Mejorar seleccionado': 'Improve selected', 'Aplica la descripción como cambio al juego seleccionado': 'Apply the description as a change to the selected game',
    // visor y herramientas
    'Sin asset seleccionado': 'No asset selected', 'Crea tu primer asset': 'Create your first asset', 'Describe el asset a la izquierda y pulsa Generar.': 'Describe the asset on the left and press Generate.',
    'Todo se guarda en tu PC y puedes procesarlo aquí sin gastar créditos.': 'Everything is saved on your PC and you can process it here without spending credits.',
    'Trabajando…': 'Working…', '☆ Favorito': '☆ Favorite', '★ Favorito': '★ Favorite', 'Favorito: sus prompts guiarán las próximas generaciones del proyecto': "Favorite: its prompts will guide the project's next generations",
    'Fondo': 'Background', 'Tolerancia': 'Tolerance', 'Quitar fondo': 'Remove bg', 'Recortar': 'Crop', 'Pixel': 'Pixel', 'Ancho en píxeles': 'Width in pixels', 'Colores': 'Colors', 'Pixelar': 'Pixelate',
    'Tile': 'Tile', 'Hacer tileable': 'Make tileable', 'Ver mosaico': 'View tiled', 'Ver imagen': 'View image', 'Tileset': 'Tileset', 'Segundo terreno (textura de la biblioteca)': 'Second terrain (library texture)',
    'Tamaño de tile': 'Tile size', 'Pixel + contorno': 'Pixel + outline', 'Suave HD': 'Soft HD', 'Crear autotile': 'Create autotile', '🖌 Pintar mapa': '🖌 Paint map',
    'Luz 2D': '2D light', 'Normal map + luz': 'Normal map + light', 'Normal map para iluminación 2D (Godot, Unity) con vista previa de luz': 'Normal map for 2D lighting (Godot, Unity) with light preview',
    'POT auto': 'POT auto', 'Redimensionar': 'Resize', '↶ Deshacer': '↶ Undo', 'Guardar versión': 'Save version', 'Animar': 'Animate', 'Generar fotogramas': 'Generate frames',
    'Sprite sheet': 'Sprite sheet', 'Alto de cada fotograma (px)': 'Frame height (px)', 'Montar sprite sheet': 'Build sprite sheet', '▶ Vista previa': '▶ Preview',
    'IA': 'AI', 'Variación: ahora corriendo, vista lateral…': 'Variation: now running, side view…', 'Variación': 'Variation', '→ 3D': '→ 3D',
    '⟳ Rotar': '⟳ Rotate', 'Rejilla': 'Grid', 'Luz': 'Light', 'Elevación de cámara (º)': 'Camera elevation (°)', 'Renderizar': 'Render',
    'Altura real en metros (0 = no cambiar)': 'Real height in meters (0 = keep)', 'Máximo de triángulos LOD0 (0 = sin límite)': 'Max LOD0 triangles (0 = no limit)',
    'Optimizar + LODs + FBX': 'Optimize + LODs + FBX', 'Render Blender': 'Blender render', 'Render HD PNG': 'HD PNG render', 'Miniatura': 'Thumbnail',
    // biblioteca
    'Biblioteca': 'Library', 'Buscar nombre o tag…': 'Search name or tag…', 'Todo': 'All', 'Favoritos': 'Favorites', 'Borrar': 'Delete',
    '🎨 Paleta común': '🎨 Shared palette', 'Mismos colores exactos para los sprites marcados con Ctrl+clic (o los del filtro actual)': 'Exactly the same colors for the sprites Ctrl+clicked (or the current filter)',
    'ZIP genérico': 'Generic ZIP', '⬇ Exportar a motor': '⬇ Export to engine', 'Exporta los assets marcados con Ctrl+clic (o los 40 más recientes)': 'Exports the Ctrl+clicked assets (or the 40 most recent)',
    'Aún no hay assets.': 'No assets yet.', 'Nada coincide con el filtro.': 'Nothing matches the filter.', 'JUEGO': 'GAME',
    // ajustes
    'Todo se guarda en': 'Everything is stored in', 'dentro de la carpeta de la app, solo en tu PC.': "inside the app folder, only on your PC.", 'API key de NVIDIA Build': 'NVIDIA Build API key',
    'Gratis en': 'Free at', '→ cualquier modelo → “Get API Key”.': '→ any model → “Get API Key”.', 'Modelo de imagen por defecto': 'Default image model', 'Modelo 3D por defecto': 'Default 3D model',
    'Otro modelo de imagen (ruta en build.nvidia.com)': 'Another image model (path on build.nvidia.com)', 'Otro modelo 3D (ruta)': 'Another 3D model (path)',
    'publisher/modelo, p. ej. stabilityai/sdxl-turbo': 'publisher/model, e.g. stabilityai/sdxl-turbo', 'publisher/modelo': 'publisher/model',
    'LLM de código (modelos 3D en Blender y juegos)': 'Code LLM (Blender 3D models and games)', 'Modelo de visión (director de arte)': 'Vision model (art director)',
    'LLM que optimiza los prompts': 'LLM that optimizes prompts', 'Local compatible OpenAI (FreeLLMAPI)': 'Local OpenAI-compatible (FreeLLMAPI)', 'Modelo LLM de NVIDIA': 'NVIDIA LLM model',
    'URL base': 'Base URL', 'Modelo': 'Model', 'API key del router local (si la pide)': 'Local router API key (if required)',
    'Abre FreeLLMAPI, copia su URL y su clave. Si no responde, la app usa automáticamente el LLM de NVIDIA. Imagen y 3D siempre van con NVIDIA.': 'Open FreeLLMAPI and copy its URL and key. If it does not answer, the app automatically uses the NVIDIA LLM. Image and 3D always use NVIDIA.',
    'Imagen (FLUX)': 'Image (FLUX)', '3D (TRELLIS)': '3D (TRELLIS)', 'Nube NVIDIA': 'NVIDIA cloud', 'NIM local': 'Local NIM', 'URL NIM imagen': 'Image NIM URL', 'URL NIM 3D': '3D NIM URL',
    'Dónde se ejecutan los modelos.': 'Where the models run.', '“Nube” usa build.nvidia.com. “NIM local” usa un contenedor NVIDIA NIM en tu propio PC (GPU RTX con Docker/WSL); sin límites ni colas.': '“Cloud” uses build.nvidia.com. “Local NIM” uses an NVIDIA NIM container on your own PC (RTX GPU with Docker/WSL); no limits or queues.',
    'Carpeta de la biblioteca': 'Library folder', 'Recomendado: déjala en la app, o apúntala a la carpeta de arte de tu proyecto Unity/Godot, o a una carpeta de OneDrive/Dropbox/Google Drive para tener copia en la nube.': 'Recommended: keep it in the app, or point it to the art folder of your Unity/Godot project, or to a OneDrive/Dropbox/Google Drive folder for a cloud copy.',
    'Blender (vacío = detectar automáticamente)': 'Blender (empty = auto-detect)', 'Detectar': 'Detect', 'Gratis en blender.org. Se usa para optimizar modelos, LODs, FBX y renders de calidad.': 'Free at blender.org. Used to optimize models, LODs, FBX and quality renders.',
    'Probar conexión': 'Test connection', 'Guardar': 'Save', 'Idioma': 'Language',
    // estudio a pantalla completa
    'Terreno A': 'Terrain A', 'Terreno B': 'Terrain B', 'Pincel': 'Brush', 'Columnas': 'Columns', 'Filas': 'Rows', '🎲 Aleatorio': '🎲 Random', 'Todo A': 'All A',
    'Guardar mapa (PNG + Tiled + Godot)': 'Save map (PNG + Tiled + Godot)', 'Clic: pinta · clic derecho o Mayús: borra': 'Click: paint · right click or Shift: erase',
    'Guardar normal map': 'Save normal map', 'Mueve el ratón sobre el sprite: es una luz puntual. Así se verá en Godot (CanvasTexture) o Unity (Sprite Lit).': 'Move the mouse over the sprite: it is a point light. This is how it will look in Godot (CanvasTexture) or Unity (Sprite Lit).',
    // avisos
    'Abre primero el asset que quieres usar como referencia': 'Open the asset you want to use as reference first', 'Abre primero un mundo de la biblioteca': 'Open a world from the library first',
    'Ajustes guardados': 'Settings saved', 'Añade tu API key de NVIDIA': 'Add your NVIDIA API key', 'Cancelando…': 'Cancelling…', 'Crea primero un autotile': 'Create an autotile first',
    'Describe el asset que quieres': 'Describe the asset you want', 'Describe el mundo o elige una plantilla': 'Describe the world or pick a template',
    'Elige el segundo terreno (otra textura de la biblioteca)': 'Pick the second terrain (another library texture)', 'En cola: puedes seguir trabajando mientras tanto': 'Queued: you can keep working meanwhile',
    'Escribe la variación (p. ej. “mismo personaje atacando”)': 'Write the variation (e.g. “same character attacking”)', 'Escribe primero qué asset quieres': 'Write what asset you want first',
    'Escribe qué quieres cambiar': 'Write what you want to change', 'Estilo del proyecto guardado': 'Project style saved', 'Haz clic en un juego de la lista para seleccionarlo': 'Click a game in the list to select it',
    'Marca al menos 2 sprites con Ctrl+clic (o filtra por pack:nombre)': 'Ctrl+click at least 2 sprites (or filter by pack:name)', 'Movido a _papelera': 'Moved to _papelera (trash)',
    'Nada que deshacer': 'Nothing to undo', 'Primero pulsa “Montar sprite sheet”': 'Press “Build sprite sheet” first', 'Receta cargada: ajusta el texto si quieres y pulsa Generar': 'Recipe loaded: tweak the text if you want and press Generate',
    'Referencia de estilo guardada': 'Style reference saved', 'Trabajo cancelado': 'Job cancelled', 'Quitado de favoritos': 'Removed from favorites',
    '★ Guardado: las próximas generaciones del proyecto imitarán su estilo': "★ Saved: the project's next generations will imitate its style",
    'Autotile listo: PNG + Tiled (.tsx) + Godot (.tres) · pulsa 🖌 Pintar mapa': 'Autotile ready: PNG + Tiled (.tsx) + Godot (.tres) · press 🖌 Paint map',
    'Generando con NVIDIA…': 'Generating with NVIDIA…', 'Diseñando el pack…': 'Designing the pack…', 'Empaquetando…': 'Packing…', 'Montando autotile…': 'Building autotile…',
    // tipos, estilos, recetas y animaciones (vienen del servidor)
    'Personaje (sprite)': 'Character (sprite)', 'Objeto / arma / prop': 'Item / weapon / prop', 'Icono UI / inventario': 'UI / inventory icon', 'Textura tileable': 'Tileable texture',
    'Fondo / escenario': 'Background / scene', 'Elemento de UI': 'UI element', 'Efecto VFX': 'VFX effect', 'Concept art': 'Concept art', 'Modelo 3D pro en Blender ★': 'Pro 3D model in Blender ★',
    'Modelo 3D IA (concept → TRELLIS)': 'AI 3D model (concept → TRELLIS)', 'Modelo 3D IA (texto → TRELLIS)': 'AI 3D model (text → TRELLIS)',
    'Cuerpo entero, pose neutra, fondo limpio listo para recortar.': 'Full body, neutral pose, clean background ready to cut out.', 'Un único objeto centrado y completo.': 'A single centered, complete object.',
    'Silueta legible a tamaño pequeño.': 'Silhouette readable at small size.', 'Material repetible (suelo, pared, roca…).': 'Repeatable material (floor, wall, rock…).', 'Fondos, parallax, escenarios.': 'Backgrounds, parallax, scenes.',
    'Botones, paneles, marcos, barras.': 'Buttons, panels, frames, bars.', 'Magia, explosiones, energía (fondo negro para blending aditivo).': 'Magic, explosions, energy (black background for additive blending).',
    'Exploración visual para el equipo de arte.': 'Visual exploration for the art team.',
    'Automático': 'Automatic', 'Pixel art 16-bit': '16-bit pixel art', '★ HD-2D (pixel + luz cinematográfica)': '★ HD-2D (pixel + cinematic light)', '★ Cozy pixel (granja / vida)': '★ Cozy pixel (farming / life sim)',
    '★ Metroidvania gótico (pixel)': '★ Gothic metroidvania (pixel)', '★ Fantasía sombría pintada': '★ Grim painted fantasy', '★ Casual móvil brillante': '★ Bright casual mobile', '★ Isométrico estratégico': '★ Strategy isometric',
    '★ Cómic entintado': '★ Inked comic', '★ Cuento acuarela': '★ Storybook watercolor', 'Stylized hand-painted': 'Stylized hand-painted', 'Cartoon / cel-shading': 'Cartoon / cel-shading', 'Anime': 'Anime',
    'Realista PBR': 'Realistic PBR', 'Low poly': 'Low poly', 'Voxel': 'Voxel', 'Dark fantasy': 'Dark fantasy', 'Sci-fi': 'Sci-fi', 'Vector flat': 'Flat vector',
    'Personajes': 'Characters', 'Enemigos': 'Enemies', 'Objetos': 'Items', 'Iconos': 'Icons', 'Texturas': 'Textures', 'Fondos': 'Backgrounds', 'UI': 'UI', 'VFX': 'VFX', '3D': '3D',
    'Héroe aventurero': 'Adventurer hero', 'Maga elfa': 'Elf mage', 'Enano herrero': 'Dwarf blacksmith', 'Caballero oscuro (jefe)': 'Dark knight (boss)', 'Granjera cozy': 'Cozy farmer',
    'Slime': 'Slime', 'Esqueleto guerrero': 'Skeleton warrior', 'Gólem de piedra': 'Stone golem', 'Cofre del tesoro': 'Treasure chest', 'Poción de vida': 'Health potion', 'Espada legendaria': 'Legendary sword',
    'Iconos de habilidad': 'Skill icons', 'Moneda': 'Coin', 'Hierba': 'Grass', 'Adoquines': 'Cobblestones', 'Tierra de camino': 'Dirt path', 'Arena de playa': 'Beach sand',
    'Bosque encantado': 'Enchanted forest', 'Mazmorra': 'Dungeon', 'Pueblo al atardecer': 'Village at dusk', 'Panel de diálogo': 'Dialogue box', 'Barras de vida y maná': 'Health and mana bars',
    'FLUX.2 klein · rápido y nítido (recomendado)': 'FLUX.2 klein · fast and sharp (recommended)', 'FLUX.1 dev · más pasos (a veces saturado)': 'FLUX.1 dev · more steps (sometimes overloaded)',
    'Personalizado': 'Custom', 'Genérico': 'Generic', 'Buscando Blender…': 'Looking for Blender…', 'Optimizando con NVIDIA…': 'Optimizing with NVIDIA…', 'Probando…': 'Testing…',
    'Sin imagen de referencia. Abre un asset 2D y pulsa “Usar como referencia”.': 'No reference image. Open a 2D asset and press “Use as reference”.', 'Aún no hay juegos en este proyecto.': 'No games in this project yet.',
    '🧊 Escena 3D': '🧊 3D Scene', 'Editor de escenas 3D tipo Blender': 'Blender-style 3D scene editor', '🧊 Abrir en escena': '🧊 Open in scene', 'Abrir en el editor de escenas 3D': 'Open in the 3D scene editor',
    'Escena 3D': '3D Scene', 'Nueva': 'New', 'Abrir…': 'Open…', 'Nombre de la escena': 'Scene name', 'Guardar en biblioteca': 'Save to library', '⬇ Render PNG': '⬇ Render PNG', 'Volver al estudio': 'Back to the studio',
    'Añadir': 'Add', 'Kit modular': 'Modular kit', 'Naturaleza y luces': 'Nature and lights', '📦 Modelo de la biblioteca…': '📦 Library model…', 'Escena': 'Scene', 'Mover': 'Move', 'Rotar': 'Rotate', 'Escalar': 'Scale',
    'Ajuste': 'Snap', 'Ajuste a rejilla (0,5 m / 15°)': 'Grid snap (0.5 m / 15°)', 'Arriba': 'Top', 'Frente': 'Front', 'Perspectiva': 'Perspective', 'Propiedades': 'Properties', 'Selecciona un objeto.': 'Select an object.',
    'Entorno': 'Environment', 'Suelo': 'Ground', 'Césped': 'Grass', 'Ninguno': 'None', 'Nombre': 'Name', 'Posición (m)': 'Position (m)', 'Rotación (°)': 'Rotation (°)', 'Escala': 'Scale', 'Color': 'Color',
    'Color de la luz': 'Light color', 'Potencia': 'Power', 'Rugosidad': 'Roughness', 'Metálico': 'Metallic', 'Emisión (brillo propio)': 'Emission (self glow)', 'Textura de la biblioteca': 'Library texture', '— ninguna —': '— none —',
    'Repetición de la textura': 'Texture repeat', 'Vacía: añade piezas arriba.': 'Empty: add pieces above.', 'Modelos 3D de la biblioteca': 'Library 3D models', 'No hay modelos .glb todavía': 'No .glb models yet',
    'Escenas guardadas': 'Saved scenes', 'Aún no hay escenas': 'No scenes yet', 'La escena está vacía': 'The scene is empty', '✓ guardada en la biblioteca': '✓ saved to the library', '● sin guardar': '● unsaved',
    'Guardada: en el estudio puedes optimizarla y renderizarla con Blender (LODs, FBX, sprites)': 'Saved: in the studio you can optimize and render it with Blender (LODs, FBX, sprites)',
    'Cubo': 'Cube', 'Plano': 'Plane', 'Cilindro': 'Cylinder', 'Cono': 'Cone', 'Esfera': 'Sphere', 'Toro': 'Torus', 'Cápsula': 'Capsule', 'Muro': 'Wall', 'Muro con ventana': 'Wall with window', 'Muro con puerta': 'Wall with door',
    'Suelo 4×4': 'Floor 4×4', 'Tejado a dos aguas': 'Gable roof', 'Escalera': 'Stairs', 'Columna': 'Column', 'Arco': 'Arch', 'Valla': 'Fence', 'Caja': 'Crate', 'Barril': 'Barrel', 'Árbol': 'Tree', 'Pino': 'Pine', 'Roca': 'Rock',
    'Editor de escenas': 'Scene editor', 'Arbusto': 'Bush', 'Agua': 'Water', 'Luz puntual': 'Point light', 'Modelo': 'Model',
    'Impacto mágico': 'Magic impact', 'Curación': 'Healing', 'Taberna medieval': 'Medieval tavern', 'Pozo de piedra': 'Stone well',
  };
  const P = [ // textos con partes variables
    [/^Exportados (\d+) assets$/, 'Exported $1 assets'],
    [/^✓ (\d+) asset\(s\) listo\(s\)( · están en la biblioteca)?$/, (m, n, b) => `✓ ${n} asset(s) ready${b ? ' · they are in the library' : ''}`],
    [/^Limpieza automática: (\d+) sprite\(s\) sin fondo y recortados$/, 'Auto clean-up: $1 sprite(s) without background and cropped'],
    [/^🎨 (\d+) sprites con la misma paleta de (\d+) colores \(palette\.png en (.+)\)$/, '🎨 $1 sprites with the same $2-color palette (palette.png in $3)'],
    [/^Guardado (map_\d+): PNG, Tiled \(\.tmx\) y escena de Godot \(\.tscn\) junto al tileset$/, 'Saved $1: PNG, Tiled (.tmx) and Godot scene (.tscn) next to the tileset'],
    [/^Guardado (.+)$/, 'Saved $1'], [/^Pintor de mapas · (.+)$/, 'Map painter · $1'], [/^Luz 2D · (.+)$/, '2D light · $1'],
    [/^Usará (\d+) asset\(s\) elegidos \(Ctrl\+clic para quitar\)\.$/, 'Uses $1 chosen asset(s) (Ctrl+click to remove).'],
    [/^Unificando la paleta de (\d+) sprites…$/, 'Unifying the palette of $1 sprites…'],
    [/^Juego listo: se abre en otra pestaña$/, 'Game ready: it opens in another tab'],
    [/^(.+) · (\d+) fot\.$/, (m, a, n) => `${({'Idle (respirar)': 'Idle (breathing)', 'Andar': 'Walk', 'Correr': 'Run', 'Atacar': 'Attack', 'Saltar': 'Jump', 'Recibir daño': 'Take damage', 'Lanzar hechizo': 'Cast spell', 'Morir': 'Die'})[a] || a} · ${n} fr.`],
    [/^Referencia: (.+)\. Marca “Copiar el estilo…” al generar\.$/, 'Reference: $1. Tick “Copy the style…” when generating.'],
    [/^(\d+) objetos$/, '$1 objects'], [/^abierta: (.+)$/, 'opened: $1'],
    [/^clic: seleccionar · arrastrar: orbitar · der\.: desplazar · rueda: zoom$/, 'click: select · drag: orbit · right: pan · wheel: zoom'],
    [/^G\/R\/S mover\/rotar\/escalar · Mayús\+D duplicar · X\/Supr borrar · H ocultar · F encuadrar · Ctrl\+Z deshacer$/, 'G/R/S move/rotate/scale · Shift+D duplicate · X/Del delete · H hide · F frame · Ctrl+Z undo'],
    [/^(\d+) muestras?$/, '$1 samples'],
  ];
  const LOG = [ // líneas del registro de trabajos (llegan del servidor en español)
    [/^Optimizando prompt con (.+)…$/, 'Optimizing prompt with $1…'], [/^Prompt optimizado\.$/, 'Prompt optimized.'], [/^Aplicando la guía de estilo del proyecto\.$/, 'Applying the project style guide.'],
    [/^Aprendiendo de (\d+) favorito\(s\) ★ del proyecto\.$/, 'Learning from $1 ★ favorite(s) of the project.'],
    [/^Generando imagen (.*)con (.+)…$/, 'Generating image $1with $2…'], [/^✔ Guardado (.+)$/, '✔ Saved $1'],
    [/^Planificando un pack de (\d+) assets con (.+)…$/, 'Planning a pack of $1 assets with $2…'], [/^Pack “(.+)”: (.+)$/, 'Pack “$1”: $2'],
    [/^Biblia de estilo: (.+)$/, 'Style bible: $1'], [/^Guardada como guía de estilo del proyecto\.$/, 'Saved as the project style guide.'],
    [/^✔ Pack listo: (\d+)\/(\d+) assets\. Búscalo en la biblioteca con “(.+)”\.$/, '✔ Pack ready: $1/$2 assets. Find it in the library with “$3”.'],
    [/^■ Cancelado\. Lo ya generado se queda en la biblioteca\.$/, '■ Cancelled. What was already generated stays in the library.'],
    [/^Construyendo “(.+)” en Blender \((.+), (\d+) muestras\)…$/, 'Building “$1” in Blender ($2, $3 samples)…'],
    [/^Vista de juego (\d+): (.+)$/, 'Gameplay shot $1: $2'], [/^Plano de detalle (\d+): (.+)$/, 'Detail shot $1: $2'], [/^Hora del día: (.+)\.$/, 'Time of day: $1.'],
    [/^Director de arte: (.+)$/, 'Art director: $1'], [/^Bloqueado por el filtro de contenido de NVIDIA\. Reformula el prompt\.$/, 'Blocked by the NVIDIA content filter. Rephrase the prompt.'],
  ];
  const tx = (s) => {
    if (D[s] !== undefined) return D[s];
    const ic = s.match(/^([^A-Za-zÁ-úÑñ¿¡\d\s]+\s)(.+)$/); if (ic && D[ic[2]] !== undefined) return ic[1] + D[ic[2]]; // «■ Cubo» → «■ Cube»
    for (const [re, to] of P) if (re.test(s)) return s.replace(re, to);
    const m = s.match(/^(\d\d:\d\d:\d\d\s+)([✔⚠✖■]?\s*)(.*)$/s); // línea de registro con hora
    if (m) { for (const [re, to] of LOG) { const body = (m[2] + m[3]).trim(); if (re.test(body)) return m[1] + body.replace(re, to); if (re.test(m[3])) return m[1] + m[2] + m[3].replace(re, to); } }
    return s;
  };
  window.tr = (s) => { const t = String(s); const core = t.trim(); if (!core) return t; const out = tx(core); return out === core ? t : t.replace(core, out); };
  const fixText = (n) => { const v = n.nodeValue; if (!v || !/[A-Za-zÁ-ú]/.test(v)) return; const o = window.tr(v); if (o !== v) n.nodeValue = o; };
  const fixEl = (el) => {
    for (const a of ['placeholder', 'title', 'label']) { const v = el.getAttribute && el.getAttribute(a); if (v) { const o = window.tr(v); if (o !== v) el.setAttribute(a, o); } }
  };
  const walk = (root) => {
    if (root.nodeType === 3) return fixText(root);
    if (root.nodeType !== 1) return;
    if (/^(SCRIPT|STYLE|TEXTAREA|CODE|PRE)$/.test(root.tagName) && !root.closest('#log')) return;
    fixEl(root);
    const w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let n; while ((n = w.nextNode())) { if (n.nodeType === 3) { const p = n.parentElement; if (p && /^(SCRIPT|STYLE|TEXTAREA)$/.test(p.tagName)) continue; fixText(n); } else fixEl(n); }
  };
  const start = () => {
    document.documentElement.lang = 'en';
    walk(document.body);
    new MutationObserver((muts) => { for (const m of muts) { if (m.type === 'characterData') fixText(m.target); else if (m.type === 'attributes') fixEl(m.target); else m.addedNodes.forEach(walk); } })
      .observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['placeholder', 'title', 'label'] });
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
