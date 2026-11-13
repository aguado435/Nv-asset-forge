// NV Asset Forge · herramientas 2D que corren en el navegador (las usan la app y Forge Lite en docs/).
// Si cambias este archivo, cópialo también a docs/forge-tools.js.
function cornerColor(d, w, h) {
  const pts = []; const s = Math.max(2, Math.round(Math.min(w, h) * 0.01));
  for (const [cx, cy] of [[0, 0], [w - s, 0], [0, h - s], [w - s, h - s]]) for (let y = cy; y < cy + s; y++) for (let x = cx; x < cx + s; x++) { const i = (y * w + x) * 4; pts.push([d[i], d[i + 1], d[i + 2]]); }
  const med = (k) => pts.map((p) => p[k]).sort((a, b) => a - b)[pts.length >> 1];
  return [med(0), med(1), med(2)];
}
function removeBg(tol, target) {
  const tx = target.getContext('2d', { willReadFrequently: true });
  const w = target.width, h = target.height, id = tx.getImageData(0, 0, w, h), d = id.data;
  const bg = cornerColor(d, w, h);
  const dist = (p) => { const i = p * 4; const r = d[i] - bg[0], g = d[i + 1] - bg[1], b = d[i + 2] - bg[2]; return Math.sqrt(r * r + g * g + b * b); };
  const N = w * h, mark = new Uint8Array(N), st = new Int32Array(N); let sp = 0;
  const push = (p) => { if (!mark[p] && d[p * 4 + 3] > 0 && dist(p) <= tol) { mark[p] = 1; st[sp++] = p; } };
  for (let x = 0; x < w; x++) { push(x); push((h - 1) * w + x); }
  for (let y = 0; y < h; y++) { push(y * w); push(y * w + w - 1); }
  while (sp) { const p = st[--sp], x = p % w; if (x > 0) push(p - 1); if (x < w - 1) push(p + 1); if (p >= w) push(p - w); if (p < N - w) push(p + w); }
  // borde suave + descontaminación de color
  for (let p = 0; p < N; p++) {
    if (mark[p]) { d[p * 4 + 3] = 0; continue; }
    const x = p % w;
    const near = (x > 0 && mark[p - 1]) || (x < w - 1 && mark[p + 1]) || (p >= w && mark[p - w]) || (p < N - w && mark[p + w]);
    if (!near) continue;
    const dd = dist(p); if (dd > tol * 2.2) continue;
    const a = Math.max(0.15, Math.min(1, (dd - tol) / (tol * 1.2)));
    const i = p * 4;
    for (let k = 0; k < 3; k++) d[i + k] = Math.max(0, Math.min(255, (d[i + k] - bg[k] * (1 - a)) / a));
    d[i + 3] = Math.round(d[i + 3] * a);
  }
  tx.putImageData(id, 0, 0);
}
function alphaBox(c) {
  const w = c.width, h = c.height, d = c.getContext('2d', { willReadFrequently: true }).getImageData(0, 0, w, h).data;
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (d[(y * w + x) * 4 + 3] > 10) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  return x1 < 0 ? null : { x0, y0, x1, y1, w: x1 - x0 + 1, h: y1 - y0 + 1 };
}
function kmeans(px, k) {
  const n = px.length / 3; if (!n) return [];
  const C = [];
  C.push([px[0], px[1], px[2]]);
  while (C.length < Math.min(k, n)) { // k-means++ aproximado
    let best = -1, bi = 0;
    for (let s = 0; s < 400; s++) { const i = Math.floor(Math.random() * n) * 3; let m = Infinity; for (const c of C) { const dr = px[i] - c[0], dg = px[i + 1] - c[1], db = px[i + 2] - c[2]; m = Math.min(m, dr * dr + dg * dg + db * db); } if (m > best) { best = m; bi = i; } }
    C.push([px[bi], px[bi + 1], px[bi + 2]]);
  }
  const asg = new Uint8Array(n);
  for (let it = 0; it < 10; it++) {
    const S = C.map(() => [0, 0, 0, 0]);
    for (let j = 0; j < n; j++) { const i = j * 3; let m = Infinity, mi = 0; C.forEach((c, ci) => { const dr = px[i] - c[0], dg = px[i + 1] - c[1], db = px[i + 2] - c[2]; const dd = dr * dr + dg * dg + db * db; if (dd < m) { m = dd; mi = ci; } }); asg[j] = mi; const s = S[mi]; s[0] += px[i]; s[1] += px[i + 1]; s[2] += px[i + 2]; s[3]++; }
    S.forEach((s, ci) => { if (s[3]) C[ci] = [s[0] / s[3], s[1] / s[3], s[2] / s[3]]; });
  }
  return C.map((c) => c.map(Math.round));
}
function pixelateCanvas(base, tw, colors) {
  tw = Math.max(8, Math.min(512, tw | 0)); const th = Math.max(1, Math.round(base.height * tw / base.width));
  // reducción por pasos para promediar bien
  let src = base;
  while (src.width / 2 > tw) { const c = document.createElement('canvas'); c.width = Math.round(src.width / 2); c.height = Math.round(src.height / 2); const x = c.getContext('2d'); x.imageSmoothingQuality = 'high'; x.drawImage(src, 0, 0, c.width, c.height); src = c; }
  const c = document.createElement('canvas'); c.width = tw; c.height = th; const x = c.getContext('2d', { willReadFrequently: true }); x.imageSmoothingQuality = 'high'; x.drawImage(src, 0, 0, tw, th);
  const id = x.getImageData(0, 0, tw, th), d = id.data, px = [];
  for (let i = 0; i < d.length; i += 4) { d[i + 3] = d[i + 3] < 128 ? 0 : 255; if (d[i + 3]) px.push(d[i], d[i + 1], d[i + 2]); }
  const pal = kmeans(px, colors);
  for (let i = 0; i < d.length; i += 4) { if (!d[i + 3]) continue; let m = Infinity, b = pal[0]; for (const p of pal) { const dr = d[i] - p[0], dg = d[i + 1] - p[1], db = d[i + 2] - p[2]; const dd = dr * dr + dg * dg + db * db; if (dd < m) { m = dd; b = p; } } d[i] = b[0]; d[i + 1] = b[1]; d[i + 2] = b[2]; }
  x.putImageData(id, 0, 0); return c;
}
function periodicNoise(n, seed) { // ruido de valor periódico (n celdas por tile), continuo entre tiles
  const g = []; let s = seed >>> 0; const rnd = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
  for (let i = 0; i < n * n; i++) g.push(rnd());
  const f = (t) => t * t * (3 - 2 * t);
  return (u, v) => { const x = u * n, y = v * n, x0 = Math.floor(x), y0 = Math.floor(y), fx = f(x - x0), fy = f(y - y0);
    const G = (i, j) => g[((j % n + n) % n) * n + ((i % n + n) % n)];
    const a = G(x0, y0) + (G(x0 + 1, y0) - G(x0, y0)) * fx, b = G(x0, y0 + 1) + (G(x0 + 1, y0 + 1) - G(x0, y0 + 1)) * fx; return a + (b - a) * fy; };
}
function texPixels(img, T) {
  const c = document.createElement('canvas'); c.width = c.height = T; const x = c.getContext('2d'); x.imageSmoothingQuality = 'high'; x.drawImage(img, 0, 0, T, T);
  const d = x.getImageData(0, 0, T, T).data, o = new Uint8ClampedArray(d.length), H = T >> 1;
  // fuerza la textura a ser tileable: mezcla con una copia desplazada medio tile (su costura queda en el centro) cerca de los bordes
  for (let y = 0; y < T; y++) for (let xx = 0; xx < T; xx++) {
    const e = Math.min(xx, T - 1 - xx, y, T - 1 - y) / (T * 0.22), w = Math.min(1, e);
    const i = (y * T + xx) * 4, j = (((y + H) % T) * T + (xx + H) % T) * 4;
    for (let k = 0; k < 4; k++) o[i + k] = d[i + k] * w + d[j + k] * (1 - w);
  }
  return o;
}
function buildAutotile(imgA, imgB, T, mode) {
  const A = texPixels(imgA, T), B = texPixels(imgB, T);
  const n1 = periodicNoise(3, 7), n2 = periodicNoise(7, 19);
  const out = document.createElement('canvas'); out.width = out.height = T * 4; const ox = out.getContext('2d'); const id = ox.createImageData(T * 4, T * 4); const D = id.data;
  const mask = (c, u, v) => { const w = (c[0] * (1 - u) + c[1] * u) * (1 - v) + (c[3] * (1 - u) + c[2] * u) * v;
    return w + ((n1(u, v) - 0.5) * 0.42 + (n2(u, v) - 0.5) * 0.16) * Math.min(1, 4 * w * (1 - w) + 0.15); };
  for (let i = 0; i < 16; i++) {
    const c = [i & 1, (i >> 1) & 1, (i >> 2) & 1, (i >> 3) & 1].map(Number); // TL, TR, BR, BL (1 = terreno B)
    const tx = (i % 4) * T, ty = Math.floor(i / 4) * T;
    const M = new Float32Array(T * T);
    for (let y = 0; y < T; y++) for (let x = 0; x < T; x++) M[y * T + x] = mask(c, (x + 0.5) / T, (y + 0.5) / T);
    for (let y = 0; y < T; y++) for (let x = 0; x < T; x++) {
      const m = M[y * T + x], k = (y * T + x) * 4, o = ((ty + y) * T * 4 + tx + x) * 4;
      let t, shade = 1;
      if (mode === 'pixel') {
        t = m >= 0.5 ? 1 : 0;
        if (t) { const nb = [[1, 0], [-1, 0], [0, 1], [0, -1]].some(([dx, dy]) => { const X = x + dx, Y = y + dy; return X >= 0 && Y >= 0 && X < T && Y < T && M[Y * T + X] < 0.5; }); if (nb) shade = 0.45; }
        else if (m > 0.5 - 1.6 / T) shade = 0.72; // sombra de contacto en el lado A
      } else {
        const e = 0.06; t = Math.max(0, Math.min(1, (m - 0.5 + e) / (2 * e))); t = t * t * (3 - 2 * t);
        const edge = Math.max(0, 1 - Math.abs(m - 0.5) / 0.14); shade = 1 - 0.28 * edge * (m < 0.5 ? 1 : 0.4);
      }
      for (let ch = 0; ch < 3; ch++) D[o + ch] = Math.max(0, Math.min(255, (A[k + ch] * (1 - t) + B[k + ch] * t) * shade));
      D[o + 3] = 255;
    }
  }
  ox.putImageData(id, 0, 0); return out;
}
function autotilePreview(sheet, T, cols = 14, rows = 9) {
  const V = []; for (let j = 0; j <= rows; j++) for (let i = 0; i <= cols; i++) { const d = Math.hypot(i - cols / 2, (j - rows / 2) * 1.4); const d2 = Math.hypot(i - cols * 0.18, (j - rows * 0.2) * 1.3); V.push(d < 3.2 + Math.sin(i * 1.7 + j) * 0.9 || d2 < 1.6 ? 1 : 0); }
  const P = document.createElement('canvas'); P.width = cols * T; P.height = rows * T; const px = P.getContext('2d'); px.imageSmoothingEnabled = false;
  const at = (i, j) => V[j * (cols + 1) + i];
  for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) { const idx = at(i, j) | at(i + 1, j) << 1 | at(i + 1, j + 1) << 2 | at(i, j + 1) << 3; px.drawImage(sheet, (idx % 4) * T, Math.floor(idx / 4) * T, T, T, i * T, j * T, T, T); }
  return P;
}
function tilesetTSX(name, png, T, nameA, nameB) {
  let w = ''; for (let i = 0; i < 16; i++) { const c = [i & 1, (i >> 1) & 1, (i >> 2) & 1, (i >> 3) & 1].map((v) => v + 1); w += `   <wangtile tileid="${i}" wangid="0,${c[1]},0,${c[2]},0,${c[3]},0,${c[0]}"/>\n`; }
  return `<?xml version="1.0" encoding="UTF-8"?>\n<tileset version="1.10" tiledversion="1.11.0" name="${name}" tilewidth="${T}" tileheight="${T}" tilecount="16" columns="4">\n <image source="${png}" width="${T * 4}" height="${T * 4}"/>\n <wangsets>\n  <wangset name="${name}" type="corner" tile="-1">\n   <wangcolor name="${nameA}" color="#4a8f3c" tile="0" probability="1"/>\n   <wangcolor name="${nameB}" color="#a5773f" tile="15" probability="1"/>\n${w}  </wangset>\n </wangsets>\n</tileset>\n`;
}
function tilesetTRES(png, T, nameA, nameB) {
  const bits = ['top_left_corner', 'top_right_corner', 'bottom_right_corner', 'bottom_left_corner'];
  let t = '';
  for (let i = 0; i < 16; i++) { const c = [i & 1, (i >> 1) & 1, (i >> 2) & 1, (i >> 3) & 1]; const k = `${i % 4}:${Math.floor(i / 4)}/0`;
    t += `${k} = 0\n${k}/terrain_set = 0\n${k}/terrain = ${c.reduce((a, b) => a + b, 0) >= 2 ? 1 : 0}\n` + bits.map((b, j) => `${k}/terrains_peering_bit/${b} = ${c[j]}\n`).join(''); }
  return `[gd_resource type="TileSet" load_steps=3 format=3]\n\n[ext_resource type="Texture2D" path="${png}" id="1_tex"]\n\n[sub_resource type="TileSetAtlasSource" id="TileSetAtlasSource_1"]\ntexture = ExtResource("1_tex")\ntexture_region_size = Vector2i(${T}, ${T})\n${t}\n[resource]\ntile_size = Vector2i(${T}, ${T})\nterrain_set_0/mode = 1\nterrain_set_0/terrain_0/name = "${nameA}"\nterrain_set_0/terrain_0/color = Color(0.29, 0.56, 0.24, 1)\nterrain_set_0/terrain_1/name = "${nameB}"\nterrain_set_0/terrain_1/color = Color(0.65, 0.47, 0.25, 1)\nsources/0 = SubResource("TileSetAtlasSource_1")\n`;
}

// ───────── Normal maps para iluminación 2D (Godot CanvasTexture, Unity Sprite Lit) ─────────
// Altura = bisel desde el borde del sprite (alfa difuminado) + detalle por luminancia. Convención OpenGL (verde = arriba).
function normalMapCanvas(src, { strength = 2.2, bevel = 1.0, detail = 0.6 } = {}) {
  const w = src.width, h = src.height, d = src.getContext('2d', { willReadFrequently: true }).getImageData(0, 0, w, h).data;
  const A = new Float32Array(w * h), Lm = new Float32Array(w * h);
  for (let p = 0; p < w * h; p++) { A[p] = d[p * 4 + 3] / 255; Lm[p] = (0.299 * d[p * 4] + 0.587 * d[p * 4 + 1] + 0.114 * d[p * 4 + 2]) / 255; }
  const blur = (src_, r) => { // caja separable, dos pasadas ≈ gaussiana
    let a = src_, b = new Float32Array(w * h);
    for (let pass = 0; pass < 2; pass++) {
      for (let y = 0; y < h; y++) { let acc = 0; for (let x = -r; x <= r; x++) acc += a[y * w + Math.min(w - 1, Math.max(0, x))]; for (let x = 0; x < w; x++) { b[y * w + x] = acc / (2 * r + 1); acc += a[y * w + Math.min(w - 1, x + r + 1)] - a[y * w + Math.max(0, x - r)]; } }
      const c = new Float32Array(w * h);
      for (let x = 0; x < w; x++) { let acc = 0; for (let y = -r; y <= r; y++) acc += b[Math.min(h - 1, Math.max(0, y)) * w + x]; for (let y = 0; y < h; y++) { c[y * w + x] = acc / (2 * r + 1); acc += b[Math.min(h - 1, y + r + 1) * w + x] - b[Math.max(0, y - r) * w + x]; } }
      a = c;
    }
    return a;
  };
  const r = Math.max(1, Math.round(Math.min(w, h) * 0.035));
  const B = blur(A, r), Ld = blur(Lm, 1);
  const H = new Float32Array(w * h);
  for (let p = 0; p < w * h; p++) H[p] = (B[p] * bevel + Ld[p] * detail) * A[p];
  const out = document.createElement('canvas'); out.width = w; out.height = h;
  const ox = out.getContext('2d'); const id = ox.createImageData(w, h), o = id.data;
  const at = (x, y) => H[Math.min(h - 1, Math.max(0, y)) * w + Math.min(w - 1, Math.max(0, x))];
  const k = strength * Math.max(1, Math.min(w, h) / 64);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const p = y * w + x;
    const dx = (at(x + 1, y - 1) + 2 * at(x + 1, y) + at(x + 1, y + 1)) - (at(x - 1, y - 1) + 2 * at(x - 1, y) + at(x - 1, y + 1));
    const dy = (at(x - 1, y + 1) + 2 * at(x, y + 1) + at(x + 1, y + 1)) - (at(x - 1, y - 1) + 2 * at(x, y - 1) + at(x + 1, y - 1));
    let nx = -dx * k, ny = dy * k, nz = 1; const l = Math.hypot(nx, ny, nz); nx /= l; ny /= l; nz /= l;
    o[p * 4] = (nx * 0.5 + 0.5) * 255; o[p * 4 + 1] = (ny * 0.5 + 0.5) * 255; o[p * 4 + 2] = (nz * 0.5 + 0.5) * 255; o[p * 4 + 3] = d[p * 4 + 3];
  }
  ox.putImageData(id, 0, 0); return out;
}
// Vista previa de luz: el color del sprite iluminado por una luz puntual en (lx, ly) (coordenadas del sprite) con su normal map.
function litPreview(color, normal, lx, ly, { height = 0.45, ambient = 0.32, tint = [1, 0.86, 0.66] } = {}) {
  const w = color.width, h = color.height;
  const c = color.getContext('2d', { willReadFrequently: true }).getImageData(0, 0, w, h).data;
  const n = normal.getContext('2d', { willReadFrequently: true }).getImageData(0, 0, w, h).data;
  const out = document.createElement('canvas'); out.width = w; out.height = h; const ox = out.getContext('2d'); const id = ox.createImageData(w, h), o = id.data;
  const zl = Math.max(w, h) * height;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4; if (!c[i + 3]) continue;
    const nx = n[i] / 127.5 - 1, ny = n[i + 1] / 127.5 - 1, nz = n[i + 2] / 127.5 - 1;
    let Lx = lx - x, Ly = -(ly - y), Lz = zl; const dist = Math.hypot(Lx, Ly, Lz); Lx /= dist; Ly /= dist; Lz /= dist;
    const att = 1 / (1 + (dist / (Math.max(w, h) * 1.4)) ** 2);
    const diff = Math.max(0, nx * Lx + ny * Ly + nz * Lz) * att * 1.7;
    for (let k = 0; k < 3; k++) o[i + k] = Math.min(255, c[i + k] * (ambient + diff * tint[k]));
    o[i + 3] = c[i + 3];
  }
  ox.putImageData(id, 0, 0); return out;
}

// ───────── Paleta única para un pack: todos los sprites comparten exactamente los mismos colores ─────────
function unifyPalette(canvases, k = 24) {
  const px = [];
  for (const cv_ of canvases) {
    const d = cv_.getContext('2d', { willReadFrequently: true }).getImageData(0, 0, cv_.width, cv_.height).data;
    const step = Math.max(1, Math.floor((cv_.width * cv_.height) / 40000));
    for (let p = 0; p < cv_.width * cv_.height; p += step) { const i = p * 4; if (d[i + 3] > 127) px.push(d[i], d[i + 1], d[i + 2]); }
  }
  const pal = kmeans(px, k);
  const out = canvases.map((cv_) => {
    const c = document.createElement('canvas'); c.width = cv_.width; c.height = cv_.height; const x = c.getContext('2d', { willReadFrequently: true });
    x.drawImage(cv_, 0, 0); const id = x.getImageData(0, 0, c.width, c.height), d = id.data;
    for (let i = 0; i < d.length; i += 4) { if (d[i + 3] < 128) { d[i + 3] = 0; continue; } d[i + 3] = 255; let m = Infinity, b = pal[0]; for (const p of pal) { const dr = d[i] - p[0], dg = d[i + 1] - p[1], db = d[i + 2] - p[2]; const dd = dr * dr * 0.3 + dg * dg * 0.59 + db * db * 0.11; if (dd < m) { m = dd; b = p; } } d[i] = b[0]; d[i + 1] = b[1]; d[i + 2] = b[2]; }
    x.putImageData(id, 0, 0); return c;
  });
  return { palette: pal, canvases: out };
}
function paletteStrip(pal, sw = 16) { const c = document.createElement('canvas'); c.width = pal.length * sw; c.height = sw; const x = c.getContext('2d'); pal.forEach((p, i) => { x.fillStyle = `rgb(${p[0]},${p[1]},${p[2]})`; x.fillRect(i * sw, 0, sw, sw); }); return c; }

// ───────── Pintor de mapas con autotiles (terreno por esquinas) ─────────
// El mapa guarda un valor por vértice (0 = terreno A, 1 = terreno B); cada celda elige su tile por sus 4 esquinas.
class MapPainter {
  constructor(canvas, sheet, T, { cols = 40, rows = 24, zoom = 1, onChange } = {}) {
    Object.assign(this, { canvas, sheet, T, cols, rows, zoom, onChange, brush: 1, value: 1 });
    this.V = new Uint8Array((cols + 1) * (rows + 1));
    this.hist = []; this.down = false;
    const pos = (e) => { const r = canvas.getBoundingClientRect(); return [(e.clientX - r.left) / r.width * this.cols, (e.clientY - r.top) / r.height * this.rows]; };
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    canvas.addEventListener('pointerdown', (e) => { this.down = true; this.paintValue = e.button === 2 || e.shiftKey ? 1 - this.value : this.value; this.hist.push(this.V.slice()); if (this.hist.length > 40) this.hist.shift(); canvas.setPointerCapture(e.pointerId); this.stroke(...pos(e)); });
    canvas.addEventListener('pointermove', (e) => { this.hover = pos(e); if (this.down) this.stroke(...this.hover); else this.render(); });
    canvas.addEventListener('pointerup', () => { this.down = false; this.onChange && this.onChange(); });
    canvas.addEventListener('pointerleave', () => { this.hover = null; this.render(); });
    this.resize(cols, rows);
  }
  resize(cols, rows) {
    const old = this.V, oc = this.cols; this.cols = cols; this.rows = rows; this.V = new Uint8Array((cols + 1) * (rows + 1));
    if (old) for (let j = 0; j <= rows; j++) for (let i = 0; i <= cols; i++) { if (i <= oc && j * (oc + 1) + i < old.length) this.V[j * (cols + 1) + i] = old[j * (oc + 1) + i]; }
    this.canvas.width = cols * this.T; this.canvas.height = rows * this.T; this.render();
  }
  v(i, j) { return this.V[j * (this.cols + 1) + i]; }
  stroke(x, y) {
    const r = this.brush - 0.5;
    for (let j = Math.floor(y - r - 1); j <= Math.ceil(y + r + 1); j++) for (let i = Math.floor(x - r - 1); i <= Math.ceil(x + r + 1); i++) {
      if (i < 0 || j < 0 || i > this.cols || j > this.rows) continue;
      if (Math.hypot(i - x, j - y) <= r + 0.5) this.V[j * (this.cols + 1) + i] = this.paintValue;
    }
    this.render();
  }
  fill(v) { this.hist.push(this.V.slice()); this.V.fill(v); this.render(); }
  random(seed = 1) {
    this.hist.push(this.V.slice()); const n = periodicNoise(6, seed), n2 = periodicNoise(13, seed + 7);
    for (let j = 0; j <= this.rows; j++) for (let i = 0; i <= this.cols; i++) this.V[j * (this.cols + 1) + i] = n(i / this.cols, j / this.rows) * 0.75 + n2(i / this.cols, j / this.rows) * 0.25 > 0.52 ? 1 : 0;
    this.render();
  }
  undo() { const h = this.hist.pop(); if (h) { this.V = h; this.render(); } }
  idx(i, j) { return this.v(i, j) | this.v(i + 1, j) << 1 | this.v(i + 1, j + 1) << 2 | this.v(i, j + 1) << 3; }
  render(target = this.canvas, grid = true) {
    const x = target.getContext('2d'); x.imageSmoothingEnabled = false; const T = this.T;
    for (let j = 0; j < this.rows; j++) for (let i = 0; i < this.cols; i++) { const k = this.idx(i, j); x.drawImage(this.sheet, (k % 4) * T, Math.floor(k / 4) * T, T, T, i * T, j * T, T, T); }
    if (grid && this.hover && target === this.canvas) {
      x.strokeStyle = 'rgba(255,255,255,.85)'; x.lineWidth = Math.max(1, T / 16); x.beginPath();
      x.arc(this.hover[0] * T, this.hover[1] * T, (this.brush) * T, 0, Math.PI * 2); x.stroke();
    }
  }
  toCanvas() { const c = document.createElement('canvas'); c.width = this.cols * this.T; c.height = this.rows * this.T; this.render(c, false); return c; }
  toTMX(tsx) {
    const rows = []; for (let j = 0; j < this.rows; j++) { const r = []; for (let i = 0; i < this.cols; i++) r.push(this.idx(i, j) + 1); rows.push(r.join(',')); }
    return `<?xml version="1.0" encoding="UTF-8"?>\n<map version="1.10" tiledversion="1.11.0" orientation="orthogonal" renderorder="right-down" width="${this.cols}" height="${this.rows}" tilewidth="${this.T}" tileheight="${this.T}" infinite="0" nextlayerid="2" nextobjectid="1">\n <tileset firstgid="1" source="${tsx}"/>\n <layer id="1" name="Terreno" width="${this.cols}" height="${this.rows}">\n  <data encoding="csv">\n${rows.join(',\n')}\n</data>\n </layer>\n</map>\n`;
  }
  toTSCN(tres) {
    const d = []; for (let j = 0; j < this.rows; j++) for (let i = 0; i < this.cols; i++) { const k = this.idx(i, j); d.push((j << 16) | (i & 0xffff), 0 | ((k % 4) << 16), Math.floor(k / 4)); }
    return `[gd_scene load_steps=2 format=3]\n\n[ext_resource type="TileSet" path="${tres}" id="1_ts"]\n\n[node name="Mapa" type="TileMap"]\ntile_set = ExtResource("1_ts")\nformat = 2\nlayer_0/name = "Terreno"\nlayer_0/tile_data = PackedInt32Array(${d.join(', ')})\n`;
  }
  toJSON() { return JSON.stringify({ cols: this.cols, rows: this.rows, tile: this.T, corners: Array.from(this.V) }); }
}
