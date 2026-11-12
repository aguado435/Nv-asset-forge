#!/usr/bin/env node
'use strict';
/*
 * NV Asset Forge — servidor local
 * Genera assets 2D y 3D para videojuegos con los modelos de NVIDIA Build
 * (LLM para el prompt, FLUX para imagen, FLUX Kontext para variaciones,
 * TRELLIS para 3D). El render, el post-procesado y la biblioteca son locales.
 *
 * Requisitos: Node.js 18 o superior. Sin dependencias npm.
 */
const http = require('http');
const fs = require('fs');
const fsp = fs.promises;
const path = require('path');
const crypto = require('crypto');
const os = require('os');
const { exec, execFile, spawn } = require('child_process');

const ROOT = __dirname;
const PUBLIC = path.join(ROOT, 'public');
const CONFIG_PATH = path.join(ROOT, 'config.json');
const PORT = parseInt(process.env.PORT || '7860', 10);
const HOST = process.env.HOST || '127.0.0.1';

if (typeof fetch !== 'function') {
  console.error('\n  Necesitas Node.js 18 o superior: https://nodejs.org\n');
  process.exit(1);
}

// ───────────────────────── Configuración ─────────────────────────
const DEFAULTS = {
  apiKey: '',
  llmProvider: 'nvidia', // nvidia | local (FreeLLMAPI u otro servidor compatible OpenAI)
  llmModel: 'meta/llama-3.3-70b-instruct',
  llmLocalUrl: 'http://localhost:31415/v1',
  llmLocalKey: '',
  llmLocalModel: 'auto',
  imageModel: 'flux.1-dev',
  customImagePath: '',
  model3d: 'trellis',
  custom3dPath: '',
  backend2d: 'cloud', // cloud | local (NIM en tu PC)
  backend3d: 'cloud',
  local2dUrl: 'http://localhost:8000',
  local3dUrl: 'http://localhost:8001',
  libraryPath: path.join(ROOT, 'library'),
  project: 'MiJuego',
  blenderPath: '', // vacío = autodetectar
  codeModel: 'qwen/qwen3-coder-480b-a35b-instruct',
};

function readConfigFile() {
  try { return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8')); } catch { return {}; }
}
function loadConfig() {
  const cfg = { ...DEFAULTS, ...readConfigFile() };
  if (!cfg.apiKey && process.env.NVIDIA_API_KEY) cfg.apiKey = process.env.NVIDIA_API_KEY;
  if (!path.isAbsolute(cfg.libraryPath)) cfg.libraryPath = path.resolve(ROOT, cfg.libraryPath);
  return cfg;
}
function saveConfig(patch) {
  const cur = { ...DEFAULTS, ...readConfigFile() };
  for (const k of Object.keys(DEFAULTS)) {
    if (patch[k] === undefined || patch[k] === null) continue;
    const v = String(patch[k]).trim();
    if ((k === 'apiKey' || k === 'llmLocalKey') && v.includes('•')) continue; // máscara: no tocar
    if (k === 'apiKey' && v === '') continue;
    cur[k] = v;
  }
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cur, null, 2));
  return cur;
}
function publicConfig(cfg) {
  const k = cfg.apiKey || '';
  return {
    ...cfg,
    apiKey: k ? k.slice(0, 6) + '••••••••' + k.slice(-4) : '',
    llmLocalKey: cfg.llmLocalKey ? '••••••••' + cfg.llmLocalKey.slice(-4) : '',
    hasKey: !!k,
    imageModels: { ...Object.fromEntries(Object.entries(IMAGE_MODELS).map(([k, m]) => [k, m.label])), ...(cfg.customImagePath ? { custom: 'Personalizado: ' + cfg.customImagePath } : {}) },
    models3d: { ...Object.fromEntries(Object.entries(MODELS_3D).map(([k, m]) => [k, m.label])), ...(cfg.custom3dPath ? { custom: 'Personalizado: ' + cfg.custom3dPath } : {}) },
    llmSuggestions: LLM_SUGGESTIONS,
    types: Object.fromEntries(Object.entries(TYPES).map(([id, t]) => [id, { label: t.label, kind: t.kind, group: t.group, size: t.size, hint: t.hint }])),
    styles: Object.fromEntries(Object.entries(STYLES).map(([id, s]) => [id, s.label])),
  };
}

// ───────────────────────── NVIDIA Build ─────────────────────────
const NV = {
  chat: process.env.NV_CHAT_URL || 'https://integrate.api.nvidia.com/v1/chat/completions',
  genai: process.env.NV_GENAI_URL || 'https://ai.api.nvidia.com/v1/genai/',
  status: process.env.NV_STATUS_URL || 'https://api.nvcf.nvidia.com/v2/nvcf/pexec/status/',
  assets: process.env.NV_ASSETS_URL || 'https://api.nvcf.nvidia.com/v2/nvcf/assets',
};
// Modelos de imagen. Cada usuario elige el que quiera, y puede añadir cualquier otro
// de build.nvidia.com escribiendo su ruta (Ajustes → modelo personalizado).
const IMAGE_MODELS = {
  'flux.1-dev': { label: 'FLUX.1 dev · máxima calidad', path: 'black-forest-labs/flux.1-dev', mode: 'base', steps: { draft: 20, normal: 30, high: 50 }, cfg: 3.5 },
  'flux.1-schnell': { label: 'FLUX.1 schnell · muy rápido', path: 'black-forest-labs/flux.1-schnell', mode: 'base', steps: { draft: 4, normal: 4, high: 4 }, cfg: null },
  'sd3.5-large': { label: 'Stable Diffusion 3.5 Large', path: 'stabilityai/stable-diffusion-3.5-large', mode: 'base', steps: { draft: 20, normal: 40, high: 50 }, cfg: 4.5 },
  'qwen-image': { label: 'Qwen-Image · bueno con texto', path: 'qwen/qwen-image', steps: { draft: 20, normal: 30, high: 50 }, cfg: 4 },
};
const MODELS_3D = {
  trellis: { label: 'Microsoft TRELLIS', path: 'microsoft/trellis' },
};
const LLM_SUGGESTIONS = ['meta/llama-3.3-70b-instruct', 'nvidia/llama-3.3-nemotron-super-49b-v1.5', 'qwen/qwen3-coder-480b-a35b-instruct', 'deepseek-ai/deepseek-v3.1', 'mistralai/mistral-medium-3-instruct', 'openai/gpt-oss-120b'];
function imageModel(cfg, key) {
  key = key || cfg.imageModel;
  if (key === 'custom' && cfg.customImagePath) return { label: 'Personalizado', path: cfg.customImagePath.replace(/^https?:\/\/[^/]+\/v1\/genai\//, ''), steps: { draft: 20, normal: 30, high: 40 }, cfg: null };
  return IMAGE_MODELS[key] || IMAGE_MODELS['flux.1-dev'];
}
function model3D(cfg, key) {
  key = key || cfg.model3d;
  if (key === 'custom' && cfg.custom3dPath) return { label: 'Personalizado', path: cfg.custom3dPath.replace(/^https?:\/\/[^/]+\/v1\/genai\//, '') };
  return MODELS_3D[key] || MODELS_3D.trellis;
}
const KONTEXT = { path: 'black-forest-labs/flux.1-kontext-dev', steps: { draft: 20, normal: 30, high: 40 }, cfg: 3.5 };
const TRELLIS = { steps: { draft: 12, normal: 25, high: 40 } };
const SIZES = ['1024x1024', '832x1216', '1216x832', '768x1344', '1344x768'];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const trimUrl = (u) => String(u || '').replace(/\/+$/, '');
const short = (s, n = 160) => (String(s).length > n ? String(s).slice(0, n) + '…' : String(s));
const randSeed = () => crypto.randomInt(1, 2147483647);

async function nvRequest(url, payload, { apiKey, headers = {}, local = false } = {}) {
  const h = { 'Content-Type': 'application/json', Accept: 'application/json', ...headers };
  if (!local) {
    if (!apiKey) throw new Error('Falta la API key de NVIDIA. Ponla en Ajustes (consíguela gratis en build.nvidia.com).');
    h.Authorization = `Bearer ${apiKey}`;
  }
  let res;
  try {
    res = await fetch(url, { method: 'POST', headers: h, body: JSON.stringify(payload) });
  } catch (e) {
    throw new Error(local ? `No se pudo conectar con el NIM local en ${url}. ¿Está el contenedor arrancado?` : `Sin conexión con NVIDIA (${e.cause?.code || e.message})`);
  }
  const started = Date.now();
  while (res.status === 202) { // cola asíncrona de NVCF
    const reqId = res.headers.get('nvcf-reqid');
    if (!reqId) break;
    if (Date.now() - started > 10 * 60e3) throw new Error('NVIDIA tardó más de 10 minutos. Prueba otra vez.');
    await sleep(2000);
    res = await fetch(NV.status + reqId, { headers: { Authorization: `Bearer ${apiKey}`, Accept: 'application/json' } });
  }
  const text = await res.text();
  if (!res.ok) {
    let msg = text;
    try { const j = JSON.parse(text); msg = j.detail || j.title || j.error?.message || j.message || text; if (typeof msg !== 'string') msg = JSON.stringify(msg); } catch {}
    const hint = res.status === 401 || res.status === 403 ? ' (revisa tu API key)' : res.status === 429 ? ' (límite de peticiones; espera un poco)' : res.status >= 500 ? ' (el servicio de NVIDIA falla ahora mismo; reintenta o usa NIM local)' : '';
    const err = new Error(`NVIDIA ${res.status}${hint}: ${short(msg, 300)}`);
    err.status = res.status;
    throw err;
  }
  try { return JSON.parse(text); } catch { throw new Error('Respuesta inesperada de NVIDIA: ' + short(text, 200)); }
}

function firstArtifact(j) {
  const a = (j.artifacts && j.artifacts[0]) || (j.data && j.data[0]) || null;
  if (!a) throw new Error('NVIDIA no devolvió resultado: ' + short(JSON.stringify(j), 300));
  if (a.finishReason && /FILTER|BLOCK/i.test(a.finishReason)) throw new Error('Bloqueado por el filtro de contenido de NVIDIA. Reformula el prompt.');
  const b64 = a.base64 || a.b64_json || a.image;
  if (!b64) throw new Error('El resultado no trae datos.');
  return { buf: Buffer.from(String(b64).replace(/^data:[^,]+,/, ''), 'base64'), seed: a.seed };
}

// Sube una imagen a NVCF Assets para usarla como entrada en la nube.
async function uploadNvcfAsset(buf, apiKey, contentType = 'image/png') {
  const description = 'nv-asset-forge-input';
  const r = await fetch(NV.assets, {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ contentType, description }),
  });
  if (!r.ok) throw new Error(`No se pudo subir la imagen a NVIDIA (${r.status}): ${short(await r.text(), 200)}`);
  const { uploadUrl, assetId } = await r.json();
  const put = await fetch(uploadUrl, { method: 'PUT', headers: { 'Content-Type': contentType, 'x-amz-meta-nvcf-asset-description': description }, body: buf });
  if (!put.ok) throw new Error(`Fallo al subir la imagen (${put.status})`);
  return assetId;
}
async function imageInput(buf, local, apiKey) {
  if (local) return { value: 'data:image/png;base64,' + buf.toString('base64'), headers: {} };
  const id = await uploadNvcfAsset(buf, apiKey);
  return { value: `data:image/png;asset_id,${id}`, headers: { 'NVCF-INPUT-ASSET-REFERENCES': id, 'NVCF-FUNCTION-ASSET-IDS': id } };
}

async function genImage(cfg, { prompt, width, height, quality, seed, model }) {
  const local = cfg.backend2d === 'local';
  const m = imageModel(cfg, model);
  const payload = { prompt, width, height, seed, steps: m.steps[quality] || m.steps.normal };
  if (m.mode) payload.mode = m.mode;
  if (m.cfg != null) payload.cfg_scale = m.cfg;
  const url = local ? trimUrl(cfg.local2dUrl) + '/v1/infer' : NV.genai + m.path;
  try {
    return firstArtifact(await nvRequest(url, payload, { apiKey: cfg.apiKey, local }));
  } catch (e) {
    if (e.status !== 422 && e.status !== 400) {
      if (e.status === 404) e.message += ` · ¿Existe el modelo “${m.path}” en build.nvidia.com?`;
      throw e;
    }
    // el modelo no acepta algún parámetro → reintento con lo mínimo (y prompt recortado)
    const min = { prompt: prompt.slice(0, 600), width, height, seed };
    try { return firstArtifact(await nvRequest(url, min, { apiKey: cfg.apiKey, local })); }
    catch { return firstArtifact(await nvRequest(url, { prompt: prompt.slice(0, 300), seed }, { apiKey: cfg.apiKey, local })); }
  }
}

async function editImage(cfg, { prompt, imageBuf, quality, seed }) {
  const local = cfg.backend2d === 'local';
  const inp = await imageInput(imageBuf, local, cfg.apiKey);
  const payload = { prompt, image: inp.value, aspect_ratio: 'match_input_image', steps: KONTEXT.steps[quality] || 30, cfg_scale: KONTEXT.cfg, seed };
  const url = local ? trimUrl(cfg.local2dUrl) + '/v1/infer' : NV.genai + KONTEXT.path;
  return firstArtifact(await nvRequest(url, payload, { apiKey: cfg.apiKey, local, headers: inp.headers }));
}

async function gen3D(cfg, { mode, prompt, imageBuf, quality, seed, model }) {
  const local = cfg.backend3d === 'local';
  const st = TRELLIS.steps[quality] || 25;
  const payload = { mode, seed, ss_sampling_steps: st, slat_sampling_steps: st, ss_cfg_scale: 7.5, slat_cfg_scale: 3 };
  let headers = {};
  if (mode === 'text') payload.prompt = String(prompt).slice(0, 77);
  else { const inp = await imageInput(imageBuf, local, cfg.apiKey); payload.image = inp.value; headers = inp.headers; }
  const url = local ? trimUrl(cfg.local3dUrl) + '/v1/infer' : NV.genai + model3D(cfg, model).path;
  return firstArtifact(await nvRequest(url, payload, { apiKey: cfg.apiKey, local, headers }));
}

async function chatOnce(cfg, messages, max_tokens, nvModel) {
  const body = { messages, temperature: 0.35, top_p: 0.9, max_tokens, stream: false };
  if (cfg.llmProvider === 'local') {
    const headers = cfg.llmLocalKey ? { Authorization: `Bearer ${cfg.llmLocalKey}` } : {};
    try {
      return await nvRequest(trimUrl(cfg.llmLocalUrl) + '/chat/completions', { ...body, model: cfg.llmLocalModel || 'auto' }, { local: true, headers });
    } catch (e) {
      if (!cfg.apiKey) throw new Error(`LLM local (${cfg.llmLocalUrl}): ${e.message}`);
      // si el router local no responde, se usa el LLM de NVIDIA
    }
  }
  try {
    return await nvRequest(NV.chat, { ...body, model: nvModel || cfg.llmModel }, { apiKey: cfg.apiKey });
  } catch (e) {
    if (nvModel && nvModel !== cfg.llmModel && [400, 404, 422].includes(e.status)) // modelo no disponible → el LLM general
      return nvRequest(NV.chat, { ...body, model: cfg.llmModel }, { apiKey: cfg.apiKey });
    throw e;
  }
}
const llmLabel = (cfg) => (cfg.llmProvider === 'local' ? `LLM local (${cfg.llmLocalModel || 'auto'})` : cfg.llmModel);

async function llmJSON(cfg, system, user) {
  const j = await chatOnce(cfg, [{ role: 'system', content: system }, { role: 'user', content: user }], 900);
  let txt = j.choices?.[0]?.message?.content || '';
  txt = txt.replace(/<think>[\s\S]*?<\/think>/g, '');
  const s = txt.indexOf('{'), e = txt.lastIndexOf('}');
  if (s < 0 || e < s) throw new Error('el LLM no devolvió JSON');
  return JSON.parse(txt.slice(s, e + 1));
}

// ───────────────────────── Dirección de arte ─────────────────────────
const WHITE_BG = 'isolated on a plain solid pure white background, no ground shadow, no text, no watermark, no frame';
const TYPES = {
  '2d-character': { kind: '2d', group: '2D', label: 'Personaje (sprite)', size: '832x1216', bg: 'white', hint: 'Cuerpo entero, pose neutra, fondo limpio listo para recortar.',
    guide: `Single full-body game character, entire body visible from head to feet with margin, centered, neutral idle pose, three-quarter front view, clean readable silhouette, consistent proportions, ${WHITE_BG}.` },
  '2d-item': { kind: '2d', group: '2D', label: 'Objeto / arma / prop', size: '1024x1024', bg: 'white', hint: 'Un único objeto centrado y completo.',
    guide: `Single game item or prop, centered, the whole object visible with margin, three-quarter view, clean silhouette, clearly defined materials, ${WHITE_BG}.` },
  '2d-icon': { kind: '2d', group: '2D', label: 'Icono UI / inventario', size: '1024x1024', bg: 'white', hint: 'Silueta legible a tamaño pequeño.',
    guide: `Single game UI icon, bold silhouette readable at 64px, centered, slight rim light, high contrast, simple shapes, ${WHITE_BG}.` },
  '2d-texture': { kind: '2d', group: '2D', label: 'Textura tileable', size: '1024x1024', bg: 'none', hint: 'Material repetible (suelo, pared, roca…).',
    guide: 'Seamless tileable texture, flat orthographic top-down view, even diffuse lighting, no perspective, no directional cast shadows, no vignette, uniform detail density from edge to edge, fills the entire frame, no objects cut off, no text.' },
  '2d-environment': { kind: '2d', group: '2D', label: 'Fondo / escenario', size: '1344x768', bg: 'none', hint: 'Fondos, parallax, escenarios.',
    guide: 'Wide game background environment art, clear depth layers (foreground, midground, background), readable play space, strong composition, atmospheric perspective, no characters, no UI, no text.' },
  '2d-ui': { kind: '2d', group: '2D', label: 'Elemento de UI', size: '1216x832', bg: 'white', hint: 'Botones, paneles, marcos, barras.',
    guide: `Game UI element (button, panel, frame or bar), front orthographic view, centered, crisp clean edges, consistent bevel and lighting, no text labels, ${WHITE_BG}.` },
  '2d-vfx': { kind: '2d', group: '2D', label: 'Efecto VFX', size: '1024x1024', bg: 'black', hint: 'Magia, explosiones, energía (fondo negro para blending aditivo).',
    guide: 'Single game visual effect sprite (magic, explosion, energy or particles), centered, glowing, vivid emissive colors, isolated on a plain solid pure black background, no environment, no text.' },
  '2d-concept': { kind: '2d', group: '2D', label: 'Concept art', size: '1344x768', bg: 'none', hint: 'Exploración visual para el equipo de arte.',
    guide: 'Professional game concept art, clear design language, strong shape language, cohesive color palette, polished presentation, no text.' },
  '3d-image': { kind: '3d', group: '3D', label: 'Modelo 3D (concept → 3D) ★', size: '1024x1024', bg: 'white', hint: 'Mejor calidad: genera un concept con FLUX y lo reconstruye en 3D con TRELLIS.',
    guide: 'Single object or character designed for 3D reconstruction, entire subject fully visible and centered, three-quarter front view from slightly above, neutral soft studio lighting, no dramatic shadows, plain solid pure white background, no ground, no text, clean shapes, clearly defined materials and colors.' },
  '3d-text': { kind: '3d', group: '3D', label: 'Modelo 3D (texto → 3D)', size: '1024x1024', bg: 'none', hint: 'Directo con TRELLIS, más rápido.',
    guide: 'Single 3D game-ready object.' },
};
const STYLES = {
  auto: { label: 'Automático', p: '' },
  pixel: { label: 'Pixel art 16-bit', p: '16-bit pixel art, crisp pixels, limited color palette, clean dark outlines' },
  handpainted: { label: 'Stylized hand-painted', p: 'stylized hand-painted game art, painterly brushwork, vibrant saturated colors, exaggerated proportions' },
  cartoon: { label: 'Cartoon / cel-shading', p: 'cartoon cel-shaded style, bold clean outlines, flat vibrant colors' },
  anime: { label: 'Anime', p: 'anime style, clean line art, cel shading' },
  realistic: { label: 'Realista PBR', p: 'photorealistic, physically based materials, high detail, AAA game asset' },
  lowpoly: { label: 'Low poly', p: 'low poly style, flat shaded facets, simple geometric shapes' },
  voxel: { label: 'Voxel', p: 'voxel art, built from small cubes' },
  darkfantasy: { label: 'Dark fantasy', p: 'dark fantasy, gritty, muted desaturated palette, dramatic' },
  scifi: { label: 'Sci-fi', p: 'sci-fi, futuristic hard surface design, emissive details' },
  vector: { label: 'Vector flat', p: 'flat vector art, clean geometric shapes, minimal gradients' },
};

const ENHANCE_SYS = `You are a senior game art director and prompt engineer for the FLUX.1 image model and the TRELLIS text/image-to-3D model.
Turn the user's request (it may be in Spanish or any language) into production-ready prompts for ONE game asset.
Return ONLY a JSON object, no markdown, with keys:
"name": short English snake_case asset name, 1-4 words;
"image_prompt": English prompt for FLUX, 45-90 words, starting with the subject, then style, then framing/background/lighting rules. Concrete nouns, shapes, materials, colors. Never mention resolution numbers or camera brands;
"trellis_prompt": English, MAXIMUM 70 characters, a single object with concrete shape, material and color words, no background words;
"tags": array of 3-6 lowercase English tags.
Strictly respect the asset framing rules and the art style given. Keep any detail the user asked for. Do not add text, logos, watermarks or brand names.`;

function slugName(s) {
  return String(s || 'asset').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 40) || 'asset';
}
function fallbackPlan(prompt, category, style, bible = '') {
  const T = TYPES[category], S = STYLES[style] || STYLES.auto;
  return {
    name: slugName(prompt.split(/\s+/).slice(0, 4).join(' ')),
    image_prompt: [prompt, S.p, bible, T.guide].filter(Boolean).join(', '),
    trellis_prompt: [prompt, S.p.split(',')[0]].filter(Boolean).join(', ').slice(0, 77),
    tags: [category.replace(/^\dd-/, ''), style].filter((x) => x && x !== 'auto'),
    source: 'plantilla',
  };
}
async function enhancePrompt(cfg, prompt, category, style, bible = '') {
  const T = TYPES[category], S = STYLES[style] || STYLES.auto;
  const user = `Asset type: ${T.label}\nFraming rules (mandatory): ${T.guide}\nArt style: ${S.p || (bible ? 'follow the project art bible' : 'choose the most fitting professional game art style for the request')}\n${bible ? `Project art bible (mandatory, every asset of this game must share it): ${bible}\n` : ''}User request: ${prompt}`;
  const j = await llmJSON(cfg, ENHANCE_SYS, user);
  if (!j.image_prompt) throw new Error('JSON incompleto');
  return {
    name: slugName(j.name || prompt),
    image_prompt: String(j.image_prompt),
    trellis_prompt: String(j.trellis_prompt || prompt).slice(0, 77),
    tags: Array.isArray(j.tags) ? j.tags.slice(0, 6).map(String) : [],
    source: llmLabel(cfg),
  };
}

// ───────────────────────── Biblioteca local ─────────────────────────
const safeName = (s) => String(s || '').replace(/[<>:"/\\|?*\x00-\x1f]/g, '').replace(/\s+/g, ' ').trim().slice(0, 60);
const TRASH = '_papelera';

function urlFor(cfg, dir) {
  return '/files/' + path.relative(cfg.libraryPath, dir).split(path.sep).map(encodeURIComponent).join('/') + '/';
}
async function readAsset(cfg, dir) {
  try {
    const meta = JSON.parse(await fsp.readFile(path.join(dir, 'meta.json'), 'utf8'));
    const files = (await fsp.readdir(dir)).filter((f) => f !== 'meta.json').sort();
    return { ...meta, files, url: urlFor(cfg, dir), dir };
  } catch { return null; }
}
async function listAssets(cfg) {
  const lib = cfg.libraryPath, out = [];
  let projects = [];
  try { projects = await fsp.readdir(lib, { withFileTypes: true }); } catch { return out; }
  for (const p of projects) {
    if (!p.isDirectory() || p.name === TRASH) continue;
    for (const kind of ['2d', '3d']) {
      let dirs = [];
      try { dirs = await fsp.readdir(path.join(lib, p.name, kind), { withFileTypes: true }); } catch { continue; }
      for (const d of dirs) {
        if (!d.isDirectory()) continue;
        const a = await readAsset(cfg, path.join(lib, p.name, kind, d.name));
        if (a) out.push(a);
      }
    }
  }
  return out.sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
}
async function findAsset(cfg, id) {
  return (await listAssets(cfg)).find((a) => a.id === id) || null;
}
async function createAsset(cfg, meta, files) {
  const id = Date.now().toString(36) + crypto.randomBytes(2).toString('hex');
  const project = safeName(meta.project || cfg.project) || 'MiJuego';
  const dir = path.join(cfg.libraryPath, project, meta.kind, `${slugName(meta.name)}_${id}`);
  await fsp.mkdir(dir, { recursive: true });
  for (const [name, buf] of Object.entries(files)) await fsp.writeFile(path.join(dir, name), buf);
  const full = { id, ...meta, project, createdAt: new Date().toISOString() };
  await fsp.writeFile(path.join(dir, 'meta.json'), JSON.stringify(full, null, 2));
  return readAsset(cfg, dir);
}

// ───────────────────────── Trabajos ─────────────────────────
const jobs = new Map();
function newJob() {
  const id = crypto.randomBytes(6).toString('hex');
  const job = { id, status: 'running', log: [], assets: [], error: null, created: Date.now() };
  jobs.set(id, job);
  for (const [k, j] of jobs) if (Date.now() - j.created > 3 * 3600e3) jobs.delete(k);
  return job;
}
const clampInt = (v, lo, hi, d) => { const n = parseInt(v, 10); return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : d; };

async function runJob(job, o) {
  const cfg = loadConfig();
  const log = (m) => { job.log.push(`${new Date().toLocaleTimeString('es-ES')}  ${m}`); console.log('  ' + m); };
  const quality = ['draft', 'normal', 'high'].includes(o.quality) ? o.quality : 'normal';
  const project = safeName(o.project || cfg.project) || 'MiJuego';
  try {
    if (o.action === 'edit') return await runEdit(cfg, job, o, log, quality, project);
    if (o.action === 'to3d') return await runTo3D(cfg, job, o, log, quality, project);

    const category = TYPES[o.category] ? o.category : '2d-item';
    const T = TYPES[category];
    const style = STYLES[o.style] ? o.style : 'auto';
    const prompt = String(o.prompt || '').trim();
    if (!prompt) throw new Error('Escribe qué asset quieres.');
    const size = SIZES.includes(o.size) ? o.size : T.size;
    const [w, h] = size.split('x').map(Number);
    const variants = clampInt(o.variants, 1, 4, 1);

    let plan = o.plan && o.plan.image_prompt ? { ...o.plan, name: slugName(o.plan.name || prompt), source: 'editado' } : null;
    if (!plan && o.enhance !== false) {
      log(`Optimizando prompt con ${llmLabel(cfg)}…`);
      try { plan = await enhancePrompt(cfg, prompt, category, style); log('Prompt optimizado.'); }
      catch (e) { log(`⚠ No se pudo optimizar (${short(e.message)}). Uso plantilla profesional local.`); }
    }
    if (!plan) plan = fallbackPlan(prompt, category, style);
    job.plan = plan;

    for (let v = 0; v < variants; v++) {
      const seed = o.seed && variants === 1 ? clampInt(o.seed, 1, 2147483646, randSeed()) : randSeed();
      const tag = variants > 1 ? ` [${v + 1}/${variants}]` : '';
      const meta = { name: plan.name, project, kind: T.kind, category, style, prompt, imagePrompt: plan.image_prompt, trellisPrompt: plan.trellis_prompt, tags: plan.tags || [], seed, quality, background: T.bg };
      if (T.kind === '2d') {
        log(`Generando imagen ${w}×${h} con ${cfg.imageModel} (${cfg.backend2d === 'local' ? 'NIM local' : 'NVIDIA cloud'})${tag}…`);
        const img = await genImage(cfg, { prompt: plan.image_prompt, width: w, height: h, quality, seed });
        const a = await createAsset(cfg, { ...meta, model: cfg.imageModel, width: w, height: h }, { 'source.png': img.buf });
        job.assets.push(a); log(`✔ Guardado ${a.name}${tag}`);
      } else if (category === '3d-text') {
        log(`Generando 3D con TRELLIS (texto): “${plan.trellis_prompt}”${tag}…`);
        const glb = await gen3D(cfg, { mode: 'text', prompt: plan.trellis_prompt, quality, seed });
        const a = await createAsset(cfg, { ...meta, model: 'trellis', trellisMode: 'text' }, { 'model.glb': glb.buf });
        job.assets.push(a); log(`✔ Guardado ${a.name}${tag}`);
      } else {
        log(`Generando concept 1024×1024 con ${cfg.imageModel}${tag}…`);
        const img = await genImage(cfg, { prompt: plan.image_prompt, width: 1024, height: 1024, quality, seed });
        const { glb, mode } = await imageTo3D(cfg, img.buf, plan.trellis_prompt, quality, seed, log);
        const a = await createAsset(cfg, { ...meta, model: 'trellis', trellisMode: mode, conceptModel: cfg.imageModel }, { 'model.glb': glb.buf, 'concept.png': img.buf });
        job.assets.push(a); log(`✔ Guardado ${a.name}${tag}`);
      }
    }
    job.status = 'done';
  } catch (e) {
    job.status = 'error'; job.error = e.message; log('✖ ' + e.message);
  }
}

async function imageTo3D(cfg, buf, fallbackPrompt, quality, seed, log) {
  try {
    log(`Reconstruyendo en 3D con TRELLIS (imagen, ${cfg.backend3d === 'local' ? 'NIM local' : 'NVIDIA cloud'})…`);
    return { glb: await gen3D(cfg, { mode: 'image', imageBuf: buf, quality, seed }), mode: 'image' };
  } catch (e) {
    if (!fallbackPrompt) throw e;
    log(`⚠ Imagen→3D no disponible (${short(e.message, 120)}). Paso a texto→3D.`);
    return { glb: await gen3D(cfg, { mode: 'text', prompt: fallbackPrompt, quality, seed }), mode: 'text' };
  }
}

async function sourceFile(cfg, o) {
  const src = await findAsset(cfg, o.assetId);
  if (!src) throw new Error('Asset de origen no encontrado.');
  const file = o.file && src.files.includes(o.file) ? o.file : src.files.includes('source.png') ? 'source.png' : src.files.includes('concept.png') ? 'concept.png' : src.files.find((f) => /\.png$/i.test(f) && f !== 'thumb.png');
  if (!file) throw new Error('El asset no tiene imagen.');
  return { src, file, buf: await fsp.readFile(path.join(src.dir, file)) };
}

async function runEdit(cfg, job, o, log, quality, project) {
  const { src, file, buf } = await sourceFile(cfg, o);
  let instruction = String(o.prompt || '').trim();
  if (!instruction) throw new Error('Escribe la variación que quieres.');
  if (o.enhance !== false) {
    try {
      log(`Traduciendo instrucción con ${llmLabel(cfg)}…`);
      const j = await llmJSON(cfg, 'You write image-editing instructions for FLUX.1 Kontext. Return ONLY JSON {"instruction": "...", "name": "snake_case_name"}. The instruction is concise English (max 40 words), says what to change and explicitly asks to keep the same character/object identity, art style, proportions, colors and background.', `Asset: ${src.name}\nRequest: ${instruction}`);
      if (j.instruction) instruction = String(j.instruction);
    } catch (e) { log(`⚠ Sin traducción (${short(e.message, 100)}), uso el texto tal cual.`); }
  }
  const seed = randSeed();
  log(`Creando variación con FLUX.1 Kontext a partir de ${file}…`);
  const img = await editImage(cfg, { prompt: instruction, imageBuf: buf, quality, seed });
  const a = await createAsset(cfg, { name: `${src.name}_var`, project: src.project || project, kind: '2d', category: src.category, style: src.style, prompt: o.prompt, imagePrompt: instruction, tags: src.tags || [], seed, quality, model: 'flux.1-kontext-dev', parent: src.id, background: src.background }, { 'source.png': img.buf });
  job.assets.push(a); log(`✔ Variación guardada ${a.name}`);
  job.status = 'done';
}

async function runTo3D(cfg, job, o, log, quality, project) {
  const { src, file, buf } = await sourceFile(cfg, o);
  const seed = randSeed();
  const fb = src.trellisPrompt || String(src.prompt || src.name).slice(0, 77);
  const { glb, mode } = await imageTo3D(cfg, buf, fb, quality, seed, log);
  const a = await createAsset(cfg, { name: `${src.name}_3d`, project: src.project || project, kind: '3d', category: '3d-image', style: src.style, prompt: src.prompt, imagePrompt: src.imagePrompt, trellisPrompt: fb, tags: src.tags || [], seed, quality, model: 'trellis', trellisMode: mode, parent: src.id }, { 'model.glb': glb.buf, 'concept.png': buf });
  job.assets.push(a); log(`✔ Modelo 3D guardado ${a.name} (desde ${file})`);
  job.status = 'done';
}

// ───────────────────────── HTTP ─────────────────────────
const MIME = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.glb': 'model/gltf-binary', '.gltf': 'model/gltf+json', '.ico': 'image/x-icon' };

function send(res, code, body, type = 'application/json') {
  const data = type === 'application/json' ? JSON.stringify(body) : body;
  res.writeHead(code, { 'Content-Type': type, 'Cache-Control': 'no-store' });
  res.end(data);
}
function readBody(req, limit = 80 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    const chunks = []; let n = 0;
    req.on('data', (c) => { n += c.length; if (n > limit) { reject(new Error('Petición demasiado grande')); req.destroy(); } else chunks.push(c); });
    req.on('end', () => { try { resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {}); } catch { reject(new Error('JSON inválido')); } });
    req.on('error', reject);
  });
}
async function serveFile(res, base, rel) {
  const file = path.resolve(base, '.' + path.sep + rel);
  if (!file.startsWith(path.resolve(base) + path.sep) && file !== path.resolve(base)) return send(res, 403, { error: 'prohibido' });
  try {
    const st = await fsp.stat(file);
    if (!st.isFile()) throw 0;
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream', 'Content-Length': st.size, 'Cache-Control': 'no-cache' });
    fs.createReadStream(file).pipe(res);
  } catch { send(res, 404, { error: 'no encontrado' }); }
}
function openPath(p) {
  const cmd = process.platform === 'win32' ? `start "" "${p}"` : process.platform === 'darwin' ? `open "${p}"` : `xdg-open "${p}"`;
  exec(cmd, { shell: process.platform === 'win32' ? 'cmd.exe' : undefined }, () => {});
}
const strip = (a) => { if (!a) return a; const { dir, ...rest } = a; return rest; };

const server = http.createServer(async (req, res) => {
  const u = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const p = decodeURIComponent(u.pathname);
  try {
    // Seguridad: solo peticiones desde esta misma app
    if (req.method !== 'GET') {
      const origin = req.headers.origin;
      if (origin && !/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(origin)) return send(res, 403, { error: 'origen no permitido' });
    }
    if (p === '/api/config' && req.method === 'GET') return send(res, 200, publicConfig(loadConfig()));
    if (p === '/api/config' && req.method === 'POST') { saveConfig(await readBody(req)); return send(res, 200, publicConfig(loadConfig())); }
    if (p === '/api/test' && req.method === 'POST') {
      const cfg = loadConfig();
      const out = {};
      if (cfg.llmProvider === 'local') {
        try { await chatOnce({ ...cfg, apiKey: '' }, [{ role: 'user', content: 'Reply with: OK' }], 5); out.local = 'ok'; } catch (e) { out.local = e.message; }
      }
      if (cfg.apiKey) {
        try { const r = await fetch('https://integrate.api.nvidia.com/v1/models', { headers: { Authorization: `Bearer ${cfg.apiKey}` } }); out.nvidia = r.ok ? 'ok' : `HTTP ${r.status}`; } catch (e) { out.nvidia = e.message; }
      } else out.nvidia = 'sin API key';
      return send(res, 200, out);
    }
    if (p === '/api/enhance' && req.method === 'POST') {
      const b = await readBody(req); const cfg = loadConfig();
      const category = TYPES[b.category] ? b.category : '2d-item';
      try { return send(res, 200, await enhancePrompt(cfg, String(b.prompt || ''), category, b.style)); }
      catch (e) { return send(res, 200, { ...fallbackPlan(String(b.prompt || ''), category, b.style), warning: e.message }); }
    }
    if (p === '/api/generate' && req.method === 'POST') {
      const b = await readBody(req); const job = newJob();
      runJob(job, b); return send(res, 200, { jobId: job.id });
    }
    let m;
    if ((m = p.match(/^\/api\/jobs\/([a-f0-9]+)$/))) {
      const j = jobs.get(m[1]); if (!j) return send(res, 404, { error: 'trabajo no encontrado' });
      return send(res, 200, { ...j, assets: j.assets.map(strip) });
    }
    if (p === '/api/assets' && req.method === 'GET') return send(res, 200, (await listAssets(loadConfig())).map(strip));
    if ((m = p.match(/^\/api\/assets\/([\w]+)$/))) {
      const cfg = loadConfig(); const a = await findAsset(cfg, m[1]);
      if (!a) return send(res, 404, { error: 'asset no encontrado' });
      if (req.method === 'GET') return send(res, 200, strip(a));
      if (req.method === 'DELETE') {
        const dest = path.join(cfg.libraryPath, TRASH, path.basename(a.dir));
        await fsp.mkdir(path.dirname(dest), { recursive: true });
        await fsp.rename(a.dir, dest);
        return send(res, 200, { ok: true });
      }
      if (req.method === 'PATCH') {
        const b = await readBody(req); const meta = JSON.parse(await fsp.readFile(path.join(a.dir, 'meta.json'), 'utf8'));
        if (b.name) meta.name = slugName(b.name);
        if (Array.isArray(b.tags)) meta.tags = b.tags.map(String).slice(0, 12);
        if (b.notes !== undefined) meta.notes = String(b.notes).slice(0, 2000);
        await fsp.writeFile(path.join(a.dir, 'meta.json'), JSON.stringify(meta, null, 2));
        return send(res, 200, strip(await readAsset(cfg, a.dir)));
      }
    }
    if ((m = p.match(/^\/api\/assets\/([\w]+)\/file$/)) && req.method === 'POST') {
      const cfg = loadConfig(); const a = await findAsset(cfg, m[1]);
      if (!a) return send(res, 404, { error: 'asset no encontrado' });
      const b = await readBody(req);
      const name = String(b.name || '').replace(/[^\w\-.]/g, '_');
      if (!/^[\w\-.]{1,80}\.(png|webp|jpg|glb|json)$/i.test(name) || name === 'meta.json') return send(res, 400, { error: 'nombre de archivo no válido' });
      const buf = Buffer.from(String(b.data || '').replace(/^data:[^,]+,/, ''), 'base64');
      await fsp.writeFile(path.join(a.dir, name), buf);
      return send(res, 200, strip(await readAsset(cfg, a.dir)));
    }
    if (p === '/api/open' && req.method === 'POST') {
      const cfg = loadConfig(); const b = await readBody(req);
      let target = cfg.libraryPath;
      if (b.id) { const a = await findAsset(cfg, b.id); if (a) target = a.dir; }
      await fsp.mkdir(target, { recursive: true });
      openPath(target); return send(res, 200, { ok: true, path: target });
    }
    if (p.startsWith('/files/')) return serveFile(res, loadConfig().libraryPath, p.slice('/files/'.length));
    if (req.method === 'GET') return serveFile(res, PUBLIC, p === '/' ? 'index.html' : p.slice(1));
    send(res, 404, { error: 'no encontrado' });
  } catch (e) {
    console.error(e);
    send(res, 500, { error: e.message });
  }
});

server.on('error', (e) => {
  if (e.code === 'EADDRINUSE') {
    console.log(`\n  El puerto ${PORT} ya está en uso (¿ya está abierta la app?). Abriendo el navegador…\n`);
    if (!process.env.NO_OPEN) openPath(`http://localhost:${PORT}`);
    setTimeout(() => process.exit(0), 1500);
  } else { console.error(e); process.exit(1); }
});
server.listen(PORT, HOST, () => {
  const cfg = loadConfig();
  fs.mkdirSync(cfg.libraryPath, { recursive: true });
  console.log(`\n  ▲ NV Asset Forge listo →  http://localhost:${PORT}`);
  console.log(`    Biblioteca: ${cfg.libraryPath}`);
  console.log(`    API key: ${cfg.apiKey ? 'configurada' : 'FALTA (ponla en Ajustes)'}\n    Cierra esta ventana para detener la app.\n`);
  if (!process.env.NO_OPEN) openPath(`http://localhost:${PORT}`);
});
