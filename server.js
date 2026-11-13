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
  llmModel: 'nvidia/nemotron-3.5-lightning-30b-a3b',
  llmLocalUrl: 'http://localhost:31415/v1',
  llmLocalKey: '',
  llmLocalModel: 'auto',
  imageModel: 'flux.2-klein-4b',
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
  codeModel: 'minimaxai/minimax-m3.1-flash',
  visionModel: 'nvidia/nemotron-3.5-super-vl-120b-a12b',
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
    anims: Object.fromEntries(Object.entries(ANIMS).map(([k, a]) => [k, `${a.label} · ${a.frames.length} fot.`])),
    types: Object.fromEntries(Object.entries(TYPES).map(([id, t]) => [id, { label: t.label, kind: t.kind, group: t.group, size: t.size, hint: t.hint }])),
    styles: Object.fromEntries(Object.entries(STYLES).map(([id, s]) => [id, s.label])),
    pixelStyles: Object.keys(STYLES).filter((k) => STYLES[k].px),
    presets: PRESETS,
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
  'flux.2-klein-4b': { label: 'FLUX.2 klein · rápido y nítido (recomendado)', path: 'black-forest-labs/flux.2-klein-4b', steps: { draft: 4, normal: 4, high: 4 }, cfg: null, maxPrompt: 800 },
  'flux.1-dev': { label: 'FLUX.1 dev · más pasos (a veces saturado)', path: 'black-forest-labs/flux.1-dev', mode: 'base', steps: { draft: 20, normal: 30, high: 50 }, cfg: 3.5 },
  'flux.1-schnell': { label: 'FLUX.1 schnell', path: 'black-forest-labs/flux.1-schnell', mode: 'base', steps: { draft: 4, normal: 4, high: 4 }, cfg: null },
};
const MODELS_3D = {
  trellis: { label: 'Microsoft TRELLIS', path: 'microsoft/trellis' },
};
const LLM_SUGGESTIONS = ['nvidia/nemotron-3.5-lightning-30b-a3b', 'minimaxai/minimax-m3.1-flash', 'mistralai/mistral-large-4-1t-a52b', 'z-ai/glm-5.3-flash', 'deepseek-ai/deepseek-v4.1-flash', 'openai/gpt-oss-20b'];
function imageModel(cfg, key) {
  key = key || cfg.imageModel;
  if (key === 'custom' && cfg.customImagePath) return { label: 'Personalizado', path: cfg.customImagePath.replace(/^https?:\/\/[^/]+\/v1\/genai\//, ''), steps: { draft: 20, normal: 30, high: 40 }, cfg: null };
  return IMAGE_MODELS[key] || IMAGE_MODELS['flux.2-klein-4b'];
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
    res = await fetch(url, { method: 'POST', headers: h, body: JSON.stringify(payload), signal: AbortSignal.timeout(local ? 900e3 : 200e3) });
  } catch (e) {
    const err = new Error(local ? `No se pudo conectar con el NIM local en ${url}. ¿Está el contenedor arrancado?` : `Sin conexión con NVIDIA (${e.name === 'TimeoutError' ? 'sin respuesta en 200 s' : e.cause?.code || e.message})`);
    err.network = true; throw err;
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
const CLOUD_NO_INPUT = 'La nube gratuita de NVIDIA solo acepta sus imágenes de ejemplo como entrada; para usar imágenes propias (variaciones exactas, referencia de estilo, imagen→3D) hace falta NIM local';
function mimeOf(buf) {
  if (buf[0] === 0xff && buf[1] === 0xd8) return 'image/jpeg';
  if (buf.slice(0, 4).toString('hex') === '89504e47') return 'image/png';
  if (buf.slice(8, 12).toString() === 'WEBP') return 'image/webp';
  return 'image/png';
}
const extOf = (buf) => ({ 'image/jpeg': '.jpg', 'image/webp': '.webp' }[mimeOf(buf)] || '.png');
async function imageInput(buf, local, apiKey) {
  if (local) return { value: `data:${mimeOf(buf)};base64,` + buf.toString('base64'), headers: {} };
  if (!process.env.NVF_CLOUD_IMAGE_INPUT) { const e = new Error(CLOUD_NO_INPUT); e.cloudInput = true; throw e; }
  const id = await uploadNvcfAsset(buf, apiKey, mimeOf(buf));
  return { value: `data:${mimeOf(buf)};asset_id,${id}`, headers: { 'NVCF-INPUT-ASSET-REFERENCES': id, 'NVCF-FUNCTION-ASSET-IDS': id } };
}

function fitPrompt(p, max) { // recorta por frases sin cortar palabras a la mitad
  if (p.length <= max) return p;
  const parts = p.split(/(?<=[.,;])\s+/); let out = '';
  for (const x of parts) { if ((out + ' ' + x).trim().length > max) break; out = (out + ' ' + x).trim(); }
  return out || p.slice(0, max);
}
// El filtro de NVIDIA da falsos positivos con palabras inocentes (p. ej. "sage green"): se limpian y se reintenta solo
const FILTER_SWAPS = [[/\bsage[ -]?green\b/gi, 'soft olive green'], [/\bsage\b/gi, 'herb'], [/\(#?[0-9a-f]{6}\)/gi, ''], [/#[0-9a-f]{6}\b/gi, ''],
  [/\b(blood|bloody|gore|gory|corpse|naked|nude|kill(ing)?|skin)\b/gi, ''], [/\s{2,}/g, ' ']];
function filterSafe(p) { let o = p; for (const [re, to] of FILTER_SWAPS) o = o.replace(re, to); return o.replace(/\s+([,.])/g, '$1').trim(); }
async function genImage(cfg, opts) {
  try { return await genImageRaw(cfg, opts); } catch (e) {
    if (!/filtro de contenido/.test(e.message)) throw e;
    const safe = filterSafe(opts.prompt);
    try { return await genImageRaw(cfg, { ...opts, prompt: safe, seed: (opts.seed || 1) + 7 }); } catch (e2) {
      if (!/filtro de contenido/.test(e2.message)) throw e2;
      // último recurso: tema + encuadre (primera y última frase), sin la biblia de estilo
      const parts = safe.split(/(?<=\.)\s+/);
      return genImageRaw(cfg, { ...opts, prompt: [parts[0], parts.length > 2 ? parts[1] : '', parts[parts.length - 1]].join(' '), seed: (opts.seed || 1) + 13 });
    }
  }
}
async function genImageRaw(cfg, { prompt, width, height, quality, seed, model }) {
  const local = cfg.backend2d === 'local';
  const m = imageModel(cfg, model);
  const payload = { prompt, width, height, seed, steps: m.steps[quality] || m.steps.normal };
  if (m.mode) payload.mode = m.mode;
  if (m.cfg != null) payload.cfg_scale = m.cfg;
  const url = local ? trimUrl(cfg.local2dUrl) + '/v1/infer' : NV.genai + m.path;
  if (!local && m.maxPrompt && prompt.length > m.maxPrompt) payload.prompt = fitPrompt(prompt, m.maxPrompt);
  try {
    try { return firstArtifact(await nvRequest(url, payload, { apiKey: cfg.apiKey, local })); }
    catch (e) { if (!e.network || local) throw e; return firstArtifact(await nvRequest(url, payload, { apiKey: cfg.apiKey, local })); } // un reintento si la cola se cuelga
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
  const nvBody = { ...body, chat_template_kwargs: { enable_thinking: false, thinking: false } };
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
    return await nvRequest(NV.chat, { ...nvBody, model: nvModel || cfg.llmModel }, { apiKey: cfg.apiKey });
  } catch (e) {
    if (nvModel && nvModel !== cfg.llmModel && [400, 404, 422].includes(e.status)) // modelo no disponible → el LLM general
      return nvRequest(NV.chat, { ...nvBody, model: cfg.llmModel }, { apiKey: cfg.apiKey });
    throw e;
  }
}
const llmLabel = (cfg) => (cfg.llmProvider === 'local' ? `LLM local (${cfg.llmLocalModel || 'auto'})` : cfg.llmModel);

async function llmJSON(cfg, system, user, max_tokens = 2000, nvModel) {
  const j = await chatOnce(cfg, [{ role: 'system', content: system }, { role: 'user', content: user }], max_tokens, nvModel);
  let txt = j.choices?.[0]?.message?.content || '';
  txt = txt.replace(/<think>[\s\S]*?<\/think>/g, '');
  const s = txt.indexOf('{'), e = txt.lastIndexOf('}');
  if (s < 0 || e < s) throw new Error('el LLM no devolvió JSON');
  try { return JSON.parse(txt.slice(s, e + 1)); } catch { return JSON.parse(tolerantJSON(txt.slice(s, e + 1))); }
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
  '3d-blender': { kind: '3d', group: '3D', label: 'Modelo 3D pro en Blender ★', size: '1024x1024', bg: 'none', hint: 'Un LLM modela el asset en Blender con texturas FLUX y un director de arte (IA de visión) lo revisa. Topología limpia, FBX/GLB/.blend. Requiere Blender.',
    guide: 'Procedural Blender model.' },
  '3d-image': { kind: '3d', group: '3D', label: 'Modelo 3D IA (concept → TRELLIS)', size: '1024x1024', bg: 'white', hint: 'Mejor calidad: genera un concept con FLUX y lo reconstruye en 3D con TRELLIS.',
    guide: 'Single object or character designed for 3D reconstruction, entire subject fully visible and centered, three-quarter front view from slightly above, neutral soft studio lighting, no dramatic shadows, plain solid pure white background, no ground, no text, clean shapes, clearly defined materials and colors.' },
  '3d-text': { kind: '3d', group: '3D', label: 'Modelo 3D IA (texto → TRELLIS)', size: '1024x1024', bg: 'none', hint: 'Directo con TRELLIS, más rápido.',
    guide: 'Single 3D game-ready object.' },
};
const STYLES = {
  auto: { label: 'Automático', p: '' },
  pixel: { label: 'Pixel art 16-bit', p: '16-bit pixel art, crisp pixels, limited color palette, clean dark outlines', px: 1 },
  hd2d: { label: '★ HD-2D (pixel + luz cinematográfica)', px: 1, p: 'high-resolution 32-bit pixel art sprite, crisp readable pixel clusters, soft painterly sub-shading, warm cinematic key light with cool rim light, rich jewel-tone palette, clean dark outline, premium JRPG quality' },
  cozy: { label: '★ Cozy pixel (granja / vida)', px: 1, p: 'cozy pixel art, soft rounded chunky shapes, warm pastel palette, gentle shading, friendly proportions, clean dark brown outline, charming farming-sim feel' },
  gothicpx: { label: '★ Metroidvania gótico (pixel)', px: 1, p: 'detailed 32-bit pixel art, moody gothic palette of deep blues, crimson and bone white, strong silhouette, high-contrast rim lighting, ornate details, clean outline' },
  soulslike: { label: '★ Fantasía sombría pintada', p: 'grim dark fantasy painted game art, desaturated earthy palette with one ember accent, heavy chiaroscuro lighting, worn weathered materials, gothic ornament, painterly texture' },
  mobile: { label: '★ Casual móvil brillante', p: 'polished casual mobile game art, chunky rounded shapes, bright saturated candy colors, soft gradients and glossy highlights, thick clean outline, playful and readable' },
  isometric: { label: '★ Isométrico estratégico', p: 'isometric game art at a consistent 30 degree angle, clean readable forms, soft ambient occlusion, crisp edges, consistent top-left lighting, strategy game quality' },
  inked: { label: '★ Cómic entintado', p: 'hand-inked comic game art, bold confident brush lines, flat colors with halftone shading, dynamic silhouette, limited bold palette' },
  storybook: { label: '★ Cuento acuarela', p: 'storybook watercolor game art, soft washes with ink linework, gentle paper texture, warm muted palette, whimsical shapes' },
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

const ENHANCE_SYS = `You are the art director of a top-tier game studio and an expert prompt engineer for the FLUX.1 image model and the TRELLIS image/text-to-3D model.
Turn the user's request (it may be in Spanish or any language) into a production-ready brief for ONE game asset at professional studio quality.
Return ONLY a JSON object, no markdown, with keys:
"name": short English snake_case asset name, 1-4 words;
"image_prompt": English prompt for FLUX, 70-120 words. Order: (1) the subject with a strong, specific design idea: era/culture, silhouette, proportions, 2-3 signature details, materials and wear; (2) the art style and rendering technique; (3) professional quality cues: clean readable silhouette, clear shape language (big/medium/small forms), strong value contrast, harmonious limited color palette with one accent color, consistent single key light from the upper left with soft fill and subtle rim light, crisp edges, polished final production asset, high detail where it matters; (4) the mandatory framing/background rules. Use concrete nouns and adjectives, no vague words like "beautiful" or "epic", no resolution numbers, no camera brands, no artist names;
"trellis_prompt": English, MAXIMUM 70 characters, one object with concrete shape, material and color words, no background words;
"tags": array of 3-6 lowercase English tags.
Strictly respect the asset framing rules and the art style given. Keep every detail the user asked for. No text, letters, logos, watermarks, UI or brand names in the image.`;

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
async function favoriteExamples(cfg, project, category, n = 4) {
  // "Aprender de tus favoritos": los prompts de los assets marcados con ★ guían a los nuevos (few-shot, sin reentrenar)
  const favs = (await listAssets(cfg)).filter((a) => a.favorite && a.project === project && a.imagePrompt);
  favs.sort((a, b) => (b.category === category) - (a.category === category));
  return favs.slice(0, n).map((a) => ({ category: a.category, prompt: String(a.imagePrompt).slice(0, 700) }));
}
async function enhancePrompt(cfg, prompt, category, style, bible = '', favs = []) {
  const T = TYPES[category], S = STYLES[style] || STYLES.auto;
  const ex = favs.length ? `Approved prompts from this project (the art director starred these results; match their art style, rendering vocabulary, palette and structure exactly, but not their subjects):\n${favs.map((f, i) => `${i + 1}. [${f.category}] ${f.prompt}`).join('\n')}\n` : '';
  const user = `Asset type: ${T.label}\nFraming rules (mandatory): ${T.guide}\nArt style: ${S.p || (bible ? 'follow the project art bible' : 'choose the most fitting professional game art style for the request')}\n${bible ? `Project art bible (mandatory, every asset of this game must share it): ${bible}\n` : ''}${ex}User request: ${prompt}`;
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

// ───────────────────────── Packs coherentes ─────────────────────────
const PACK_CATS = ['2d-character', '2d-item', '2d-icon', '2d-texture', '2d-environment', '2d-vfx', '2d-ui'];
const PACK_SYS = `You are the art director of a top-tier indie game studio. From one request you plan a COHERENT ASSET PACK: every asset must look like it comes from the same game.
Return ONLY JSON, no markdown:
{"pack_name": short English snake_case name,
 "style_bible": English, 35-55 words (max 320 characters), the shared visual rules: rendering technique, line/outline treatment, shading model, light direction, palette (name 5-7 colors with plain words, no hex codes), level of detail, texture treatment. This exact text is appended to every asset prompt, so make it precise and reusable,
 "assets": [{"name": short English snake_case, "category": one of ${PACK_CATS.join(', ')}, "subject": English, 25-50 words, only WHAT the asset is: design, silhouette, signature details, materials (no style words, no background words)}]}
Rules: cover what a developer needs to start building that game (characters, enemies, props, pickups, icons, ground/wall textures, one background, a VFX), no duplicates, concrete and varied silhouettes, everything fits the same world and color story. No text, letters or logos anywhere.`;

async function runPack(cfg, job, o, log, quality, project) {
  const prompt = String(o.prompt || '').trim();
  if (!prompt) throw new Error('Describe el pack (juego, mundo, tema…).');
  const count = clampInt(o.count, 3, 24, 10);
  const style = STYLES[o.style] ? o.style : 'auto';
  const proj = await loadProject(cfg, project);
  const bible = String(proj.bible || '').trim();
  const only = Array.isArray(o.categories) ? o.categories.filter((c) => PACK_CATS.includes(c)) : [];
  const favs = await favoriteExamples(cfg, project, '', 3);
  log(`Planificando un pack de ${count} assets con ${llmLabel(cfg)}${favs.length ? ` (aprendiendo de ${favs.length} favorito(s) ★)` : ''}…`);
  let plan;
  try {
    plan = await llmJSON(cfg, PACK_SYS, `Request: ${prompt}\nNumber of assets: exactly ${count}\n${only.length ? `Allowed categories: ${only.join(', ')}\n` : ''}${STYLES[style].p ? `Mandatory art style: ${STYLES[style].p}\n` : ''}${bible ? `Existing project art bible (keep it, refine it): ${bible}\n` : ''}${favs.length ? `Starred example prompts of this project (derive the style bible from them):\n${favs.map((f) => '- ' + f.prompt).join('\n')}\n` : ''}`, 5000);
  } catch (e) { throw new Error('El LLM no pudo planificar el pack: ' + short(e.message)); }
  const items = (Array.isArray(plan.assets) ? plan.assets : []).filter((a) => a && a.subject).slice(0, count)
    .map((a) => ({ name: slugName(a.name || a.subject), category: PACK_CATS.includes(a.category) ? a.category : (only[0] || '2d-item'), subject: String(a.subject).slice(0, 600) }));
  if (!items.length) throw new Error('El plan del pack llegó vacío.');
  const styleBible = [STYLES[style].p, String(plan.style_bible || bible || '').slice(0, 900)].filter(Boolean).join(', ');
  const packName = slugName(plan.pack_name || prompt);
  const packId = Date.now().toString(36);
  job.pack = { id: packId, name: packName, styleBible, items };
  log(`Pack “${packName}”: ${items.map((i) => i.name).join(', ')}`);
  log(`Biblia de estilo: ${styleBible}`);
  if (o.saveBible !== false && !bible) { await saveProject(cfg, project, { bible: styleBible }); log('Guardada como guía de estilo del proyecto.'); }
  const imgKey = o.imageModel || cfg.imageModel;
  const baseSeed = randSeed();
  let ok = 0;
  for (let i = 0; i < items.length; i++) {
    const it = items[i], T = TYPES[it.category];
    const [w, h] = T.size.split('x').map(Number);
    // FLUX.2 klein admite 800 caracteres: tema + encuadre + fondo siempre caben; la biblia de estilo ocupa el resto
    const frame = T.guide.split(',').slice(0, 2).join(',');
    const bgRule = T.bg === 'white' ? 'isolated on a plain pure white background, no shadow, no text' : T.bg === 'black' ? 'on a plain pure black background, no text' : 'no text, no UI';
    const head = `${fitPrompt(it.subject, 260)}. ${frame}. `, tail = `. ${bgRule}.`;
    const image_prompt = head + fitPrompt(styleBible, 790 - head.length - tail.length) + tail;
    job.progress = i / items.length;
    log(`[${i + 1}/${items.length}] ${it.name} (${T.label})…`);
    try {
      const img = await genImage(cfg, { prompt: image_prompt, width: w, height: h, quality, seed: baseSeed + i, model: imgKey });
      const sz = pngSize(img.buf) || {};
      const a = await createAsset(cfg, { name: it.name, project, kind: '2d', category: it.category, style, prompt: it.subject, imagePrompt: image_prompt,
        tags: ['pack:' + packName, it.category.replace('2d-', '')], seed: baseSeed + i, quality, background: T.bg, model: imgKey,
        width: sz.w || w, height: sz.h || h, pack: { id: packId, name: packName, index: i } }, { 'source.png': img.buf });
      job.assets.push(a); ok++;
    } catch (e) { log(`⚠ ${it.name}: ${short(e.message)}`); }
  }
  log(`✔ Pack listo: ${ok}/${items.length} assets. Búscalo en la biblioteca con “pack:${packName}”.`);
  job.status = ok ? 'done' : 'error'; if (!ok) job.error = 'No se generó ningún asset del pack.';
}

// ───────────────────────── Escenas 3D por prompt (el LLM compone con las piezas del editor) ─────────────────────────
const SCENE_TYPES = {
  cube: '1×1×1 m box, origin at its base', plane: '4×4 m flat plane', cylinder: 'Ø1 m, 1 m tall', cone: 'Ø1 m, 1 m tall', sphere: 'Ø1 m', torus: 'ring Ø1 m', capsule: '1.5 m tall',
  wall: 'wall 4 m wide (local X) × 3 m tall × 0.3 m thick, origin bottom-center', wallwin: 'same wall with an arched window', doorway: 'same wall with an arched door',
  floor: '4×4 m floor slab 0.2 m thick (put walls on top at y=0.2)', roof: 'gable roof 4.6 m wide (local X) × 4.4 m deep (local Z) × 1.8 m tall; for a 4×4 house rotate 90° in Y and place at y=3.2',
  house: 'MACRO: complete 4×4 m cottage (floor, walls with door facing local +Z and windows, gable roof). Optional "color" = walls, "roof" = roof color. Use r[1] to turn the door towards the path', tower: 'MACRO: 3-story stone watchtower 4×4 m with cone roof', pier: 'MACRO: wooden pier 2 m wide, extends along local -Z; s[2] = length multiplier (1 = 8 m)',
  stairs: '2 m wide stairs rising 1.5 m along local +Z over 2.4 m', column: '3.1 m column', arch: '3.2 m wide × 3.2 m tall stone arch', fence: '4 m fence along local X', crate: '0.8 m crate', barrel: 'barrel 1 m tall',
  tree: 'deciduous tree ~4 m', pine: 'pine tree ~4 m', rock: 'rock ~1.2 m (scale freely)', bush: 'bush ~1 m', water: '6×6 m water plane (scale to make ponds/rivers)', plight: 'warm point light (lanterns, fires, windows at night)',
};
const SCENE_SYS = `You are a level designer composing a small 3D scene for a game from modular pieces, like assembling a diorama in Blender.
Units are meters, Y is up, the ground is y=0, X is right, Z is towards the camera. Rotation is in DEGREES around Y unless needed.
Available piece types (use ONLY these): ${Object.entries(SCENE_TYPES).map(([k, v]) => `${k}: ${v}`).join('; ')}.
Return ONLY JSON: {"name": short snake_case, "tod": "day"|"dawn"|"dusk"|"night", "ground": "grass"|"grid", "objs": [{"type": one of the types, "name": short label, "p": [x,y,z], "r": [rx,ry,rz] degrees, "s": [sx,sy,sz], "color": "#rrggbb" optional}]}.
Prefer the MACRO pieces (house, tower, pier) for buildings: one house object = one complete cottage. Space houses at least 7 m apart, never put buildings on water; a pier starts on land and goes over a water plane.\nRules: build structures that actually connect (walls meet at corners on a 4 m grid, roofs sit on walls, floors under houses), keep paths walkable, use 15-70 objects, vary scale and rotation of nature pieces so it does not look repeated, use believable colors, add point lights at doors/lamps when it is dusk or night. Keep everything within about 40×40 m around the origin.
NEVER assemble buildings from floor/wall/roof pieces: always one "house" or "tower" object per building (walls are only for town walls, ruins or fences). Water planes: scale at most 3 (18 m), place them beside the village, not under it.
Example for "two cottages by a pond at night":
{"name":"pond_cottages","tod":"night","ground":"grass","objs":[{"type":"house","name":"cottage_a","p":[-5,0,0],"r":[0,20,0],"s":[1,1,1],"color":"#d9cbb0","roof":"#7a3326"},{"type":"house","name":"cottage_b","p":[5,0,-1],"r":[0,-15,0],"s":[1,1,1],"color":"#cfc2a8","roof":"#4a5a6a"},{"type":"water","name":"pond","p":[0,0,9],"r":[0,0,0],"s":[1.4,1,1],"color":"#2f6f8f"},{"type":"plight","name":"door_lamp_a","p":[-4.3,2.2,2.6],"r":[0,0,0],"s":[1,1,1],"color":"#ffb866"},{"type":"plight","name":"door_lamp_b","p":[5.5,2.2,1.6],"r":[0,0,0],"s":[1,1,1],"color":"#ffb866"},{"type":"pine","name":"pine","p":[-11,0,-6],"r":[0,40,0],"s":[1.2,1.3,1.2]},{"type":"tree","name":"oak","p":[10,0,-7],"r":[0,0,0],"s":[1.1,1.1,1.1]},{"type":"rock","name":"rock","p":[3,0,6],"r":[0,70,0],"s":[0.8,0.6,0.8]},{"type":"bush","name":"bush","p":[-2,0,4],"r":[0,0,0],"s":[1,1,1]}]}`;
function expandMacro(o) { // casas, torres y muelles → piezas del kit con su transformación
  const ry = (o.r[1] * Math.PI) / 180, c = Math.cos(ry), sn = Math.sin(ry);
  const at = (x, y, z) => [o.p[0] + x * c + z * sn, o.p[1] + y, o.p[2] - x * sn + z * c];
  const P = (type, x, y, z, rotY = 0, extra = {}) => ({ type, name: `${o.name || o.type} · ${type}`, p: at(x, y, z), r: [0, o.r[1] + rotY, 0], s: [1, 1, 1], ...extra });
  const wc = o.color, rc = o.roof;
  if (o.type === 'house') return [P('floor', 0, 0, 0), P('doorway', 0, 0.2, 2, 0, { color: wc }), P('wall', 0, 0.2, -2, 0, { color: wc }), P('wallwin', 2, 0.2, 0, 90, { color: wc }), P('wallwin', -2, 0.2, 0, 90, { color: wc }), P('roof', 0, 3.2, 0, 90, { color: rc })];
  if (o.type === 'tower') { const out = []; for (let k = 0; k < 3; k++) { out.push(P(k === 1 ? 'wallwin' : k === 0 ? 'doorway' : 'wall', 0, k * 3, 2, 0, { color: wc || '#8f8a80' }), P(k === 2 ? 'wallwin' : 'wall', 0, k * 3, -2, 0, { color: wc || '#8f8a80' }), P('wallwin', 2, k * 3, 0, 90, { color: wc || '#8f8a80' }), P('wall', -2, k * 3, 0, 90, { color: wc || '#8f8a80' })); } out.push({ type: 'cone', name: `${o.name || 'tower'} · roof`, p: at(0, 9, 0), r: [0, 0, 0], s: [5.2, 3.2, 5.2], color: rc || '#6b2f2a' }); return out; }
  if (o.type === 'pier') { const n = Math.max(1, Math.round(2 * (o.s[2] || 1))); const out = []; for (let k = 0; k < n; k++) { out.push({ type: 'cube', name: `${o.name || 'pier'} · deck`, p: at(0, 0.6, -2 - k * 4), r: [0, o.r[1], 0], s: [2, 0.15, 4], color: '#8a6440' }); for (const sx of [-0.9, 0.9]) out.push({ type: 'cylinder', name: `${o.name || 'pier'} · post`, p: at(sx, -0.5, -4 - k * 4), r: [0, 0, 0], s: [0.25, 1.4, 0.25], color: '#5c4029' }); } return out; }
  return [o];
}
async function designScene(cfg, prompt, current) {
  const user = `${current && current.length ? `Current scene objects (modify/extend them as requested, return the FULL list):\n${JSON.stringify(current).slice(0, 6000)}\n\n` : ''}Request (may be in any language): ${prompt}`;
  const j = await llmJSON(cfg, SCENE_SYS, user, 6000);
  const raw = (Array.isArray(j.objs) ? j.objs : []).filter((o) => o && SCENE_TYPES[o.type]).slice(0, 200).map((o) => {
    const v3 = (a, d) => (Array.isArray(a) && a.length === 3 ? a.map((x) => (Number.isFinite(+x) ? Math.max(-500, Math.min(500, +x)) : 0)) : d);
    const col = (c) => (/^#[0-9a-f]{6}$/i.test(c || '') ? c : undefined);
    const sc = v3(o.s, [1, 1, 1]).map((x) => x || 1); if (o.type === 'water') { sc[0] = Math.min(3, Math.abs(sc[0])); sc[2] = Math.min(3, Math.abs(sc[2])); sc[1] = 1; }
    return { type: o.type, name: String(o.name || o.type).slice(0, 40), p: v3(o.p, [0, 0, 0]), r: v3(o.r, [0, 0, 0]), s: sc, color: col(o.color), roof: col(o.roof) };
  });
  // maquetación: edificios sin solaparse (mín. 7 m entre centros) y agua bajo los muelles
  const blds = raw.filter((o) => o.type === 'house' || o.type === 'tower');
  for (let it = 0; it < 40; it++) {
    let moved = false;
    for (let i = 0; i < blds.length; i++) for (let k = i + 1; k < blds.length; k++) {
      const A = blds[i].p, B = blds[k].p; let dx = B[0] - A[0], dz = B[2] - A[2]; let d = Math.hypot(dx, dz);
      if (d < 7) { if (d < 0.01) { dx = 1; dz = 0; d = 1; } const push = (7 - d) / 2 + 0.05; A[0] -= dx / d * push; A[2] -= dz / d * push; B[0] += dx / d * push; B[2] += dz / d * push; moved = true; }
    }
    if (!moved) break;
  }
  for (const w of raw.filter((x) => x.type === 'water')) { // los edificios no se construyen sobre el agua
    const pad = 2.5, hx = 3 * (w.s[0] || 1) + pad, hz = 3 * (w.s[2] || 1) + pad, ry = (w.r[1] * Math.PI) / 180, c = Math.cos(ry), sn = Math.sin(ry);
    for (const b of raw.filter((x) => !['water', 'pier', 'plight', 'plane'].includes(x.type))) {
      const dx = b.p[0] - w.p[0], dz = b.p[2] - w.p[2], lx = dx * c - dz * sn, lz = dx * sn + dz * c;
      if (Math.abs(lx) < hx && Math.abs(lz) < hz) {
        let nx = lx, nz = lz; if (hx - Math.abs(lx) < hz - Math.abs(lz)) nx = Math.sign(lx || 1) * (hx + 0.5); else nz = Math.sign(lz || 1) * (hz + 0.5);
        b.p[0] = w.p[0] + nx * c + nz * sn; b.p[2] = w.p[2] - nx * sn + nz * c;
      }
    }
  }
  for (const o of raw.filter((x) => x.type === 'pier')) {
    if (raw.some((w) => w.type === 'water' && Math.hypot(w.p[0] - o.p[0], w.p[2] - o.p[2]) < 12)) continue;
    const len = 8 * (o.s[2] || 1), ry = (o.r[1] * Math.PI) / 180;
    raw.push({ type: 'water', name: 'agua', p: [o.p[0] - Math.sin(ry) * len * 0.75, 0, o.p[2] - Math.cos(ry) * len * 0.75], r: [0, o.r[1], 0], s: [Math.max(3, len / 3), 1, Math.max(2, len / 3)] });
  }
  const objs = raw.flatMap(expandMacro).map((o) => ({ type: o.type, name: o.name, p: o.p.map((v) => +v.toFixed(3)), r: o.r.map((d) => +((d * Math.PI) / 180).toFixed(4)), s: o.s, color: o.color }));
  if (!objs.length) throw new Error('El LLM no devolvió piezas válidas.');
  return { name: slugName(j.name || prompt), tod: ['day', 'dawn', 'dusk', 'night'].includes(j.tod) ? j.tod : 'day', ground: j.ground === 'grid' ? 'grid' : 'grass', objs };
}

// ───────────────────────── Exportar a motor (ZIP sin dependencias) ─────────────────────────
const CRC_T = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
function crc32(buf) { let c = 0xffffffff; for (let i = 0; i < buf.length; i++) c = CRC_T[(c ^ buf[i]) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; }
function makeZip(entries) { // entries: [{name, data:Buffer}]
  const zlib = require('zlib');
  const local = [], central = []; let off = 0;
  const d = new Date(), dos = (((d.getFullYear() - 1980) << 9 | (d.getMonth() + 1) << 5 | d.getDate()) << 16 | d.getHours() << 11 | d.getMinutes() << 5 | (d.getSeconds() >> 1)) >>> 0;
  for (const { name, data } of entries) {
    const nm = Buffer.from(name, 'utf8'), crc = crc32(data);
    const comp = /\.(png|jpe?g|webp|glb|zip)$/i.test(name) ? null : zlib.deflateRawSync(data, { level: 9 });
    const method = comp && comp.length < data.length ? 8 : 0, body = method ? comp : data;
    const h = Buffer.alloc(30); h.writeUInt32LE(0x04034b50, 0); h.writeUInt16LE(20, 4); h.writeUInt16LE(0x0800, 6); h.writeUInt16LE(method, 8);
    h.writeUInt32LE(dos, 10); h.writeUInt32LE(crc, 14); h.writeUInt32LE(body.length, 18); h.writeUInt32LE(data.length, 22); h.writeUInt16LE(nm.length, 26);
    local.push(h, nm, body);
    const c = Buffer.alloc(46); c.writeUInt32LE(0x02014b50, 0); c.writeUInt16LE(20, 4); c.writeUInt16LE(20, 6); c.writeUInt16LE(0x0800, 8); c.writeUInt16LE(method, 10);
    c.writeUInt32LE(dos, 12); c.writeUInt32LE(crc, 16); c.writeUInt32LE(body.length, 20); c.writeUInt32LE(data.length, 24); c.writeUInt16LE(nm.length, 28); c.writeUInt32LE(off, 42);
    central.push(c, nm); off += 30 + nm.length + body.length;
  }
  const cd = Buffer.concat(central), e = Buffer.alloc(22);
  e.writeUInt32LE(0x06054b50, 0); e.writeUInt16LE(entries.length, 8); e.writeUInt16LE(entries.length, 10); e.writeUInt32LE(cd.length, 12); e.writeUInt32LE(off, 16);
  return Buffer.concat([...local, cd, e]);
}
const ENGINES = {
  godot: { root: 'nvforge', label: 'Godot 4' },
  unity: { root: 'Assets/NVForge', label: 'Unity' },
  generic: { root: 'nvforge_assets', label: 'Genérico' },
};
async function exportPack(cfg, ids, engine) {
  const E = ENGINES[engine] || ENGINES.generic;
  const all = await listAssets(cfg);
  const pick = ids && ids.length ? all.filter((a) => ids.includes(a.id)) : all.slice(0, 40);
  if (!pick.length) throw new Error('No hay assets que exportar.');
  const entries = [], manifest = { tool: 'NV Asset Forge', engine: E.label, exported: new Date().toISOString(), assets: [] };
  const used = new Set();
  for (const a of pick) {
    let folder = `${a.kind}/${a.category || a.kind}/${slugName(a.name)}`;
    for (let k = 2; used.has(folder); k++) folder = `${a.kind}/${a.category || a.kind}/${slugName(a.name)}_${k}`;
    used.add(folder);
    const files = a.files.filter((f) => !/^(thumb\.png|render_review.*|.*\.log|.*\.blend1)$/i.test(f) && !(engine !== 'generic' && /\.(py|blend)$/i.test(f)));
    for (const f of files) {
      const st = await fsp.stat(path.join(a.dir, f)); if (!st.isFile() || st.size > 200e6) continue;
      entries.push({ name: `${E.root}/${folder}/${f}`, data: await fsp.readFile(path.join(a.dir, f)) });
    }
    manifest.assets.push({ id: a.id, name: a.name, kind: a.kind, category: a.category, path: `${folder}/`, files, main: bestFile(a), tags: a.tags || [], prompt: a.prompt, seed: a.seed, model: a.model, pack: a.pack });
  }
  entries.push({ name: `${E.root}/manifest.json`, data: Buffer.from(JSON.stringify(manifest, null, 2)) });
  const pixel = pick.some((a) => a.style === 'pixel' || (a.tags || []).some((t) => /pixel/.test(t)));
  const readme = engine === 'godot'
    ? `# NV Asset Forge → Godot 4\n\nCopia la carpeta \`nvforge/\` dentro de tu proyecto (res://nvforge).\n\n- Los .glb se importan solos como escenas 3D.\n- Los tilesets incluyen un \`.tres\` (TileSet con terreno por esquinas) listo para un TileMapLayer.\n${pixel ? '- Pixel art: Proyecto → Ajustes → Rendering → Textures → Default Texture Filter = **Nearest**.\n' : ''}- \`manifest.json\` lista cada asset con su prompt y semilla para regenerarlo.\n`
    : engine === 'unity'
      ? `# NV Asset Forge → Unity\n\nDescomprime en la raíz del proyecto: todo queda en \`Assets/NVForge\`.\n\n- Los .fbx/.glb (glTFast) se importan como modelos.\n- Sprites: Texture Type = Sprite (2D and UI).${pixel ? ' Pixel art: Filter Mode = Point, Compression = None.' : ''}\n- \`manifest.json\` lista prompts y semillas.\n`
      : '# NV Asset Forge\n\nAssets exportados con su manifest.json (prompt, semilla, modelo).\n';
  entries.push({ name: `${E.root}/README.md`, data: Buffer.from(readme) });
  return { zip: makeZip(entries), count: pick.length, name: `nvforge_${engine}_${new Date().toISOString().slice(0, 10)}.zip` };
}

// ───────────────────────── Biblioteca local ─────────────────────────
const safeName = (s) => String(s || '').replace(/[<>:"/\\|?*\x00-\x1f]/g, '').replace(/\s+/g, ' ').trim().slice(0, 60);
// Recetas de estudio: prompts de partida probados (tema + tipo + estilo). El LLM los convierte en el brief final.
const PRESETS = [
  { g: 'Personajes', n: 'Héroe aventurero', c: '2d-character', s: 'hd2d', p: 'joven aventurero con capa corta, espada a la cintura, mochila de cuero y bufanda al viento, mirada decidida', pe: 'young adventurer with a short cape, sword at the hip, leather backpack and a scarf in the wind, determined look' },
  { g: 'Personajes', n: 'Maga elfa', c: '2d-character', s: 'hd2d', p: 'maga elfa con túnica verde bosque bordada en oro, bastón de madera viva con un cristal brillante, orejas largas, pelo plateado', pe: 'elf mage in a forest-green robe embroidered in gold, living-wood staff with a glowing crystal, long ears, silver hair' },
  { g: 'Personajes', n: 'Enano herrero', c: '2d-character', s: 'gothicpx', p: 'enano herrero robusto con barba trenzada, delantal de cuero chamuscado, martillo enorme al hombro', pe: 'sturdy dwarf blacksmith with a braided beard, scorched leather apron, huge hammer on the shoulder' },
  { g: 'Personajes', n: 'Caballero oscuro (jefe)', c: '2d-character', s: 'soulslike', p: 'caballero caído gigantesco con armadura negra agrietada, capa hecha jirones, espadón dentado, brasas saliendo de las grietas', pe: 'giant fallen knight in cracked black armor, tattered cape, serrated greatsword, embers glowing through the cracks' },
  { g: 'Personajes', n: 'Granjera cozy', c: '2d-character', s: 'cozy', p: 'granjera sonriente con sombrero de paja, peto vaquero, regadera en la mano y un pollito en el hombro', pe: 'smiling farmer girl with a straw hat, denim overalls, a watering can in hand and a chick on her shoulder' },
  { g: 'Enemigos', n: 'Slime', c: '2d-character', s: 'cozy', p: 'slime gelatinoso translúcido con ojitos grandes y una hoja pegada en la cabeza', pe: 'translucent jelly slime with big eyes and a leaf stuck on its head' },
  { g: 'Enemigos', n: 'Esqueleto guerrero', c: '2d-character', s: 'gothicpx', p: 'esqueleto guerrero con escudo redondo roto, casco oxidado y espada corta mellada', pe: 'skeleton warrior with a broken round shield, rusty helmet and a chipped short sword' },
  { g: 'Enemigos', n: 'Gólem de piedra', c: '2d-character', s: 'hd2d', p: 'gólem de piedra musgosa con runas azules brillantes en el pecho y cristales en los hombros', pe: 'mossy stone golem with glowing blue runes on the chest and crystals on the shoulders' },
  { g: 'Objetos', n: 'Cofre del tesoro', c: '2d-item', s: 'hd2d', p: 'cofre de madera reforzado con hierro y remaches de oro, entreabierto con monedas y gemas asomando', pe: 'iron-bound wooden chest with gold rivets, half open with coins and gems peeking out' },
  { g: 'Objetos', n: 'Poción de vida', c: '2d-item', s: 'pixel', p: 'frasco de cristal redondo con líquido rojo brillante, tapón de corcho y etiqueta de pergamino atada con cordel', pe: 'round glass flask with glowing red liquid, cork stopper and a parchment label tied with string' },
  { g: 'Objetos', n: 'Espada legendaria', c: '2d-item', s: 'hd2d', p: 'espada legendaria con hoja de plata grabada con runas, guarda en forma de alas y gema azul en el pomo', pe: 'legendary sword with a silver blade engraved with runes, wing-shaped guard and a blue gem in the pommel' },
  { g: 'Iconos', n: 'Iconos de habilidad', c: '2d-icon', s: 'soulslike', p: 'icono de habilidad: bola de fuego espiral naranja sobre fondo circular oscuro', pe: 'skill icon: orange spiral fireball on a dark circular background' },
  { g: 'Iconos', n: 'Moneda', c: '2d-icon', s: 'mobile', p: 'moneda de oro gruesa con una estrella grabada y brillo especular', pe: 'thick gold coin with an engraved star and a specular shine' },
  { g: 'Texturas', n: 'Hierba', c: '2d-texture', s: 'hd2d', p: 'césped corto denso con tréboles y pequeñas flores blancas dispersas', pe: 'dense short grass with clovers and small scattered white flowers' },
  { g: 'Texturas', n: 'Adoquines', c: '2d-texture', s: 'hd2d', p: 'adoquines de piedra gris irregulares con musgo entre las juntas', pe: 'irregular grey cobblestones with moss in the joints' },
  { g: 'Texturas', n: 'Tierra de camino', c: '2d-texture', s: 'hd2d', p: 'tierra de camino compacta con piedrecillas y huellas leves', pe: 'packed dirt path with small pebbles and faint footprints' },
  { g: 'Texturas', n: 'Arena de playa', c: '2d-texture', s: 'cozy', p: 'arena de playa fina con conchas pequeñas y ondas suaves', pe: 'fine beach sand with small shells and soft ripples' },
  { g: 'Fondos', n: 'Bosque encantado', c: '2d-environment', s: 'storybook', p: 'claro de bosque encantado con árboles enormes, rayos de luz, luciérnagas y un camino que se pierde al fondo', pe: 'enchanted forest clearing with huge trees, light rays, fireflies and a path fading into the distance' },
  { g: 'Fondos', n: 'Mazmorra', c: '2d-environment', s: 'gothicpx', p: 'pasillo de mazmorra con antorchas, cadenas colgando, charcos que reflejan la luz y una puerta de hierro al fondo', pe: 'dungeon corridor with torches, hanging chains, puddles reflecting the light and an iron door at the end' },
  { g: 'Fondos', n: 'Pueblo al atardecer', c: '2d-environment', s: 'hd2d', p: 'plaza de pueblo medieval al atardecer con faroles encendidos, fuente central y casas con entramado de madera', pe: 'medieval village square at dusk with lit lanterns, a central fountain and half-timbered houses' },
  { g: 'UI', n: 'Panel de diálogo', c: '2d-ui', s: 'hd2d', p: 'marco de caja de diálogo de madera oscura con esquinas de latón ornamentadas y pergamino interior', pe: 'dark wood dialogue box frame with ornate brass corners and parchment inside' },
  { g: 'UI', n: 'Barras de vida y maná', c: '2d-ui', s: 'gothicpx', p: 'marco ornamentado para barras de vida y maná con calavera central y bordes de hierro', pe: 'ornate frame for health and mana bars with a central skull and iron edges' },
  { g: 'VFX', n: 'Impacto mágico', c: '2d-vfx', s: 'hd2d', p: 'explosión de energía mágica azul y blanca con chispas y anillo de choque', pe: 'burst of blue and white magic energy with sparks and a shockwave ring' },
  { g: 'VFX', n: 'Curación', c: '2d-vfx', s: 'cozy', p: 'aura de curación verde con hojitas y destellos ascendiendo en espiral', pe: 'green healing aura with little leaves and sparkles rising in a spiral' },
  { g: '3D', n: 'Taberna medieval', c: '3d-blender', s: 'auto', p: 'taberna medieval de dos plantas con tejado de pizarra, chimenea de piedra, cartel colgante y barriles en la puerta', pe: 'two-story medieval tavern with slate roof, stone chimney, hanging sign and barrels at the door' },
  { g: '3D', n: 'Pozo de piedra', c: '3d-blender', s: 'auto', p: 'pozo de piedra con tejadillo de madera, cubo y manivela', pe: 'stone well with a small wooden roof, bucket and crank' },
];

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
  const job = { id, status: 'running', log: [], assets: [], error: null, created: Date.now(), progress: null, label: '', kind: '' };
  jobs.set(id, job);
  for (const [k, j] of jobs) if (Date.now() - j.created > 3 * 3600e3) jobs.delete(k);
  return job;
}
const clampInt = (v, lo, hi, d) => { const n = parseInt(v, 10); return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : d; };

// ───────────────────────── Colecciones (estilo por proyecto) ─────────────────────────
const projectFile = (cfg, project) => path.join(cfg.libraryPath, safeName(project) || 'MiJuego', 'project.json');
async function loadProject(cfg, project) {
  try { return JSON.parse(await fsp.readFile(projectFile(cfg, project), 'utf8')); } catch { return {}; }
}
async function saveProject(cfg, project, patch) {
  const cur = await loadProject(cfg, project);
  if (patch.bible !== undefined) cur.bible = String(patch.bible).slice(0, 1500);
  if (patch.refAssetId !== undefined) cur.refAssetId = patch.refAssetId ? String(patch.refAssetId) : '';
  if (patch.refFile !== undefined) cur.refFile = String(patch.refFile || '');
  const f = projectFile(cfg, project);
  await fsp.mkdir(path.dirname(f), { recursive: true });
  await fsp.writeFile(f, JSON.stringify(cur, null, 2));
  return cur;
}
async function referenceBuf(cfg, proj) {
  if (!proj.refAssetId) return null;
  const a = await findAsset(cfg, proj.refAssetId);
  if (!a) return null;
  const f = proj.refFile && a.files.includes(proj.refFile) ? proj.refFile : a.files.includes('source.png') ? 'source.png' : a.files.includes('concept.png') ? 'concept.png' : null;
  return f ? fsp.readFile(path.join(a.dir, f)) : null;
}

// ───────────────────────── Animaciones 2D ─────────────────────────
const ANIMS = {
  idle: { label: 'Idle (respirar)', fps: 4, frames: ['standing in a relaxed neutral idle pose', 'idle pose breathing in: chest slightly raised, shoulders slightly lifted, arms slightly moved'] },
  walk: { label: 'Andar', fps: 8, frames: ['walking, left leg forward touching the ground, right arm swinging forward', 'walking passing pose, legs together under the body, upright', 'walking, right leg forward touching the ground, left arm swinging forward', 'walking passing pose, legs together under the body, body slightly lower'] },
  run: { label: 'Correr', fps: 10, frames: ['running, left knee raised high, right arm forward, leaning forward', 'running, both feet off the ground mid-stride, leaning forward', 'running, right knee raised high, left arm forward, leaning forward', 'running, landing on the left foot, leaning forward'] },
  attack: { label: 'Atacar', fps: 10, frames: ['preparing to attack, weapon or fist pulled far back, weight on the back foot', 'attacking, weapon or fist swinging forward with force', 'attack fully extended, weapon or arm at the end of the swing', 'recovering after the attack, returning to a guard stance'] },
  jump: { label: 'Saltar', fps: 8, frames: ['crouching down preparing to jump, knees bent', 'jumping high in the air, legs tucked, arms raised', 'landing, knees bent absorbing the impact'] },
  hurt: { label: 'Recibir daño', fps: 8, frames: ['recoiling from a hit, body bent backwards, pained expression', 'staggering back, off balance'] },
  cast: { label: 'Lanzar hechizo', fps: 8, frames: ['raising both hands to channel magic', 'casting a spell, hands thrust forward with a glowing magic effect', 'after casting, magic fading, hands lowering'] },
  death: { label: 'Morir', fps: 6, frames: ['falling backwards, losing balance', 'collapsed on the ground lying on its back, defeated'] },
};
const FRAME_RULES = 'Keep exactly the same character: same face, outfit, colors, art style, proportions, size in the frame and camera angle. Full body visible, plain solid pure white background, no shadow, no text. Change only the pose to:';

async function runAnimate(cfg, job, o, log, quality, project) {
  const { src, file, buf } = await sourceFile(cfg, o);
  const A = ANIMS[o.anim] || ANIMS.walk;
  const key = ANIMS[o.anim] ? o.anim : 'walk';
  const seed = randSeed();
  const files = {};
  for (let i = 0; i < A.frames.length; i++) {
    log(`Fotograma ${i + 1}/${A.frames.length} de “${A.label}” con FLUX Kontext…`);
    const img = await editImage(cfg, { prompt: `${FRAME_RULES} ${A.frames[i]}.`, imageBuf: buf, quality, seed });
    files[`frame_${String(i + 1).padStart(2, '0')}.png`] = img.buf;
  }
  const a = await createAsset(cfg, { name: `${src.name}_${key}`, project: src.project || project, kind: '2d', category: '2d-anim', anim: key, fps: A.fps, frames: A.frames.length, style: src.style, prompt: src.prompt, tags: [...(src.tags || []), 'anim', key], seed, quality, model: 'flux.1-kontext-dev', parent: src.id, parentFile: file, background: 'white' }, files);
  job.assets.push(a);
  log(`✔ ${A.frames.length} fotogramas guardados. Pulsa “Montar sprite sheet” para quitar fondos y alinearlos.`);
  job.status = 'done';
}

// ───────────────────────── Blender (render local) ─────────────────────────
const BLENDER_SCRIPT = path.join(ROOT, 'blender', 'nvf_blender.py');
let blenderCache = null;
function verKey(name) { return (String(name).match(/\d+/g) || []).map((n) => n.padStart(4, '0')).join('.'); }
function blenderCandidates(cfg) {
  const c = [];
  if (cfg.blenderPath) c.push(cfg.blenderPath);
  if (process.env.BLENDER_PATH) c.push(process.env.BLENDER_PATH);
  const scan = (dir, rx, sub) => {
    try { fs.readdirSync(dir).filter((d) => rx.test(d)).sort((a, b) => verKey(b).localeCompare(verKey(a))).forEach((d) => c.push(path.join(dir, d, sub))); } catch {}
  };
  if (process.platform === 'win32') {
    for (const base of [process.env.ProgramFiles, process.env['ProgramFiles(x86)'], 'C:\\Program Files']) if (base) scan(path.join(base, 'Blender Foundation'), /^Blender/i, 'blender.exe');
    c.push('C:\\Program Files (x86)\\Steam\\steamapps\\common\\Blender\\blender.exe');
    if (process.env.LOCALAPPDATA) scan(path.join(process.env.LOCALAPPDATA, 'Programs'), /^Blender/i, 'blender.exe');
  } else if (process.platform === 'darwin') {
    c.push('/Applications/Blender.app/Contents/MacOS/Blender', path.join(os.homedir(), 'Applications/Blender.app/Contents/MacOS/Blender'));
  } else {
    c.push('/usr/bin/blender', '/usr/local/bin/blender', '/snap/bin/blender', '/var/lib/flatpak/exports/bin/org.blender.Blender');
    scan(os.homedir(), /^blender-\d/i, 'blender');
    scan('/opt', /^blender/i, 'blender');
  }
  c.push('blender'); // en el PATH
  return [...new Set(c)];
}
function blenderVersion(bin) {
  return new Promise((res) => execFile(bin, ['-b', '--factory-startup', '--version'], { timeout: 90000, windowsHide: true }, (e, out) => {
    const m = String(out || '').match(/Blender\s+(\d+\.\d+(?:\.\d+)?)/);
    res(m ? m[1] : null);
  }));
}
async function detectBlender(cfg, refresh = false) {
  if (blenderCache && !refresh && blenderCache.key === cfg.blenderPath) return blenderCache;
  for (const c of blenderCandidates(cfg)) {
    if (path.isAbsolute(c) && !fs.existsSync(c)) continue;
    const v = await blenderVersion(c);
    if (v) return (blenderCache = { key: cfg.blenderPath, path: c, version: v });
  }
  return (blenderCache = { key: cfg.blenderPath, path: null, version: null });
}
function runBlender(bin, args, log) {
  return new Promise((resolve, reject) => {
    const f = path.join(os.tmpdir(), `nvf_${Date.now()}_${crypto.randomBytes(3).toString('hex')}.json`);
    fs.writeFileSync(f, JSON.stringify(args));
    const p = spawn(bin, ['-b', '--factory-startup', '-P', BLENDER_SCRIPT, '--', f], { windowsHide: true });
    if (log.job) log.job.child = p;
    let result = null, err = null, carry = '';
    const tail = [];
    const onData = (chunk) => {
      const lines = (carry + chunk).split(/\r?\n/); carry = lines.pop();
      for (const line of lines) {
        if (line.startsWith('NVF:')) log('Blender · ' + line.slice(4));
        else if (line.startsWith('NVF_RESULT:')) { try { result = JSON.parse(line.slice(11)); } catch {} }
        else if (line.startsWith('NVF_ERROR:')) err = line.slice(10);
        else if (line.trim()) { tail.push(line.trim()); if (tail.length > 6) tail.shift(); }
      }
    };
    p.stdout.on('data', onData); p.stderr.on('data', onData);
    const to = setTimeout(() => { err = 'Blender tardó más de 40 minutos'; p.kill(); }, 40 * 60e3);
    p.on('error', (e) => { clearTimeout(to); reject(new Error('No se pudo lanzar Blender: ' + e.message)); });
    p.on('close', (code) => {
      clearTimeout(to); fs.unlink(f, () => {});
      if (carry) onData('\n');
      if (result) resolve(result);
      else reject(new Error(err || `Blender terminó con código ${code}: ${short(tail.join(' | '), 300)}`));
    });
  });
}
async function runBlenderJob(cfg, job, o, log) {
  const b = await detectBlender(cfg);
  if (!b.path) throw new Error('No encuentro Blender. Instálalo gratis desde blender.org o pon la ruta de blender.exe en Ajustes.');
  log(`Usando Blender ${b.version}`);
  const a = await findAsset(cfg, o.assetId);
  if (!a || a.kind !== '3d') throw new Error('Selecciona un asset 3D.');
  const glbs = a.files.filter((f) => /\.glb$/i.test(f));
  if (!glbs.length) throw new Error('El asset no tiene modelo .glb');
  const name = slugName(a.name);
  let args;
  if (o.action === 'blender-process') {
    args = { op: 'process', input: path.join(a.dir, a.files.includes('model.glb') ? 'model.glb' : glbs[0]), outDir: a.dir, name, height: Number(o.height) || null, maxTris: clampInt(o.maxTris, 0, 5e6, 0), lods: o.lods === false ? [] : [0.5, 0.25], formats: ['fbx', 'glb', 'obj'], saveBlend: true };
  } else {
    const opt = glbs.find((f) => /_optimized\.glb$/i.test(f));
    args = { op: 'render', input: path.join(a.dir, opt || (a.files.includes('model.glb') ? 'model.glb' : glbs[0])), outDir: a.dir, name, directions: clampInt(o.directions, 1, 32, 8), size: clampInt(o.size, 32, 2048, 256), elevation: Number(o.elevation) || 30, engine: o.engine === 'cycles' ? 'cycles' : 'eevee', quality: o.quality || 'normal', heroSize: 1024, pixel: !!o.pixel };
  }
  const res = await runBlender(b.path, args, log);
  job.assets.push(await readAsset(cfg, a.dir));
  log('✔ Blender terminado: ' + (res.files || []).join(', '));
  job.status = 'done';
}

// ───────────────────────── Prototipo jugable ─────────────────────────
function pngSize(buf) {
  if (buf.length > 24 && buf.readUInt32BE(12) === 0x49484452) return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
  if (buf[0] === 0xff && buf[1] === 0xd8) { // JPEG: buscar el marcador SOF
    let i = 2;
    while (i + 9 < buf.length) {
      if (buf[i] !== 0xff) { i++; continue; }
      const m = buf[i + 1];
      if (m >= 0xc0 && m <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(m)) return { h: buf.readUInt16BE(i + 5), w: buf.readUInt16BE(i + 7) };
      i += 2 + buf.readUInt16BE(i + 2);
    }
  }
  return null;
}
const isSource = (f) => /^source\.(png|jpe?g|webp)$/i.test(f);
const srcOf = (a) => a.files.find(isSource) || (a.files.find((f) => /^concept\.(png|jpe?g|webp)$/i.test(f))) || null;
const GAME_SYS = `You are a senior HTML5 game developer. Write a complete, polished, playable single-file browser game.
Rules:
- Reply with exactly one \`\`\`html code block containing the full index.html, nothing else.
- Use Phaser 3: <script src="https://cdn.jsdelivr.net/npm/phaser@3.80.1/dist/phaser.min.js"></script>
- Use ONLY the provided assets, loaded with their exact URLs (this.load.image, or this.load.spritesheet with the given frameWidth/frameHeight). Anything else (bullets, platforms, particles, UI) must be drawn with Phaser Graphics or textures generated with this.make.graphics().
- Game size 960x540, Phaser.Scale.FIT with autoCenter. Scale sprites with setDisplaySize to sensible sizes. Assets marked "white background" are not transparent: use them as icons/cards or tint-free, or avoid overlapping them.
- Arcade physics. Keyboard (arrows/WASD + space) and touch/pointer controls.
- Title screen with the game name and "press to start", gameplay with score and lives or health, rising difficulty, game over screen with restart.
- Create animations from spritesheets with the given fps.
- Juice: tweens, screen shake, simple particles made with graphics.
- No external assets, no network calls. Wrap any localStorage use in try/catch.
- Clean commented code, no placeholders, no TODOs.`;

function bestFile(a) {
  const sheet = a.files.find((f) => /_sheet_\d+x\d+_n\d+\.png$/i.test(f));
  if (sheet) return sheet;
  if (a.kind === '3d') return a.files.find((f) => /_blender_\d+dir_/.test(f)) || a.files.find((f) => /^spritesheet_/.test(f)) || (a.files.includes('thumb.png') ? 'thumb.png' : null);
  return a.files.filter((f) => /^processed.*\.png$/i.test(f)).pop() || (a.files.includes('source.png') ? 'source.png' : null);
}
async function runGame(cfg, job, o, log, project) {
  const desc = String(o.prompt || '').trim();
  if (!desc && !o.gameId) throw new Error('Describe el juego que quieres.');
  let assets = (await listAssets(cfg)).filter((a) => a.project === project);
  if (Array.isArray(o.assetIds) && o.assetIds.length) assets = assets.filter((a) => o.assetIds.includes(a.id));
  else assets = assets.slice(0, 12);
  const lines = [];
  for (const a of assets) {
    const f = bestFile(a); if (!f) continue;
    const buf = await fsp.readFile(path.join(a.dir, f));
    const sz = pngSize(buf) || { w: 0, h: 0 };
    const url = a.url + encodeURIComponent(f);
    const m = f.match(/_sheet_(\d+)x(\d+)_n(\d+)\.png$/i) || f.match(/_(\d+)dir_(\d+)px/);
    let kind = `image ${sz.w}x${sz.h}`;
    if (m && /_sheet_/.test(f)) kind = `spritesheet frameWidth=${m[1]} frameHeight=${m[2]} frames=${m[3]} fps=${a.fps || 8} (animation "${a.anim}")`;
    else if (m) kind = `spritesheet frameWidth=${m[2]} frameHeight=${m[2]} frames=${m[1]} (one frame per facing direction, frame 0 = facing camera, then rotating)`;
    const bg = /^processed|_sheet_|_dir|_blender_|thumb/.test(f) ? 'transparent background' : (a.background === 'white' ? 'white background' : 'opaque');
    lines.push(`- key "${slugName(a.name)}_${a.id.slice(-4)}": ${url} · ${kind} · ${bg} · ${TYPES[a.category]?.label || a.category}: ${short(a.prompt || a.name, 120)}`);
  }
  if (!lines.length) throw new Error('No hay assets en este proyecto para usar en el juego.');
  const dirOf = (id) => path.join(cfg.libraryPath, project, 'games', id);
  let prev = null, gid = o.gameId ? String(o.gameId).replace(/[^\w-]/g, '') : null;
  if (gid) { try { prev = await fsp.readFile(path.join(dirOf(gid), 'index.html'), 'utf8'); } catch { gid = null; } }
  const messages = [{ role: 'system', content: GAME_SYS }];
  if (prev) {
    messages.push({ role: 'user', content: `Assets:\n${lines.join('\n')}\n\nCurrent game code:\n\`\`\`html\n${prev}\n\`\`\`\n\nChange request (may be in Spanish): ${desc || 'fix bugs and polish the game'}\nReturn the full updated index.html.` });
  } else {
    messages.push({ role: 'user', content: `Game idea (may be in Spanish; in-game text in Spanish): ${desc}\n\nAssets:\n${lines.join('\n')}` });
  }
  log(`Escribiendo el juego con ${cfg.llmProvider === 'local' ? llmLabel(cfg) : cfg.codeModel} (${lines.length} assets)…`);
  const r = await chatStream(cfg, messages, cfg.codeModel, 16000, (n) => log(`… ${n} líneas`));
  const txt = r.text || '';
  const m = txt.match(/```html\s*([\s\S]*?)```/i) || txt.match(/```\s*(<!doctype[\s\S]*?)```/i) || txt.match(/(<!doctype html[\s\S]*<\/html>)/i);
  if (!m) throw new Error('El modelo no devolvió código HTML. Prueba otra vez u otro modelo de código.');
  const code = m[1].trim();
  if (!gid) gid = `${slugName(desc || 'juego').slice(0, 30)}_${Date.now().toString(36)}`;
  await fsp.mkdir(dirOf(gid), { recursive: true });
  if (prev) await fsp.writeFile(path.join(dirOf(gid), `index_v${Date.now().toString(36)}.html`), prev);
  await fsp.writeFile(path.join(dirOf(gid), 'index.html'), code);
  const metaF = path.join(dirOf(gid), 'game.json');
  let gm = {}; try { gm = JSON.parse(await fsp.readFile(metaF, 'utf8')); } catch {}
  gm = { id: gid, project, title: gm.title || desc.slice(0, 80), history: [...(gm.history || []), { at: new Date().toISOString(), prompt: desc, model: cfg.codeModel }], assets: assets.map((a) => a.id) };
  await fsp.writeFile(metaF, JSON.stringify(gm, null, 2));
  job.game = { id: gid, url: urlFor(cfg, dirOf(gid)) + 'index.html', title: gm.title };
  log(`✔ Juego listo: ${gm.title}`);
  job.status = 'done';
}
async function listGames(cfg, project) {
  const dir = path.join(cfg.libraryPath, safeName(project), 'games');
  let ds = []; try { ds = await fsp.readdir(dir, { withFileTypes: true }); } catch { return []; }
  const out = [];
  for (const d of ds) {
    if (!d.isDirectory()) continue;
    try { const g = JSON.parse(await fsp.readFile(path.join(dir, d.name, 'game.json'), 'utf8')); out.push({ ...g, url: urlFor(cfg, path.join(dir, d.name)) + 'index.html', updated: g.history?.slice(-1)[0]?.at }); } catch {}
  }
  return out.sort((a, b) => String(b.updated).localeCompare(String(a.updated)));
}

// ───────────────────────── 3D pro: Blender + LLM + texturas FLUX ─────────────────────────
// Respuestas largas por streaming (evita cortes) y sin "modo razonamiento" para que el
// presupuesto de tokens se use en el código.
async function chatStream(cfg, messages, model, max_tokens = 16000, onProgress) {
  const local = cfg.llmProvider === 'local';
  const url = local ? trimUrl(cfg.llmLocalUrl) + '/chat/completions' : NV.chat;
  const headers = { 'Content-Type': 'application/json', Accept: 'text/event-stream' };
  if (local) { if (cfg.llmLocalKey) headers.Authorization = `Bearer ${cfg.llmLocalKey}`; }
  else { if (!cfg.apiKey) throw new Error('Falta la API key de NVIDIA.'); headers.Authorization = `Bearer ${cfg.apiKey}`; }
  const body = { model: local ? (cfg.llmLocalModel || 'auto') : model, messages, temperature: 0.4, top_p: 0.95, max_tokens, stream: true };
  if (!local) body.chat_template_kwargs = { enable_thinking: false, thinking: false };
  const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) });
  if (!res.ok) {
    const t = await res.text();
    const e = new Error(`LLM ${res.status}: ${short(t, 300)}`); e.status = res.status; throw e;
  }
  const dec = new TextDecoder(); let buf = '', text = '', reasoning = 0, finish = null, last = 0;
  for await (const chunk of res.body) {
    buf += dec.decode(chunk, { stream: true });
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
      if (!line.startsWith('data:')) continue;
      const p = line.slice(5).trim(); if (p === '[DONE]') continue;
      try {
        const c = JSON.parse(p).choices?.[0]; if (!c) continue;
        text += c.delta?.content || '';
        reasoning += (c.delta?.reasoning_content || c.delta?.reasoning || '').length;
        if (c.finish_reason) finish = c.finish_reason;
      } catch {}
    }
    if (onProgress && Date.now() - last > 15000) { last = Date.now(); onProgress(text.split('\n').length); }
  }
  return { text, finish, reasoning };
}
const extractPython = (t) => { const m = t.match(/```(?:python|py)?\s*\n([\s\S]*?)```/i); return (m ? m[1] : t.replace(/```\w*/g, '')).trim(); };

const BUILD_PROMPT_FILE = path.join(ROOT, 'blender', 'build_prompt.md');
const PLAN3D_SYS = `You are the art director of a game studio planning ONE 3D game asset that will be modelled procedurally in Blender.
Return ONLY JSON: {"name": "snake_case english name", "brief": "precise English modelling brief, 60-120 words: overall shape and real dimensions in meters, every main part, materials, colour palette with one accent, small details and props that sell the asset", "textures": [{"key": "short_snake_key", "prompt": "what the tileable texture shows, e.g. rough grey fieldstone masonry"}]}
Use 2-6 textures for the large surfaces only (walls, roof, ground, wood, metal plates...). Reuse these keys when they fit: {EXISTING}.`;

async function projectTextures(cfg, project) {
  const dir = path.join(cfg.libraryPath, safeName(project), 'textures');
  const out = {};
  try { for (const f of await fsp.readdir(dir)) { const m = f.match(/^([\w-]+)\.(png|jpe?g|webp)$/i); if (m) out[m[1]] = path.join(dir, f); } } catch {}
  return { dir, map: out };
}
async function ensureTextures(cfg, project, wanted, styleText, log, imgKey) {
  const { dir, map } = await projectTextures(cfg, project);
  await fsp.mkdir(dir, { recursive: true });
  const todo = wanted.filter((t) => t && t.key && !map[slugName(t.key)]).slice(0, 6);
  await Promise.all(todo.map(async (t) => {
    const key = slugName(t.key);
    log(`Textura “${key}” con ${imageModel(cfg, imgKey).label}…`);
    const prompt = `Seamless tileable game texture of ${t.prompt}, ${styleText || 'stylized hand-painted game art'}, flat orthographic front view, even diffuse lighting, no cast shadows, no perspective, uniform pattern from edge to edge, fills the entire frame, no text`;
    try {
      const img = await genImage(cfg, { prompt, width: 1024, height: 1024, quality: 'normal', seed: randSeed(), model: imgKey });
      const f = path.join(dir, key + extOf(img.buf));
      await fsp.writeFile(f, img.buf); map[key] = f;
    } catch (e) { log(`⚠ Textura ${key} no generada (${short(e.message, 100)}); se usará color plano.`); }
  }));
  return map;
}
async function reviewRender(cfg, file, brief, log) {
  if (cfg.llmProvider === 'local') return null;
  const buf = await fsp.readFile(file);
  try {
    const r = await nvRequest(NV.chat, {
      model: cfg.visionModel,
      messages: [{ role: 'user', content: [
        { type: 'text', text: `You are the art director of a AAA game studio reviewing a 3D asset render. Brief: ${brief}\nList the 6 most important MODELLING problems (wrong proportions, floating or intersecting parts, missing parts from the brief, weak silhouette, lack of detail, bad colours). For each give one concrete geometric fix with sizes in meters. Be brief.` },
        { type: 'image_url', image_url: { url: `data:${mimeOf(buf)};base64,${buf.toString('base64')}` } },
      ] }],
      max_tokens: 700, temperature: 0.2, chat_template_kwargs: { enable_thinking: false },
    }, { apiKey: cfg.apiKey });
    return r.choices?.[0]?.message?.content || null;
  } catch (e) { log(`⚠ Revisión visual no disponible (${short(e.message, 100)}).`); return null; }
}

async function runBuild3D(cfg, job, o, log, quality, project) {
  const b = await detectBlender(cfg);
  if (!b.path) throw new Error('Para los modelos 3D pro hace falta Blender (gratis en blender.org). Si ya lo tienes, pon su ruta en Ajustes.');
  const prompt = String(o.prompt || '').trim();
  if (!prompt) throw new Error('Describe el modelo 3D.');
  const style = STYLES[o.style] ? o.style : 'auto';
  const proj = await loadProject(cfg, project);
  const styleText = [STYLES[style].p, proj.bible].filter(Boolean).join(', ');
  const imgKey = o.imageModel || cfg.imageModel;
  const codeModel = cfg.codeModel;
  const reviews = clampInt(o.reviews, 0, 3, quality === 'draft' ? 0 : quality === 'high' ? 2 : 1);

  // 1) plan de dirección de arte
  const { map: existing } = await projectTextures(cfg, project);
  log(`Dirección de arte con ${llmLabel(cfg)}…`);
  let plan;
  try {
    plan = await llmJSON(cfg, PLAN3D_SYS.replace('{EXISTING}', Object.keys(existing).join(', ') || 'none'), `Asset request (any language): ${prompt}\nArt style: ${styleText || 'stylized game art'}`);
  } catch (e) {
    log(`⚠ Plan automático no disponible (${short(e.message, 100)}); uso la descripción tal cual.`);
    plan = { name: slugName(prompt), brief: prompt, textures: [] };
  }
  const name = slugName(plan.name || prompt);
  const brief = String(plan.brief || prompt);
  log(`Brief: ${short(brief, 220)}`);

  // 2) texturas tileables (se reutilizan en todo el proyecto)
  const tex = await ensureTextures(cfg, project, Array.isArray(plan.textures) ? plan.textures : [], styleText, log, imgKey);
  const texList = Object.keys(tex).map((k) => k).join(', ') || 'none';

  // 3) script de Blender por el LLM + construcción, con autocorrección
  const sys = (await fsp.readFile(BUILD_PROMPT_FILE, 'utf8')).replace('{TEXTURES}', texList);
  const messages = [{ role: 'system', content: sys }, { role: 'user', content: `Asset: ${prompt}\nArt direction brief: ${brief}\nStyle: ${styleText || 'stylized game art'}` }];
  const id = Date.now().toString(36) + crypto.randomBytes(2).toString('hex');
  const dir = path.join(cfg.libraryPath, project, '3d', `${name}_${id}`);
  await fsp.mkdir(dir, { recursive: true });
  const bargs = { op: 'build', outDir: dir, name, engine: o.engine === 'cycles' ? 'cycles' : 'eevee', quality, heroSize: 1024, textures: tex };
  let code = null, result = null, lastErr = null, version = 0;
  const writeScript = async () => {
    log(`Escribiendo el modelo en Python para Blender con ${cfg.llmProvider === 'local' ? llmLabel(cfg) : codeModel}…`);
    const r = await chatStream(cfg, messages, codeModel, 16000, (n) => log(`… ${n} líneas`));
    const c = extractPython(r.text);
    if (c.split('\n').length < 10) throw new Error(`El modelo de código no devolvió un script (${r.finish || 'vacío'}). Prueba otro modelo en Ajustes.`);
    messages.push({ role: 'assistant', content: '```python\n' + c + '\n```' });
    return c;
  };
  const build = async (c) => {
    version++;
    const f = path.join(dir, version === 1 ? 'model_script.py' : `model_script_v${version}.py`);
    await fsp.writeFile(f, c);
    return runBlender(b.path, { ...bargs, script: f }, log);
  };
  for (let attempt = 0; attempt < 3 && !result; attempt++) {
    try {
      code = await writeScript();
      result = await build(code);
    } catch (e) {
      lastErr = e;
      if (/no devolvió un script|API key|401|403/.test(e.message)) throw e;
      log(`⚠ Error al construir: ${short(e.message, 200)}. Pido la corrección…`);
      messages.push({ role: 'user', content: `Blender raised this error running your script:\n${e.message}\nFix it and return the full corrected script.` });
    }
  }
  if (!result) throw lastErr || new Error('No se pudo construir el modelo.');
  log(`✔ Modelo construido: ${result.objects} piezas, ${result.triangles.toLocaleString('es')} triángulos`);

  // 4) revisión del director de arte (modelo de visión) → mejoras
  for (let r = 0; r < reviews; r++) {
    const critique = await reviewRender(cfg, path.join(dir, 'render_hero.png'), brief, log);
    if (!critique) break;
    log(`Revisión ${r + 1}/${reviews} del director de arte (${cfg.visionModel}): ${short(critique.replace(/\s+/g, ' '), 260)}`);
    await fsp.copyFile(path.join(dir, 'render_hero.png'), path.join(dir, `render_v${version}.png`)).catch(() => {});
    messages.push({ role: 'user', content: `Art director review of the current render:\n${critique}\nApply every fix that is possible with the kit, keep everything that already works, and return the full improved script.` });
    try {
      const c = await writeScript();
      const res2 = await build(c);
      result = res2; code = c;
      log(`✔ Versión ${version}: ${res2.objects} piezas, ${res2.triangles.toLocaleString('es')} triángulos`);
    } catch (e) {
      log(`⚠ La mejora falló (${short(e.message, 160)}); conservo la versión anterior.`);
      messages.push({ role: 'user', content: `That version failed: ${e.message}. Return the previous working script unchanged.` });
      const prev = path.join(dir, version - 1 === 1 ? 'model_script.py' : `model_script_v${version - 1}.py`);
      try { result = await runBlender(b.path, { ...bargs, script: prev }, log); } catch {}
      break;
    }
  }
  await fsp.copyFile(path.join(dir, 'render_hero.png'), path.join(dir, 'thumb.png')).catch(() => {});
  const meta = { id, name, project, kind: '3d', category: '3d-blender', style, prompt, imagePrompt: brief, tags: ['blender', 'procedural', style].filter((x) => x !== 'auto'), seed: 0, quality, model: `${codeModel} + Blender ${b.version}`, triangles: result.triangles, parts: result.objects, textures: Object.keys(tex), reviews, createdAt: new Date().toISOString() };
  await fsp.writeFile(path.join(dir, 'meta.json'), JSON.stringify(meta, null, 2));
  const a = await readAsset(cfg, dir);
  job.assets.push(a);
  log(`✔ Guardado ${name}: FBX, GLB, .blend, render y script editable`);
  job.status = 'done';
}

// ───────────────────────── Diseñador de mundos (LLM + recetas JSON + Blender) ─────────────────────────
const WORLD_DIR = path.join(ROOT, 'examples', 'world');
const WORLDGEN = path.join(WORLD_DIR, 'worldgen.py');
const WORLD_TEMPLATES_DIR = path.join(WORLD_DIR, 'worlds');
const W_BIOMES = ['plains', 'forest', 'farmland', 'desert', 'snow', 'mountain', 'swamp', 'volcanic', 'beach'];
const W_COMPOSITES = ['fortress', 'castle', 'village', 'port', 'oasis', 'camp', 'world_tree'];
const W_MODULES = ['tree0', 'tree1', 'tree2', 'pine', 'palm', 'crystal_teal', 'crystal_violet', 'ice_spike', 'windmill', 'pyramid', 'cave',
  'lighthouse', 'boat', 'ruins', 'house', 'castle_house', 'wall_tower', 'castle_tower', 'keep', 'castle_keep', 'waterfall', 'tent', 'pier', 'bridge', 'monolith'];

const WORLD_SYS = `You are the lead level designer of a JRPG studio. You design overworld maps as a JSON "recipe" that a Blender engine turns into a stylized cube-terrain 2D-HD world.
Coordinates are meters. X goes west→east, Y goes south→north, the map lives inside "bounds" [xmin, xmax, ymin, ymax] (default [-320, 320, -240, 240]). Sea level is 0; everything outside the land circles is sea.
Return ONLY one JSON object (no markdown) with these keys:
- name, description (Spanish), seed (int), bounds, cell (4)
- land: [{x, y, r}] circles whose union is the landmass, and/or land_polygons: [[[x,y],...]] coastline outlines (use them to reproduce real places) and sea_polygons (bays, inner seas cut from the land)
- default_biome and regions: [{biome, x, y, r}] later regions override earlier ones. Biomes: ${W_BIOMES.join(', ')}
- ridges: [{from:[x,y], to:[x,y], w, h}] mountain ranges; mountains: [{x, y, r, h}] single peaks; mesas: [{x, y, r, h}]; hills: [{x, y, r, h}]; volcanoes: [{x, y, r, h, snowcap?, dormant?}]
- lakes: [{x, y, r, frozen}], rivers: [{points:[[x,y],...], w}] (rivers should flow from mountains or lakes to the sea), roads: [{points:[[x,y],...]}] connecting landmarks, gorges: [{from, to, w, floor}]
- landmarks: [{type, x, y, rot, scale, z?}]. Composite types: ${W_COMPOSITES.join(', ')}. Single modules: ${W_MODULES.join(', ')}
- scatter: [{modules:[...], x, y, r, count, scale:[min,max]}] for forests, pines, palms, crystals, ruins, tents (total count under 700)
- floating_isles: [{x, y, z (80-130), scale}], clouds (int 0-20)
- sun: {elev (5-80 degrees), az, energy (1-6), color:[r,g,b]} and exposure (-2..0) to set the mood (golden hour, dusk, night...)
Design rules: a coherent, magical and readable world. Biomes must make geographic sense (snow and mountains together, deserts far from lakes, swamps near rivers, ports on the coast, castles on hills, fortresses in gorges or passes). Every landmark must sit on land, connected by roads. Leave breathing room between landmarks (>60 m). Keep 20 % of the land quiet (plains, forest) for contrast. Use the full map.`;

function tolerantJSON(text) {
  let t = String(text).replace(/<think>[\s\S]*?<\/think>/g, '').replace(/```(?:json)?/g, '');
  const a = t.indexOf('{'), b = t.lastIndexOf('}');
  if (a < 0 || b < a) throw new Error('no hay objeto JSON');
  t = t.slice(a, b + 1);
  try { return JSON.parse(t); } catch {}
  const fixed = t.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:"'\\])\/\/[^\n]*/g, '$1')
    .replace(/,\s*([}\]])/g, '$1').replace(/([{,]\s*)([A-Za-z_][\w]*)\s*:/g, '$1"$2":').replace(/\bTrue\b/g, 'true').replace(/\bFalse\b/g, 'false').replace(/\bNone\b/g, 'null');
  return JSON.parse(fixed);
}
function wNum(v, lo, hi, d) { const n = Number(v); return Number.isFinite(n) ? Math.max(lo, Math.min(hi, n)) : d; }
function sanitizeWorld(spec) {
  const s = typeof spec === 'object' && spec ? spec : {};
  const b = Array.isArray(s.bounds) && s.bounds.length === 4 ? s.bounds.map((v, i) => wNum(v, -600, 600, [-320, 320, -240, 240][i])) : [-320, 320, -240, 240];
  const [x0, x1, y0, y1] = b;
  const X = (v) => wNum(v, x0 - 200, x1 + 200, 0), Y = (v) => wNum(v, y0 - 200, y1 + 200, 0);
  const pts = (p) => (Array.isArray(p) ? p : []).slice(0, 80).map((q) => [X(q?.[0]), Y(q?.[1])]).filter((q) => q.length === 2);
  const arr = (a, n = 40) => (Array.isArray(a) ? a.slice(0, n) : []);
  const out = {
    name: String(s.name || 'Mundo').slice(0, 60), description: String(s.description || '').slice(0, 500), seed: wNum(s.seed, 0, 1e6, 7) | 0,
    bounds: b, cell: wNum(s.cell, 3, 8, 4), default_biome: W_BIOMES.includes(s.default_biome) ? s.default_biome : 'plains',
    land: arr(s.land, 12).map((l) => ({ x: X(l.x), y: Y(l.y), r: wNum(l.r, 10, 600, 120) })),
    regions: arr(s.regions).filter((r) => W_BIOMES.includes(r.biome)).map((r) => ({ biome: r.biome, x: X(r.x), y: Y(r.y), r: wNum(r.r, 5, 400, 60) })),
    ridges: arr(s.ridges, 10).map((r) => ({ from: [X(r.from?.[0]), Y(r.from?.[1])], to: [X(r.to?.[0]), Y(r.to?.[1])], w: wNum(r.w, 10, 200, 50), h: wNum(r.h, 5, 140, 60) })),
    mountains: arr(s.mountains, 20).map((m) => ({ x: X(m.x), y: Y(m.y), r: wNum(m.r, 10, 200, 50), h: wNum(m.h, 5, 140, 60) })),
    mesas: arr(s.mesas, 12).map((m) => ({ x: X(m.x), y: Y(m.y), r: wNum(m.r, 8, 60, 24), h: wNum(m.h, 6, 70, 30) })),
    hills: arr(s.hills, 20).map((m) => ({ x: X(m.x), y: Y(m.y), r: wNum(m.r, 8, 160, 50), h: wNum(m.h, 2, 40, 12) })),
    volcanoes: arr(s.volcanoes, 4).map((m) => ({ x: X(m.x), y: Y(m.y), r: wNum(m.r, 20, 160, 55), h: wNum(m.h, 20, 160, 75), snowcap: !!m.snowcap, dormant: !!m.dormant, green: !!m.green })),
    land_polygons: arr(s.land_polygons, 12).map((p) => pts(p).slice(0, 80)).filter((p) => p.length > 2),
    sea_polygons: arr(s.sea_polygons, 8).map((p) => pts(p).slice(0, 60)).filter((p) => p.length > 2),
    lakes: arr(s.lakes, 10).map((l) => ({ x: X(l.x), y: Y(l.y), r: wNum(l.r, 6, 120, 30), frozen: !!l.frozen })),
    rivers: arr(s.rivers, 8).map((r) => ({ points: pts(r.points), w: wNum(r.w, 2, 14, 5) })).filter((r) => r.points.length > 1),
    roads: arr(s.roads, 14).map((r) => ({ points: pts(r.points) })).filter((r) => r.points.length > 1),
    gorges: arr(s.gorges, 4).map((g) => ({ from: [X(g.from?.[0]), Y(g.from?.[1])], to: [X(g.to?.[0]), Y(g.to?.[1])], w: wNum(g.w, 10, 60, 24), floor: wNum(g.floor, 0, 40, 6) })),
    landmarks: arr(s.landmarks, 30).filter((l) => W_COMPOSITES.includes(l.type) || W_MODULES.includes(l.type) || l.type === 'pyramid')
      .map((l) => { const o = { type: l.type, x: X(l.x), y: Y(l.y), rot: wNum(l.rot, -360, 360, 0), scale: wNum(l.scale, 0.4, 2.5, 1) }; if (l.z !== undefined) o.z = wNum(l.z, -5, 200, 0); return o; }),
    scatter: arr(s.scatter, 20).map((c) => ({ modules: (Array.isArray(c.modules) ? c.modules : []).filter((m) => W_MODULES.includes(m)).slice(0, 6), x: X(c.x), y: Y(c.y), r: wNum(c.r, 5, 400, 40), count: wNum(c.count, 1, 300, 30) | 0, scale: [wNum(c.scale?.[0], 0.3, 3, 0.8), wNum(c.scale?.[1], 0.3, 3, 1.3)] }))
      .filter((c) => c.modules.length),
    floating_isles: arr(s.floating_isles, 6).map((i) => ({ x: X(i.x), y: Y(i.y), z: wNum(i.z, 60, 160, 100), scale: wNum(i.scale, 0.4, 1.6, 1) })),
    clouds: wNum(s.clouds, 0, 24, 12) | 0,
    sun: { elev: wNum(s.sun?.elev, 3, 85, 32), az: wNum(s.sun?.az, -360, 360, -40), energy: wNum(s.sun?.energy, 0.3, 8, 4.5),
      color: Array.isArray(s.sun?.color) ? s.sun.color.slice(0, 3).map((c) => wNum(c, 0, 1, 1)) : [1.0, 0.86, 0.68] },
    exposure: wNum(s.exposure, -3, 1, -0.85),
  };
  if (!out.land.length) out.land = [{ x: 0, y: 0, r: 260 }];
  return out;
}
async function listWorldTemplates() {
  const out = [];
  try { for (const f of await fsp.readdir(WORLD_TEMPLATES_DIR)) if (f.endsWith('.json')) { const j = JSON.parse(await fsp.readFile(path.join(WORLD_TEMPLATES_DIR, f), 'utf8')); out.push({ id: f.replace(/\.json$/, ''), name: j.name, description: j.description }); } } catch {}
  return out;
}
function runWorldgen(bin, args, log) {
  return new Promise((resolve, reject) => {
    const p = spawn(bin, ['-b', '--factory-startup', '-P', WORLDGEN, '--', ...args], { windowsHide: true, cwd: WORLD_DIR });
    if (log.job) log.job.child = p;
    let carry = ''; const tail = [];
    const onData = (chunk) => {
      const lines = (carry + chunk).split(/\r?\n/); carry = lines.pop();
      for (const l of lines) { if (l.startsWith('WORLD:')) log('Blender · ' + l.slice(6).trim()); else if (l.trim()) { tail.push(l.trim()); if (tail.length > 8) tail.shift(); } }
    };
    p.stdout.on('data', onData); p.stderr.on('data', onData);
    const to = setTimeout(() => p.kill(), 60 * 60e3);
    p.on('error', (e) => { clearTimeout(to); reject(new Error('No se pudo lanzar Blender: ' + e.message)); });
    p.on('close', (code) => { clearTimeout(to); code === 0 ? resolve() : reject(new Error(`Blender terminó con código ${code}: ${short(tail.filter((t) => /Error|Traceback|line/.test(t)).join(' | ') || tail.join(' | '), 400)}`)); });
  });
}
async function designWorld(cfg, messages, log) {
  log(`Diseñando el mundo con ${cfg.llmProvider === 'local' ? llmLabel(cfg) : cfg.codeModel}…`);
  const r = await chatStream(cfg, messages, cfg.codeModel, 12000, (n) => log(`… ${n} líneas de receta`));
  let spec;
  try { spec = tolerantJSON(r.text); }
  catch (e) {
    log(`⚠ Receta con errores de JSON (${short(e.message, 80)}); pido la corrección…`);
    messages.push({ role: 'assistant', content: r.text.slice(0, 20000) });
    messages.push({ role: 'user', content: `That JSON is invalid (${e.message}). Return the same recipe as strictly valid JSON: double quotes, no comments, no trailing commas, nothing else.` });
    const r2 = await chatStream(cfg, messages, cfg.codeModel, 12000, (n) => log(`… ${n} líneas`));
    spec = tolerantJSON(r2.text);
    messages.splice(messages.length - 2, 2);
  }
  messages.push({ role: 'assistant', content: JSON.stringify(spec) });
  return sanitizeWorld(spec);
}
async function runWorld(cfg, job, o, log, quality, project) {
  const b = await detectBlender(cfg);
  if (!b.path) throw new Error('El diseñador de mundos necesita Blender (gratis en blender.org).');
  const prompt = String(o.prompt || '').trim();
  let base = null;
  if (o.template) {
    try { base = JSON.parse(await fsp.readFile(path.join(WORLD_TEMPLATES_DIR, String(o.template).replace(/[^\w-]/g, '') + '.json'), 'utf8')); } catch {}
  }
  if (o.worldId) {
    const a = await findAsset(cfg, o.worldId);
    if (a && a.files.includes('world.json')) base = JSON.parse(await fsp.readFile(path.join(a.dir, 'world.json'), 'utf8'));
  }
  if (!prompt && !base && !o.spec) throw new Error('Describe el mundo o elige una plantilla.');
  let example = null;
  try { example = await fsp.readFile(path.join(WORLD_TEMPLATES_DIR, 'aethermoor.json'), 'utf8'); } catch {}
  const messages = [{ role: 'system', content: WORLD_SYS }];
  if (base) messages.push({ role: 'user', content: `Current world recipe:\n${JSON.stringify(base)}\n\nModify it as requested (the request may be in Spanish) and return the FULL new recipe. Keep everything that is not affected by the request.\nRequest: ${prompt || 'improve it: more coherent geography, richer coastline, better landmark placement and more magic'}` });
  else messages.push({ role: 'user', content: (example ? `Example recipe (for format and quality reference only, do not copy its layout):\n${example}\n\n` : '') + `Design a NEW world (request may be in Spanish): ${prompt}` });
  let spec = o.spec ? sanitizeWorld(typeof o.spec === 'string' ? JSON.parse(o.spec) : o.spec) : base && !prompt ? sanitizeWorld(base) : await designWorld(cfg, messages, log);
  if (o.spec) log('Receta editada a mano: construyo sin LLM.');
  const id = Date.now().toString(36) + crypto.randomBytes(2).toString('hex');
  const name = slugName(spec.name || prompt || 'mundo');
  const dir = path.join(cfg.libraryPath, project, '3d', `${name}_${id}`);
  await fsp.mkdir(dir, { recursive: true });
  const tod = ['day', 'dawn', 'dusk', 'night'].includes(o.time) ? o.time : null;
  const todArgs = tod ? ['--time', tod] : [];
  if (tod) log(`Hora del día: ${{ day: 'día', dawn: 'amanecer', dusk: 'atardecer', night: 'noche' }[tod]}.`);
  const render = async (tag, res, samples) => {
    const specF = path.join(dir, 'world.json');
    await fsp.writeFile(specF, JSON.stringify(spec, null, 2));
    log(`Construyendo “${spec.name}” en Blender (${res}, ${samples} muestras)…`);
    await runWorldgen(b.path, ['--spec', specF, '--res', res, '--samples', String(samples), '--out', path.join(dir, tag + '.png'), ...todArgs], log);
  };
  const reviews = o.spec ? 0 : clampInt(o.reviews, 0, 2, quality === 'draft' ? 0 : 1);
  for (let r = 0; r < reviews; r++) {
    await render('preview_v' + (r + 1), '960x540', 10);
    const critique = await reviewRender(cfg, path.join(dir, `preview_v${r + 1}.png`), `JRPG overworld map. Request: ${prompt}. Recipe summary: ${spec.description}`, log);
    if (!critique) break;
    log(`Director de arte: ${short(critique.replace(/\s+/g, ' '), 260)}`);
    messages.push({ role: 'user', content: `Art director review of the rendered map:\n${critique}\nImprove the recipe accordingly (geography, coastline, landmark placement, biome contrast, magic, mood). Return the FULL recipe.` });
    try { spec = await designWorld(cfg, messages, log); } catch (e) { log(`⚠ Mejora no aplicada (${short(e.message, 120)}).`); break; }
  }
  const res = quality === 'high' ? '1920x1080' : quality === 'draft' ? '960x540' : '1600x900';
  const samples = quality === 'high' ? 64 : quality === 'draft' ? 12 : 32;
  await render('world', res, samples);
  for (let k = 0; k < Math.min(3, spec.landmarks.length) && quality !== 'draft'; k++) {
    const specF = path.join(dir, 'world.json');
    log(`Plano de detalle ${k + 1}: ${spec.landmarks[k].type}`);
    await runWorldgen(b.path, ['--spec', specF, '--shot', `lm${k}`, '--res', '1280x720', '--samples', '24', '--out', path.join(dir, `zone_${k + 1}_${spec.landmarks[k].type}.png`), ...todArgs], log).catch((e) => log('⚠ ' + short(e.message, 120)));
  }
  if (o.playShots !== false) { // vista de juego: cámara RPG elevada y cercana, tilt-shift
    // primero los lugares habitados (donde estará el jugador), luego el resto
    const pref = ['village', 'castle', 'port', 'fortress', 'oasis', 'camp', 'world_tree', 'ruins', 'pyramid'];
    const order = spec.landmarks.map((l, k) => [k, pref.indexOf(l.type)]).filter(([, r]) => r >= 0).sort((x, y) => x[1] - y[1]).map(([k]) => k);
    const picks = order.slice(0, quality === 'draft' ? 1 : 3);
    for (let n = 0; n < picks.length; n++) {
      const k = picks[n];
      log(`Vista de juego ${n + 1}: ${spec.landmarks[k].type}`);
      await runWorldgen(b.path, ['--spec', path.join(dir, 'world.json'), '--shot', `play${k}`, '--res', quality === 'draft' ? '960x540' : '1280x720', '--samples', quality === 'draft' ? '12' : '24', '--out', path.join(dir, `play_${n + 1}_${spec.landmarks[k].type}.png`), ...todArgs], log).catch((e) => log('⚠ ' + short(e.message, 120)));
    }
  }
  await fsp.copyFile(path.join(dir, 'world.png'), path.join(dir, 'thumb.png')).catch(() => {});
  const meta = { id, name, project, kind: '3d', category: 'world', style: 'cube2dhd', prompt, imagePrompt: spec.description, tags: ['world', 'jrpg', 'blender', ...(tod ? [tod] : [])], time: tod || 'day', seed: spec.seed, quality, model: `${codeModelLabel(cfg)} + Blender ${b.version}`, worldName: spec.name, template: o.template || null, parent: o.worldId || null, createdAt: new Date().toISOString() };
  await fsp.writeFile(path.join(dir, 'meta.json'), JSON.stringify(meta, null, 2));
  job.assets.push(await readAsset(cfg, dir));
  log(`✔ Mundo “${spec.name}” guardado (receta world.json reutilizable, render y planos de zona)`);
  job.status = 'done';
}
const codeModelLabel = (cfg) => (cfg.llmProvider === 'local' ? llmLabel(cfg) : cfg.codeModel);

// ───────────────────────── Trabajos principales ─────────────────────────
async function runJob(job, o) {
  const cfg = loadConfig();
  const log = (m) => {
    if (job.cancelled) { const e = new Error('Cancelado por el usuario.'); e.cancelled = true; throw e; } // cada línea de log es un punto de cancelación
    job.log.push(`${new Date().toLocaleTimeString('es-ES')}  ${m}`); console.log('  ' + m);
  };
  log.job = job;
  const quality = ['draft', 'normal', 'high'].includes(o.quality) ? o.quality : 'normal';
  const project = safeName(o.project || cfg.project) || 'MiJuego';
  try {
    if (o.action === 'edit') return await runEdit(cfg, job, o, log, quality, project);
    if (o.action === 'to3d') return await runTo3D(cfg, job, o, log, quality, project);
    if (o.action === 'animate') return await runAnimate(cfg, job, o, log, quality, project);
    if (o.action === 'blender-process' || o.action === 'blender-render') return await runBlenderJob(cfg, job, o, log);
    if (o.action === 'game') return await runGame(cfg, job, o, log, project);
    if (o.action === 'world') return await runWorld(cfg, job, o, log, quality, project);
    if (o.action === 'pack') return await runPack(cfg, job, o, log, quality, project);
    if (o.category === '3d-blender') return await runBuild3D(cfg, job, o, log, quality, project);

    const category = TYPES[o.category] ? o.category : '2d-item';
    const T = TYPES[category];
    const style = STYLES[o.style] ? o.style : 'auto';
    const prompt = String(o.prompt || '').trim();
    if (!prompt) throw new Error('Escribe qué asset quieres.');
    const size = SIZES.includes(o.size) ? o.size : T.size;
    const [w, h] = size.split('x').map(Number);
    const variants = clampInt(o.variants, 1, 4, 1);
    const imgKey = o.imageModel || cfg.imageModel;
    const m3dKey = o.model3d || cfg.model3d;
    const proj = await loadProject(cfg, project);
    const bible = String(proj.bible || '').trim();
    if (bible) log('Aplicando la guía de estilo del proyecto.');

    let plan = o.plan && o.plan.image_prompt ? { ...o.plan, name: slugName(o.plan.name || prompt), source: 'editado' } : null;
    if (!plan && o.enhance !== false) {
      log(`Optimizando prompt con ${llmLabel(cfg)}…`);
      const favs = await favoriteExamples(cfg, project, category);
      if (favs.length) log(`Aprendiendo de ${favs.length} favorito(s) ★ del proyecto.`);
      try { plan = await enhancePrompt(cfg, prompt, category, style, bible, favs); log('Prompt optimizado.'); }
      catch (e) { log(`⚠ No se pudo optimizar (${short(e.message)}). Uso plantilla profesional local.`); }
    }
    if (!plan) plan = fallbackPlan(prompt, category, style, bible);
    job.plan = plan;

    let refBuf = null;
    if (o.useRef && category !== '3d-text') {
      refBuf = await referenceBuf(cfg, proj);
      if (!refBuf) log('⚠ El proyecto no tiene imagen de referencia; genero sin ella.');
    }
    const label = refBuf ? 'FLUX Kontext + referencia de estilo' : imageModel(cfg, imgKey).label;
    const makeImage = (W, H, seed) => refBuf
      ? editImage(cfg, { prompt: `Create a completely new image of: ${plan.image_prompt} Use exactly the same art style, rendering technique, line work, color palette, lighting and level of detail as this reference image, but do not copy its subject, pose or composition.`.slice(0, 1800), imageBuf: refBuf, quality, seed })
      : genImage(cfg, { prompt: plan.image_prompt, width: W, height: H, quality, seed, model: imgKey });

    for (let v = 0; v < variants; v++) {
      const seed = o.seed && variants === 1 ? clampInt(o.seed, 1, 2147483646, randSeed()) : randSeed();
      const tag = variants > 1 ? ` [${v + 1}/${variants}]` : '';
      job.progress = v / variants;
      const meta = { name: plan.name, project, kind: T.kind, category, style, prompt, imagePrompt: plan.image_prompt, trellisPrompt: plan.trellis_prompt, tags: plan.tags || [], seed, quality, background: T.bg, styleRef: refBuf ? proj.refAssetId : undefined };
      if (T.kind === '2d') {
        log(`Generando imagen ${refBuf ? '' : `${w}×${h} `}con ${label} (${cfg.backend2d === 'local' ? 'NIM local' : 'NVIDIA cloud'})${tag}…`);
        const img = await makeImage(w, h, seed);
        const a = await createAsset(cfg, { ...meta, model: refBuf ? 'flux.1-kontext-dev' : imgKey, width: (pngSize(img.buf) || {}).w || w, height: (pngSize(img.buf) || {}).h || h }, { 'source.png': img.buf });
        job.assets.push(a); log(`✔ Guardado ${a.name}${tag}`);
      } else if (category === '3d-text') {
        log(`Generando 3D con ${model3D(cfg, m3dKey).label} (texto): “${plan.trellis_prompt}”${tag}…`);
        const glb = await gen3D(cfg, { mode: 'text', prompt: plan.trellis_prompt, quality, seed, model: m3dKey });
        const a = await createAsset(cfg, { ...meta, model: m3dKey, trellisMode: 'text' }, { 'model.glb': glb.buf });
        job.assets.push(a); log(`✔ Guardado ${a.name}${tag}`);
      } else {
        log(`Generando concept con ${label}${tag}…`);
        const img = await makeImage(1024, 1024, seed);
        const { glb, mode } = await imageTo3D(cfg, img.buf, plan.trellis_prompt, quality, seed, log, m3dKey);
        const a = await createAsset(cfg, { ...meta, model: m3dKey, trellisMode: mode, conceptModel: refBuf ? 'flux.1-kontext-dev' : imgKey }, { 'model.glb': glb.buf, 'concept.png': img.buf });
        job.assets.push(a); log(`✔ Guardado ${a.name}${tag}`);
      }
    }
    job.status = 'done';
  } catch (e) {
    if (job.cancelled || e.cancelled) { job.status = 'cancelled'; job.error = 'Cancelado'; job.log.push(`${new Date().toLocaleTimeString('es-ES')}  ■ Cancelado. Lo ya generado se queda en la biblioteca.`); return; }
    job.status = 'error'; job.error = e.message; job.log.push(`${new Date().toLocaleTimeString('es-ES')}  ✖ ${e.message}`);
  } finally { job.child = null; job.ended = Date.now(); if (job.status === 'done') job.progress = 1; }
}

async function imageTo3D(cfg, buf, fallbackPrompt, quality, seed, log, model) {
  const label = model3D(cfg, model).label;
  try {
    log(`Reconstruyendo en 3D con ${label} (imagen, ${cfg.backend3d === 'local' ? 'NIM local' : 'NVIDIA cloud'})…`);
    return { glb: await gen3D(cfg, { mode: 'image', imageBuf: buf, quality, seed, model }), mode: 'image' };
  } catch (e) {
    if (!fallbackPrompt) throw e;
    log(`⚠ Imagen→3D no disponible (${short(e.message, 120)}). Paso a texto→3D.`);
    return { glb: await gen3D(cfg, { mode: 'text', prompt: fallbackPrompt, quality, seed, model }), mode: 'text' };
  }
}

async function sourceFile(cfg, o) {
  const src = await findAsset(cfg, o.assetId);
  if (!src) throw new Error('Asset de origen no encontrado.');
  const file = o.file && src.files.includes(o.file) && /\.png$/i.test(o.file) ? o.file : src.files.includes('source.png') ? 'source.png' : src.files.includes('concept.png') ? 'concept.png' : src.files.find((f) => /\.png$/i.test(f) && f !== 'thumb.png');
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
  const m3dKey = o.model3d || cfg.model3d;
  const fb = src.trellisPrompt || String(src.prompt || src.name).slice(0, 77);
  const { glb, mode } = await imageTo3D(cfg, buf, fb, quality, seed, log, m3dKey);
  const a = await createAsset(cfg, { name: `${src.name}_3d`, project: src.project || project, kind: '3d', category: '3d-image', style: src.style, prompt: src.prompt, imagePrompt: src.imagePrompt, trellisPrompt: fb, tags: src.tags || [], seed, quality, model: m3dKey, trellisMode: mode, parent: src.id }, { 'model.glb': glb.buf, 'concept.png': buf });
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
      job.kind = String(b.action || b.category || 'asset').slice(0, 30); job.label = String(b.label || b.prompt || job.kind).slice(0, 90);
      runJob(job, b); return send(res, 200, { jobId: job.id });
    }
    let m;
    if (p === '/api/jobs' && req.method === 'GET') {
      const list = [...jobs.values()].sort((a, b) => b.created - a.created).slice(0, 30)
        .map((j) => ({ id: j.id, label: j.label, kind: j.kind, status: j.status, progress: j.progress, created: j.created, ended: j.ended, last: j.log[j.log.length - 1] || '', error: j.error, assets: j.assets.length }));
      return send(res, 200, list);
    }
    if ((m = p.match(/^\/api\/jobs\/([a-f0-9]+)\/cancel$/)) && req.method === 'POST') {
      const j = jobs.get(m[1]); if (!j) return send(res, 404, { error: 'trabajo no encontrado' });
      if (j.status === 'running') { j.cancelled = true; try { j.child && j.child.kill(); } catch {} }
      return send(res, 200, { ok: true });
    }
    if ((m = p.match(/^\/api\/jobs\/([a-f0-9]+)$/))) {
      const j = jobs.get(m[1]); if (!j) return send(res, 404, { error: 'trabajo no encontrado' });
      const { child, ...pub } = j;
      return send(res, 200, { ...pub, assets: j.assets.map(strip) });
    }
    if (p === '/api/assets' && req.method === 'POST') { // crear un asset desde el navegador (escenas 3D del editor)
      const cfg = loadConfig(); const b = await readBody(req);
      const files = {};
      for (const [n, d] of Object.entries(b.files || {})) {
        if (!/^[\w\-.]{1,80}\.(png|glb|json)$/i.test(n) || n === 'meta.json') return send(res, 400, { error: 'nombre de archivo no válido: ' + n });
        files[n] = Buffer.from(String(d).replace(/^data:[^,]+,/, ''), 'base64');
      }
      const kind = b.kind === '2d' ? '2d' : '3d';
      const a = await createAsset(cfg, { name: slugName(b.name || 'escena'), project: b.project, kind, category: String(b.category || (kind === '3d' ? '3d-scene' : '2d-item')).slice(0, 30), prompt: String(b.prompt || '').slice(0, 500), tags: Array.isArray(b.tags) ? b.tags.map(String).slice(0, 8) : [], model: 'Editor de escenas', seed: 0 }, files);
      return send(res, 200, strip(a));
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
        if (b.favorite !== undefined) meta.favorite = !!b.favorite;
        await fsp.writeFile(path.join(a.dir, 'meta.json'), JSON.stringify(meta, null, 2));
        return send(res, 200, strip(await readAsset(cfg, a.dir)));
      }
    }
    if ((m = p.match(/^\/api\/assets\/([\w]+)\/file$/)) && req.method === 'POST') {
      const cfg = loadConfig(); const a = await findAsset(cfg, m[1]);
      if (!a) return send(res, 404, { error: 'asset no encontrado' });
      const b = await readBody(req);
      const name = String(b.name || '').replace(/[^\w\-.]/g, '_');
      if (!/^[\w\-.]{1,80}\.(png|webp|jpg|glb|json|tsx|tres|tmx|tscn)$/i.test(name) || name === 'meta.json') return send(res, 400, { error: 'nombre de archivo no válido' });
      const buf = Buffer.from(String(b.data || '').replace(/^data:[^,]+,/, ''), 'base64');
      await fsp.writeFile(path.join(a.dir, name), buf);
      return send(res, 200, strip(await readAsset(cfg, a.dir)));
    }
    if (p === '/api/blender') {
      const cfg = loadConfig();
      const b = await detectBlender(cfg, u.searchParams.has('refresh') || req.method === 'POST');
      return send(res, 200, { found: !!b.path, path: b.path, version: b.version });
    }
    if (p === '/api/project') {
      const cfg = loadConfig(); const name = safeName(u.searchParams.get('name') || cfg.project) || 'MiJuego';
      if (req.method === 'POST') return send(res, 200, await saveProject(cfg, name, await readBody(req)));
      return send(res, 200, await loadProject(cfg, name));
    }
    if (p === '/api/scene-ai' && req.method === 'POST') {
      const b = await readBody(req); const cfg = loadConfig();
      try { return send(res, 200, await designScene(cfg, String(b.prompt || '').slice(0, 2000), Array.isArray(b.current) ? b.current : null)); }
      catch (e) { return send(res, 502, { error: 'No se pudo componer la escena: ' + short(e.message, 200) }); }
    }
    if (p === '/api/export' && req.method === 'POST') {
      const b = await readBody(req);
      const r = await exportPack(loadConfig(), Array.isArray(b.ids) ? b.ids.map(String) : [], String(b.engine || 'generic'));
      res.writeHead(200, { 'Content-Type': 'application/zip', 'Content-Disposition': `attachment; filename="${r.name}"`, 'Content-Length': r.zip.length, 'X-Asset-Count': String(r.count) });
      return res.end(r.zip);
    }
    if (p === '/api/world-templates') return send(res, 200, await listWorldTemplates());
    if (p === '/api/games') {
      const cfg = loadConfig(); return send(res, 200, await listGames(cfg, safeName(u.searchParams.get('project') || cfg.project) || 'MiJuego'));
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
