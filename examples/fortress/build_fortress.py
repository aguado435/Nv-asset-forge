"""
Bastión de Piedrahonda · kit modular de fortaleza de montaña (estilo 2D-HD)
==========================================================================
Fortaleza original encajada en un desfiladero, construida con MÓDULOS reutilizables:
muro, torre, puerta, torreón, casa, rampa, escalera, roca y props. Cada módulo es
una colección con el pivote en la base que se exporta por separado (GLB + FBX) y se
coloca en el mundo como instancia, igual que en un motor de juego.

Técnica "low poly que parece muy detallado":
  · geometría simple (cajas, prismas, rocas facetadas)
  · imágenes 2D muy detalladas (FLUX.2) proyectadas encima: fachadas por cara (UV
    automáticas) y texturas tileables con proyección en caja
  · shaders que fingen detalle: oclusión ambiental en el color, brillo en aristas
    (Pointiness), suciedad/musgo en la base, bump desde la luminancia, mezcla
    roca/hierba según la normal
  · billboards 2D (soldados, arqueros, estandartes, pinos) con Alpha Clip y sombra
  · cámara tilt-shift de maqueta y postproceso (Glare + viñeta)

Uso:
  blender -b -P build_fortress.py -- [--res 1600x900] [--samples 64] [--shot hero|gate|keep]
         [--pixel] [--export-modules] [--module-previews] [--out render.png]
"""
import math
import os
import random
import sys

import bpy
import bmesh
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = {"img": os.path.join(HERE, "images"), "res": (1600, 900), "samples": 64, "shot": "hero",
       "pixel": False, "export": False, "previews": False, "out": os.path.join(HERE, "render_fortress.png"),
       "scale": 0.02, "engine": "CYCLES", "render": True}
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
for i, a in enumerate(argv):
    if a == "--res": CFG["res"] = tuple(int(v) for v in argv[i + 1].split("x"))
    if a == "--samples": CFG["samples"] = int(argv[i + 1])
    if a == "--shot": CFG["shot"] = argv[i + 1]
    if a == "--out": CFG["out"] = argv[i + 1]
    if a == "--engine": CFG["engine"] = argv[i + 1].upper()
    if a == "--pixel": CFG["pixel"] = True
    if a == "--export-modules": CFG["export"] = True
    if a == "--module-previews": CFG["previews"] = True
    if a == "--no-render": CFG["render"] = False
if not bpy.app.background:
    CFG["render"] = False
S = CFG["scale"]
rnd = random.Random(42)
B42 = bpy.app.version >= (4, 2, 0)


def log(m):
    print("FORT:", m, flush=True)


# ───────────────────────── imágenes y materiales "de detalle" ─────────────────────────
IMGS = {}


def image(key):
    if key not in IMGS:
        p = os.path.join(CFG["img"], key + ".png")
        im = bpy.data.images.load(p, check_existing=True) if os.path.exists(p) else None
        if im is not None and CFG["pixel"]:  # modo 2D-HD: menos resolución + Closest
            w, h = im.size
            k = 192 / max(w, h)
            im.scale(max(8, int(w * k)), max(8, int(h * k)))
        IMGS[key] = im
    return IMGS[key]


def _interp(t):
    t.interpolation = "Closest" if CFG["pixel"] else "Linear"


def bsdf_in(b, *names):
    for n in names:
        if n in b.inputs:
            return b.inputs[n]


def detail_mat(name, key, mode="box", repeat=0.25, rough=0.8, ao=0.55, edge=0.18, grime=1.2,
               grass_key=None, emission_boost=0.0, metal=0.0, tint=None):
    """Material que finge detalle sobre geometría simple.
    mode="box": textura tileable con proyección en caja (Object coords) · mode="uv": imagen por cara (fachadas)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    L = nt.links.new
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    tc = nt.nodes.new("ShaderNodeTexCoord")
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = image(key)
    _interp(t)
    if mode == "box":
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (repeat,) * 3
        L(tc.outputs["Object"], mp.inputs["Vector"])
        L(mp.outputs["Vector"], t.inputs["Vector"])
        t.projection = "BOX"
        t.projection_blend = 0.15
    else:
        t.extension = "EXTEND"
        L(tc.outputs["UV"], t.inputs["Vector"])
    col = t.outputs["Color"]
    if tint:
        mt = nt.nodes.new("ShaderNodeMix"); mt.data_type = "RGBA"; mt.blend_type = "MULTIPLY"
        mt.inputs[0].default_value = 1.0; L(col, mt.inputs[6]); mt.inputs[7].default_value = tuple(tint) + (1,)
        col = mt.outputs[2]
    # mezcla roca/hierba según la normal (las caras horizontales se cubren de hierba)
    if grass_key:
        g = nt.nodes.new("ShaderNodeTexImage"); g.image = image(grass_key); _interp(g)
        gm = nt.nodes.new("ShaderNodeMapping"); gm.inputs["Scale"].default_value = (repeat * 1.5,) * 3
        L(tc.outputs["Object"], gm.inputs["Vector"]); L(gm.outputs["Vector"], g.inputs["Vector"])
        g.projection = "BOX"
        geo = nt.nodes.new("ShaderNodeNewGeometry")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ"); L(geo.outputs["Normal"], sep.inputs[0])
        mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 0.55; mr.inputs["From Max"].default_value = 0.8
        L(sep.outputs["Z"], mr.inputs["Value"])
        mg = nt.nodes.new("ShaderNodeMix"); mg.data_type = "RGBA"
        L(mr.outputs[0], mg.inputs[0]); L(col, mg.inputs[6]); L(g.outputs["Color"], mg.inputs[7])
        col = mg.outputs[2]
    # suciedad / musgo en la base (gradiente en Z de objeto)
    if grime:
        sz = nt.nodes.new("ShaderNodeSeparateXYZ"); L(tc.outputs["Object"], sz.inputs[0])
        gr = nt.nodes.new("ShaderNodeMapRange"); gr.inputs["From Min"].default_value = 0.0; gr.inputs["From Max"].default_value = grime
        gr.inputs["To Min"].default_value = 0.45; gr.inputs["To Max"].default_value = 0.0
        L(sz.outputs["Z"], gr.inputs["Value"])
        mm = nt.nodes.new("ShaderNodeMix"); mm.data_type = "RGBA"; mm.blend_type = "MULTIPLY"
        L(gr.outputs[0], mm.inputs[0]); L(col, mm.inputs[6]); mm.inputs[7].default_value = (0.32, 0.38, 0.22, 1)
        col = mm.outputs[2]
    # oclusión ambiental "pintada" en el color (rincones y juntas más oscuros)
    if ao:
        aon = nt.nodes.new("ShaderNodeAmbientOcclusion"); aon.inputs["Distance"].default_value = 1.2 * S
        L(col, aon.inputs["Color"])
        ma = nt.nodes.new("ShaderNodeMix"); ma.data_type = "RGBA"; ma.blend_type = "MULTIPLY"
        ma.inputs[0].default_value = ao
        L(col, ma.inputs[6]); L(aon.outputs["AO"], ma.inputs[7])
        col = ma.outputs[2]
    # brillo en aristas (Pointiness, solo Cycles): bordes gastados más claros
    if edge:
        geo2 = nt.nodes.new("ShaderNodeNewGeometry")
        pr = nt.nodes.new("ShaderNodeMapRange"); pr.inputs["From Min"].default_value = 0.52; pr.inputs["From Max"].default_value = 0.6
        L(geo2.outputs["Pointiness"], pr.inputs["Value"])
        sc = nt.nodes.new("ShaderNodeMath"); sc.operation = "MULTIPLY"; sc.inputs[1].default_value = edge
        L(pr.outputs[0], sc.inputs[0])
        me = nt.nodes.new("ShaderNodeMix"); me.data_type = "RGBA"; me.blend_type = "SCREEN"
        L(sc.outputs[0], me.inputs[0]); L(col, me.inputs[6]); me.inputs[7].default_value = (1, 0.95, 0.85, 1)
        col = me.outputs[2]
    L(col, b.inputs["Base Color"])
    # relieve a partir de la luminancia de la imagen
    bw = nt.nodes.new("ShaderNodeRGBToBW"); L(t.outputs["Color"], bw.inputs[0])
    bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.45; bp.inputs["Distance"].default_value = 0.05 * S
    L(bw.outputs[0], bp.inputs["Height"]); L(bp.outputs["Normal"], b.inputs["Normal"])
    # las ventanas iluminadas de las fachadas emiten (píxeles cálidos y brillantes)
    if emission_boost:
        sep = nt.nodes.new("ShaderNodeSeparateColor"); L(t.outputs["Color"], sep.inputs[0])
        d = nt.nodes.new("ShaderNodeMath"); d.operation = "SUBTRACT"; L(sep.outputs[0], d.inputs[0]); L(sep.outputs[2], d.inputs[1])
        k = nt.nodes.new("ShaderNodeMapRange"); k.inputs["From Min"].default_value = 0.35; k.inputs["From Max"].default_value = 0.6
        L(d.outputs[0], k.inputs["Value"])
        mk = nt.nodes.new("ShaderNodeMath"); mk.operation = "MULTIPLY"; L(k.outputs[0], mk.inputs[0]); L(bw.outputs[0], mk.inputs[1])
        L(t.outputs["Color"], bsdf_in(b, "Emission Color", "Emission"))
        L(mk.outputs[0], b.inputs["Emission Strength"])
        st = nt.nodes.new("ShaderNodeMath"); st.operation = "MULTIPLY"; st.inputs[1].default_value = emission_boost
        L(mk.outputs[0], st.inputs[0]); L(st.outputs[0], b.inputs["Emission Strength"])
    return m


def water_mat(name, color, rough, foam=0.0):
    """Agua: muy brillante, bump de olas; foam > 0 añade vetas verticales de espuma (cascada)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; L = nt.links.new
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = tuple(color) + (1,)
    b.inputs["Roughness"].default_value = rough
    b.inputs["IOR"].default_value = 1.33
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.inputs["Scale"].default_value = 0.35 if not foam else 0.8
    wv.inputs["Distortion"].default_value = 8.0
    if foam:
        wv.bands_direction = "X"
        n = nt.nodes.new("ShaderNodeTexNoise"); n.inputs["Scale"].default_value = 0.6
        mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (2.5, 1.0, 0.08)
        L(tc.outputs["Object"], mp.inputs["Vector"]); L(mp.outputs["Vector"], n.inputs["Vector"])
        mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 0.45; mr.inputs["From Max"].default_value = 0.65
        L(n.outputs["Fac"], mr.inputs["Value"])
        mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"
        L(mr.outputs[0], mx.inputs[0]); mx.inputs[6].default_value = tuple(color) + (1,); mx.inputs[7].default_value = (0.95, 0.98, 1.0, 1)
        L(mx.outputs[2], b.inputs["Base Color"])
        L(mx.outputs[2], bsdf_in(b, "Emission Color", "Emission")); b.inputs["Emission Strength"].default_value = 0.25
    L(tc.outputs["Object"], wv.inputs["Vector"])
    bp = nt.nodes.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.3; bp.inputs["Distance"].default_value = 0.1 * S
    L(wv.outputs["Fac"], bp.inputs["Height"]); L(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def flat(name, color, rough=0.6, metal=0.0, emission=None, strength=8.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = tuple(color) + (1,)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emission:
        bsdf_in(b, "Emission Color", "Emission").default_value = tuple(emission) + (1,)
        b.inputs["Emission Strength"].default_value = strength
    return m


def sprite_mat(key):
    m = bpy.data.materials.new("SPR_" + key)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage"); t.image = image(key); _interp(t); t.extension = "CLIP"
    if key.startswith("px_"):
        t.interpolation = "Closest"   # pixel art nítido siempre
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    c = nt.nodes.new("ShaderNodeMath"); c.operation = "GREATER_THAN"; c.inputs[1].default_value = 0.5
    nt.links.new(t.outputs["Alpha"], c.inputs[0]); nt.links.new(c.outputs[0], b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = 0.85
    if B42:
        m.surface_render_method = "DITHERED"
    else:
        m.blend_method = "CLIP"; m.shadow_method = "CLIP"
    return m


# ───────────────────────── primitivas con UV de fachada ─────────────────────────
def facade_box(name, size, mats, faces=None, origin_bottom=True):
    """Caja low poly. mats: lista de materiales. faces: dict dirección→índice de material
    ('front' -Y, 'back' +Y, 'left' -X, 'right' +X, 'top', 'bottom'). UV 0..1 por cara lateral."""
    faces = faces or {}
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if origin_bottom:
        bmesh.ops.translate(bm, vec=Vector((0, 0, size[2] / 2)), verts=bm.verts)
    uv = bm.loops.layers.uv.new("UVMap")
    hx, hy = size[0] / 2, size[1] / 2
    z0 = 0 if origin_bottom else -size[2] / 2
    for f in bm.faces:
        n = f.normal
        key = "top" if n.z > 0.5 else "bottom" if n.z < -0.5 else ("front" if n.y < -0.5 else "back" if n.y > 0.5 else "left" if n.x < -0.5 else "right")
        f.material_index = faces.get(key, 0)
        for l in f.loops:
            co = l.vert.co
            if key in ("front", "back"):
                u = (co.x + hx) / size[0]
                u = u if key == "front" else 1 - u
                l[uv].uv = (u, (co.z - z0) / size[2])
            elif key in ("left", "right"):
                u = (co.y + hy) / size[1]
                u = 1 - u if key == "left" else u
                l[uv].uv = (u, (co.z - z0) / size[2])
            else:
                l[uv].uv = ((co.x + hx) / size[0], (co.y + hy) / size[1])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    o = bpy.data.objects.new(name, me)
    bv = o.modifiers.new("Bevel", "BEVEL"); bv.width = 0.06; bv.segments = 1; bv.limit_method = "ANGLE"
    return o


def prism_roof(name, w, d, h, mat, overhang=0.4):
    bm = bmesh.new()
    W, D = w / 2 + overhang, d / 2 + overhang
    v = [bm.verts.new(p) for p in [(-W, -D, 0), (W, -D, 0), (0, -D, h), (-W, D, 0), (W, D, 0), (0, D, h)]]
    for f in [(v[0], v[1], v[2]), (v[5], v[4], v[3]), (v[0], v[2], v[5], v[3]), (v[1], v[4], v[5], v[2]), (v[0], v[3], v[4], v[1])]:
        bm.faces.new(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    s = o.modifiers.new("Solid", "SOLIDIFY"); s.thickness = 0.25
    return o


def pyramid(name, w, h, mat, overhang=0.4):
    bm = bmesh.new()
    W = w / 2 + overhang
    v = [bm.verts.new(p) for p in [(-W, -W, 0), (W, -W, 0), (W, W, 0), (-W, W, 0), (0, 0, h)]]
    for f in [(v[0], v[1], v[4]), (v[1], v[2], v[4]), (v[2], v[3], v[4]), (v[3], v[0], v[4]), (v[3], v[2], v[1], v[0])]:
        bm.faces.new(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(mat)
    return bpy.data.objects.new(name, me)


def rock(name, size, mat, seed=0, detail=2):
    """Roca facetada low poly (icosfera deformada) — se lee como pintada gracias al material."""
    r = random.Random(seed)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=detail, radius=1.0)
    for v in bm.verts:
        n = v.co.normalized()
        v.co = n * (1 + r.uniform(-0.18, 0.18))
        v.co.x *= size[0]; v.co.y *= size[1]; v.co.z *= size[2]
        if v.co.z < 0: v.co.z *= 0.3
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(mat)
    for p in me.polygons: p.use_smooth = False
    return bpy.data.objects.new(name, me)


def billboard(key, height):
    im = image(key)
    if im is None:
        return None
    w, h = im.size
    W = height * w / h
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in [(-W / 2, 0, 0), (W / 2, 0, 0), (W / 2, 0, height), (-W / 2, 0, height)]]
    f = bm.faces.new(vs)
    uv = bm.loops.layers.uv.new("UVMap")
    for l, c in zip(f.loops, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        l[uv].uv = c
    me = bpy.data.meshes.new("BB_" + key); bm.to_mesh(me); bm.free(); me.materials.append(sprite_mat(key))
    o = bpy.data.objects.new("BB_" + key, me)
    return o


# ───────────────────────── módulos (colecciones con pivote en la base) ─────────────────────────
MODULES = {}


def module(name):
    def deco(fn):
        def build(M):
            col = bpy.data.collections.new("MOD_" + name)
            objs = fn(M)
            for o in objs:
                if o is not None:
                    col.objects.link(o)
            MODULES[name] = col
            return col
        build.__name__ = name
        return build
    return deco


def merlons(width, depth, z, M, count=None, prefix="m"):
    """Almenas a lo largo de X en y = depth (borde exterior)."""
    out = []
    count = count or max(3, int(width / 1.6))
    step = width / count
    for k in range(count):
        o = facade_box(f"{prefix}{k}", (step * 0.55, 0.7, 1.1), [M["wall"]])
        o.location = (-width / 2 + step * (k + 0.5), depth, z)
        out.append(o)
    return out


@module("wall_segment")
def wall_segment(M):
    """Lienzo de muralla 10 m: zócalo ataludado, adarve enlosado y almenas."""
    L, H, T = 10.0, 9.0, 3.2
    base = facade_box("wall_base", (L, T + 1.2, 2.2), [M["wall"]]);
    body = facade_box("wall_body", (L, T, H), [M["wall"], M["paving"]], {"top": 1}); body.location.z = 0
    parapet = facade_box("wall_parapet", (L, 0.7, 0.9), [M["wall"]]); parapet.location = (0, -T / 2 + 0.35, H)
    walk_rail = facade_box("wall_inner_rail", (L, 0.35, 0.6), [M["wall"]]); walk_rail.location = (0, T / 2 - 0.18, H)
    return [base, body, parapet, walk_rail] + merlons(L, -T / 2 + 0.35, H + 0.9, M, prefix="wall_merlon")


@module("wall_tower")
def wall_tower(M):
    """Torre cuadrada de flanqueo con fachada pintada en las cuatro caras."""
    W, H = 6.5, 15.0
    plinth = facade_box("tower_plinth", (W + 1.2, W + 1.2, 2.5), [M["wall"]])
    body = facade_box("tower_body", (W, W, H), [M["tower"], M["paving"]], {"top": 1})
    cornice = facade_box("tower_cornice", (W + 0.6, W + 0.6, 0.6), [M["wall"]]); cornice.location.z = H
    out = [plinth, body, cornice]
    for side in range(4):
        for k in range(4):
            o = facade_box(f"tower_merlon{side}_{k}", (0.9, 0.7, 1.2), [M["wall"]])
            a = side * math.pi / 2
            off = -W / 2 - 0.3 + 0.15 + (k + 0.5) * (W + 0.6) / 4
            o.location = (math.cos(a) * off - math.sin(a) * (-(W + 0.6) / 2 + 0.35), math.sin(a) * off + math.cos(a) * (-(W + 0.6) / 2 + 0.35), H + 0.6)
            o.rotation_euler.z = a
            out.append(o)
    roof = pyramid("tower_roof", W - 1.2, 3.8, M["roof"], 0.0); roof.location.z = H + 0.6
    out.append(roof)
    return out


@module("gatehouse")
def gatehouse(M):
    """Puerta principal: dos torres, portón pintado y paso de ronda superior."""
    out = []
    for s in (-1, 1):
        t = facade_box(f"gate_tower{s}", (5.5, 6.5, 13.0), [M["tower"], M["paving"]], {"top": 1}); t.location.x = s * 5.0
        out.append(t)
        for k in range(3):
            m = facade_box(f"gate_merlon{s}{k}", (1.0, 0.7, 1.2), [M["wall"]]); m.location = (s * 5.0 - 1.8 + k * 1.8, -3.0, 13.0)
            out.append(m)
    gate = facade_box("gate_doors", (4.6, 5.0, 7.5), [M["wall"], M["gate"], M["paving"]], {"front": 1, "top": 2})
    over = facade_box("gate_over", (4.6, 5.0, 3.5), [M["wall"], M["paving"]], {"top": 1}); over.location.z = 7.5
    out += [gate, over]
    out += merlons(4.6, -2.15, 11.0, M, 3, "gate_top_merlon")
    return out


@module("keep")
def keep(M):
    """Torreón-ciudadela: bloque principal con fachada iluminada, torre alta y tejados de pizarra."""
    out = []
    main = facade_box("keep_main", (16, 11, 16), [M["wall"], M["keep"], M["paving"]], {"front": 1, "top": 2})
    out.append(main)
    roof = prism_roof("keep_roof", 16, 11, 6.5, M["roof"]); roof.location.z = 16; roof.rotation_euler.z = math.radians(90)
    out.append(roof)
    tower = facade_box("keep_tower", (6.5, 6.5, 30), [M["tower"]]); tower.location = (5.5, 3.5, 0)
    out.append(tower)
    tr = pyramid("keep_tower_roof", 6.5, 7.0, M["roof"]); tr.location = (5.5, 3.5, 30)
    out.append(tr)
    for s in (-1, 1):
        b = facade_box(f"keep_buttress{s}", (1.4, 2.0, 12), [M["wall"]]); b.location = (s * 8.6, -5.2, 0)
        out.append(b)
    steps = []
    for k in range(6):
        st = facade_box(f"keep_step{k}", (7 - k * 0.5, 1.0, 0.35 * (6 - k)), [M["paving"]]); st.location = (0, -6.0 - k * 0.9, 0)
        steps.append(st)
    return out + steps


@module("house")
def house(M):
    """Casa del burgo: fachada y laterales pintados + tejado de pizarra."""
    W, D, H = 6.0, 5.0, 5.8
    body = facade_box("house_body", (W, D, H), [M["house_side"], M["house"], M["house"]], {"front": 1, "back": 2})
    roof = prism_roof("house_roof", W, D, 3.4, M["roof"], 0.5); roof.location.z = H; roof.rotation_euler.z = math.radians(90)
    chim = facade_box("house_chimney", (0.9, 0.9, 3.4), [M["wall"]]); chim.location = (1.6, 1.0, H)
    return [body, roof, chim]


@module("ramp")
def ramp(M):
    """Rampa-calzada de acceso (20 m) con pretiles."""
    bm = bmesh.new()
    Lr, Wr, Hr = 20.0, 6.0, 4.0
    v = [bm.verts.new(p) for p in [(-Wr / 2, 0, 0), (Wr / 2, 0, 0), (Wr / 2, Lr, 0), (-Wr / 2, Lr, 0), (-Wr / 2, 0, 0.3), (Wr / 2, 0, 0.3), (Wr / 2, Lr, Hr), (-Wr / 2, Lr, Hr)]]
    for f in [(v[0], v[1], v[5], v[4]), (v[1], v[2], v[6], v[5]), (v[2], v[3], v[7], v[6]), (v[3], v[0], v[4], v[7]), (v[4], v[5], v[6], v[7]), (v[3], v[2], v[1], v[0])]:
        bm.faces.new(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("ramp"); bm.to_mesh(me); bm.free()
    me.materials.append(M["wall"]); me.materials.append(M["paving"])
    for p in me.polygons:
        p.material_index = 1 if p.normal.z > 0.5 else 0
    o = bpy.data.objects.new("ramp", me)
    out = [o]
    for s in (-1, 1):
        rail = facade_box(f"ramp_rail{s}", (0.6, Lr, 1.0), [M["wall"]]); rail.location = (s * (Wr / 2 - 0.3), Lr / 2, 0)
        rail.rotation_euler.x = math.atan2(Hr, Lr)
        rail.location.z = Hr / 2 - 0.2
        out.append(rail)
    return out


@module("cliff")
def cliff(M):
    """Macizo rocoso facetado (se escala y gira al colocarlo)."""
    return [rock("cliff_rock", (14, 10, 22), M["cliff"], seed=3, detail=3)]


@module("strata_cliff")
def strata_cliff(M):
    """Pared de abismo en estratos: losas de roca apiladas, cada una algo retranqueada y girada,
    con hierba en las cornisas. Lectura 2D-HD muy clara con poca geometría."""
    r = random.Random(11)
    out = []
    w, d, z = 18.0, 14.0, 0.0
    for k in range(7):
        h = r.uniform(4.5, 7.5)
        o = facade_box(f"stratum{k}", (w, d, h), [M["cliff" if k % 2 == 0 else "cliff_b"], M["ledge"]], {"top": 1})
        o.modifiers["Bevel"].width = 0.5; o.modifiers["Bevel"].segments = 2
        o.location = (r.uniform(-1.2, 1.2), r.uniform(0.3, 1.6) * k * 0.6, z)
        o.rotation_euler.z = math.radians(r.uniform(-6, 6))
        out.append(o)
        # bloques desprendidos y contrafuertes de roca en la cara frontal
        for j in range(1):
            b = facade_box(f"stratum{k}_spur{j}", (r.uniform(2, 4), r.uniform(2, 3.5), h * r.uniform(0.6, 1.0)), [M["cliff"], M["ledge"]], {"top": 1})
            b.location = (r.uniform(-w / 2.4, w / 2.4), o.location.y - d / 2 - 0.8, z)
            b.rotation_euler.z = math.radians(r.uniform(-15, 15))
            out.append(b)
        z += h
        w *= r.uniform(0.86, 0.94)
        d *= r.uniform(0.86, 0.95)
    return out


@module("mountain")
def mountain(M):
    """Montaña de fondo con nieve en las caras altas."""
    return [rock("mountain", (40, 30, 70), M["mountain"], seed=21, detail=2)]


@module("waterfall")
def waterfall(M):
    """Cascada: lámina de agua con vetas de espuma + poza con anillo de espuma."""
    H = 46.0
    fall = facade_box("waterfall_sheet", (12.0, 2.0, H), [M["falls"]], origin_bottom=True)
    fall.modifiers.clear()
    pool = bpy.data.objects.new("pool", None)
    bm = bmesh.new(); bmesh.ops.create_circle(bm, cap_ends=True, segments=20, radius=9.0)
    me = bpy.data.meshes.new("pool_water"); bm.to_mesh(me); bm.free(); me.materials.append(M["water"])
    pw = bpy.data.objects.new("pool_water", me); pw.location = (0, -6, 0.4)
    rim = []
    for k in range(14):
        a = k / 14 * math.tau
        b = rock(f"pool_rock{k}", (1.6, 1.3, 1.1), M["cliff"], seed=40 + k, detail=1)
        b.location = (math.cos(a) * 9.2, -6 + math.sin(a) * 9.2, 0.2)
        rim.append(b)
    return [fall, pw] + rim


@module("stream")
def stream(M):
    """Tramo de arroyo de 10 m: cauce de piedra con agua (encadenable)."""
    bed = facade_box("stream_bed", (4.6, 10.0, 0.8), [M["cliff"]])
    water = facade_box("stream_water", (3.6, 10.0, 0.1), [M["water"]]); water.location.z = 0.62; water.modifiers.clear()
    banks = []
    for s in (-1, 1):
        bk = facade_box(f"stream_bank{s}", (0.6, 10.0, 1.0), [M["wall"]]); bk.location.x = s * 2.0
        banks.append(bk)
    return [bed, water] + banks


@module("boulder")
def boulder(M):
    return [rock("boulder", (2.2, 1.8, 1.6), M["cliff"], seed=9, detail=1)]


def voxel_field(name, x0, x1, y0, y1, cell, height_fn, side_mat, top_mat, base=-3.0):
    """Terreno de cubos en una sola malla: cada celda es una columna con tapa de hierba.
    Barato de renderizar y con la lectura escalonada de los fondos 2D-HD."""
    bm = bmesh.new()
    nx, ny = int((x1 - x0) / cell), int((y1 - y0) / cell)
    for i in range(nx):
        for j in range(ny):
            x, y = x0 + (i + 0.5) * cell, y0 + (j + 0.5) * cell
            h = height_fn(x, y)
            if h is None:
                continue
            res = bmesh.ops.create_cube(bm, size=1.0)
            vs = res["verts"]
            bmesh.ops.scale(bm, vec=Vector((cell, cell, h - base)), verts=vs)
            bmesh.ops.translate(bm, vec=Vector((x, y, base + (h - base) / 2)), verts=vs)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
    for f in bm.faces:
        f.material_index = 1 if f.normal.z > 0.5 else 0
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(side_mat); me.materials.append(top_mat)
    return bpy.data.objects.new(name, me)


# ───────────────────────── montaje del mundo con instancias ─────────────────────────
PLACED = []


def place(mod, loc, rot=0.0, scale=1.0):
    e = bpy.data.objects.new(f"{mod}_{len(PLACED)}", None)
    e.instance_type = "COLLECTION"
    e.instance_collection = MODULES[mod]
    e.location = loc
    e.rotation_euler.z = math.radians(rot)
    e.scale = (scale,) * 3 if isinstance(scale, (int, float)) else scale
    bpy.context.scene.collection.objects.link(e)
    PLACED.append(e)
    return e


SPRITES = []


def sprite(key, loc, height):
    o = billboard(key, height)
    if o is None:
        return
    o.location = loc
    bpy.context.scene.collection.objects.link(o)
    SPRITES.append(o)
    PLACED.append(o)


def torch(loc, power=900.0):
    d = bpy.data.lights.new("torch", "POINT"); d.color = (1.0, 0.55, 0.22); d.energy = power * S * S; d.shadow_soft_size = 0.15 * S
    o = bpy.data.objects.new("torch", d); o.location = loc
    bpy.context.scene.collection.objects.link(o); PLACED.append(o)
    f = bpy.data.objects.new("torch_flame", None)


def assemble(M):
    # suelo del valle y del patio
    ground = facade_box("valley_ground", (300, 300, 1), [M["ground"]]); ground.location = (0, 60, -4)
    bpy.context.scene.collection.objects.link(ground); PLACED.append(ground)
    # valle de cubos: escalones suaves que suben hacia las paredes del abismo; hueco para camino y arroyo
    def hfn(x, y):
        if y > -2:                      # dentro del recinto: lo cubre el patio
            return None if abs(x) < 34 else 0.0
        if abs(x - 12 - (y + 30) * -0.14) < 4.5 and y < -6:   # camino de acceso
            return 0.0
        if abs(x + 31 + (y + 2) * 0.18) < 3.0:                # cauce del arroyo
            return -1.2
        n = math.sin(x * 0.11) * 1.2 + math.cos(y * 0.13 + x * 0.05) * 1.0 + rnd.random() * 0.6
        rise = max(0.0, (abs(x) - 28) * 0.22)
        return round((n + rise) / 1.0) * 1.0
    vox = voxel_field("valley_voxels", -90, 90, -80, -2, 3.0, hfn, M["dirt_side"], M["ground"])
    bpy.context.scene.collection.objects.link(vox); PLACED.append(vox)
    bailey = facade_box("bailey", (66, 70, 4.0), [M["cliff"], M["paving"]], {"top": 1}); bailey.location = (0, 36, -0.5)
    bpy.context.scene.collection.objects.link(bailey); PLACED.append(bailey)
    # ABISMO: paredes en estratos que se cierran hacia el fondo y suben de altura
    for k in range(7):
        y = -6 + k * 11
        hz = 1.0 + k * 0.22
        place("strata_cliff", (-44 + k * 1.6, y, -1), 80 + rnd.uniform(-8, 8), (1.0, 1.0, hz))
        place("strata_cliff", (46 - k * 1.6, y, -1), -80 + rnd.uniform(-8, 8), (1.0, 1.0, hz))
    for x in (-34, -16, 16, 34):
        place("strata_cliff", (x, 84, -1), 180 + rnd.uniform(-10, 10), (1.2, 1.0, 2.4))
    place("strata_cliff", (0, 90, -1), 180, (1.4, 1.0, 2.8))
    for x, y in ((-62, -16), (64, -18)):
        place("strata_cliff", (x, y, -1), rnd.uniform(0, 360), (1.1, 1.0, 1.1))
    # montañas nevadas de fondo
    for x, y, sc in ((-70, 140, 1.4), (0, 160, 1.8), (75, 135, 1.5), (-130, 110, 1.2), (130, 105, 1.3)):
        place("mountain", (x, y, -5), rnd.uniform(0, 360), sc)
    # cascada al fondo del abismo y arroyo que cruza el patio hasta la alcantarilla
    place("waterfall", (-12, 72, 0), 0)
    path = [(-12, 70), (-12, 48), (-20, 36), (-26, 24), (-28, 12), (-28, -2), (-29, -14), (-31, -26), (-33, -38), (-35, -50)]
    for k in range(len(path) - 1):
        (x0, y0), (x1, y1) = path[k], path[k + 1]
        ln = math.hypot(x1 - x0, y1 - y0)
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0)) - 90
        z = 2.9 if y0 > 2 else -0.8
        place("stream", ((x0 + x1) / 2, (y0 + y1) / 2, z), ang, (1.0, ln / 10.0 + 0.05, 1.0))
    for k in range(18):
        place("boulder", (rnd.uniform(-60, 60), rnd.uniform(-40, -8), -0.5), rnd.uniform(0, 360), rnd.uniform(0.6, 2.0))
    # muralla en arco cerrando el desfiladero: torres y lienzos alternos
    pts = [(-33, 2), (-23, -1), (-13, -3), (-3, -4), (7, -4), (17, -3), (27, -1), (35, 2)]
    for k in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[k], pts[k + 1]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        if k == 4:
            place("gatehouse", ((x0 + x1) / 2, (y0 + y1) / 2, 0), ang)
        else:
            place("wall_segment", ((x0 + x1) / 2, (y0 + y1) / 2, 0), ang, (1.02, 1, 1))
    for k, (x, y) in enumerate(pts):
        if k in (0, len(pts) - 1, 2, 5):
            place("wall_tower", (x, y, 0), 0)
    place("ramp", (12, -28, 0), 0, (1, 1.05, 1.15))
    road = facade_box("road", (8, 60, 0.3), [M["road"]]); road.location = (12, -58, -0.55); road.rotation_euler.z = math.radians(8)
    bpy.context.scene.collection.objects.link(road); PLACED.append(road)
    # ciudadela y burgo en terrazas
    place("keep", (6, 46, 3.5), 0)
    for k, (x, y, r) in enumerate([(-12, 12, 0), (-4, 16, 6), (-10, 26, -8), (-2, 27, 0), (18, 15, -6), (26, 22, 4), (-4, 38, 3), (24, 33, -4), (16, 40, 5)]):
        place("house", (x, y, 3.5), r)
    # vida: guardias y arqueros en el adarve, estandartes y pinos
    PXM = 24.0  # píxeles por metro (sprites ~1,5× más grandes que la arquitectura, convención 2D-HD)
    ramp_z = lambda y: 0.3 + max(0.0, min(1.0, (y + 28.0) / 21.0)) * 4.6  # altura de la rampa en y
    def px(key, loc):
        im = image(key)
        if im is not None:
            sprite(key, loc, im.size[1] / PXM)
    for x in (-27, -19, -7, 1, 21, 29):
        px("px_guard" if int(x) % 2 else "px_archer", (x, -4.5 + abs(x) * 0.06, 9.2))
    # patio y rampa: personajes de juego
    for key, loc in [("px_captain", (10.9, -8.6, ramp_z(-8.6))), ("px_guard", (13.4, -8.2, ramp_z(-8.2))), ("px_mage", (12.0, -14.5, ramp_z(-14.5))),
                     ("px_dwarf", (10.8, -17.5, ramp_z(-17.5))), ("px_elf", (13.3, -19.0, ramp_z(-19.0))), ("px_smith", (17.5, 12.0, 3.5)),
                     ("px_villager", (-16.0, 20.0, 3.5)), ("px_guard", (2.0, 30.0, 3.5)), ("px_archer", (-3.0, 9.0, 3.5))]:
        px(key, loc)
    for x in (-13, 17, -33, 35):
        sprite("s_banner", (x, -6.2 + abs(x) * 0.05, 16.0), 6.0)
    sprite("s_banner", (6, 40, 19.5), 7.0)
    for k in range(70):
        side = rnd.choice((-1, 1))
        sprite("s_tree", (side * rnd.uniform(30, 75), rnd.uniform(-45, 30), rnd.uniform(-0.5, 6)), rnd.uniform(5, 10))
    for x, y, z in [(-4, -7.5, 6.5), (16, -7.5, 6.5), (2, 40, 5.0), (10, 40, 5.0), (-14, 18, 5.5), (22, 18, 5.5)]:
        torch((x, y, z))


# ───────────────────────── luz, cámara, render ─────────────────────────
def finalize():
    root = bpy.data.objects.new("World_Root", None)
    bpy.context.scene.collection.objects.link(root)
    for o in PLACED:
        o.parent = root
    root.scale = (S, S, S)
    bpy.context.view_layer.update()
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Sky"); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.36, 0.45, 0.68, 1); bg.inputs[1].default_value = 0.55
    sun = bpy.data.lights.new("Sun", "SUN"); sun.energy = 5.0; sun.color = (1.0, 0.8, 0.6); sun.angle = math.radians(4)
    so = bpy.data.objects.new("Sun", sun); sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(62), 0, math.radians(-50))
    fill = bpy.data.lights.new("Sky_fill", "SUN"); fill.energy = 0.8; fill.color = (0.55, 0.65, 1.0); fill.angle = math.radians(20)
    fo = bpy.data.objects.new("Sky_fill", fill); sc.collection.objects.link(fo); fo.rotation_euler = (math.radians(50), 0, math.radians(150))
    # niebla de valle muy ligera
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    me = bpy.data.meshes.new("Haze"); bm.to_mesh(me); bm.free()
    hm = bpy.data.materials.new("Haze"); hm.use_nodes = True; nt = hm.node_tree; nt.nodes.remove(nt.nodes["Principled BSDF"])
    v = nt.nodes.new("ShaderNodeVolumePrincipled"); v.inputs["Density"].default_value = 0.0012 / S; v.inputs["Color"].default_value = (0.75, 0.82, 1.0, 1)
    nt.links.new(v.outputs[0], nt.nodes["Material Output"].inputs["Volume"]); me.materials.append(hm)
    ho = bpy.data.objects.new("Haze", me); sc.collection.objects.link(ho); ho.scale = (230 * S, 230 * S, 50 * S); ho.location = (0, 20 * S, 18 * S)
    # módulos fuera de la vista (solo se usan como instancias)
    for col in MODULES.values():
        col.hide_render = False


SHOTS = {"hero": ((2, 18, 6), 38, -24, 150), "gate": ((12, -6, 6), 30, -18, 62), "keep": ((4, 34, 10), 34, -20, 75),
         "party": ((12, -13, 3.0), 26, -14, 24),
         "abyss": ((-14, 58, 16), 22, 18, 120)}


def camera():
    (tx, ty, tz), elev, az, width = SHOTS.get(CFG["shot"], SHOTS["hero"])
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("Cam"); cd.lens = 65; cd.sensor_width = 36
    dist = (width * S / 2) / math.tan(math.atan(18 / 65)) * 1.0
    e, a = math.radians(elev), math.radians(az)
    c = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(c)
    target = Vector((tx, ty, tz)) * S
    c.location = target + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
    f = bpy.data.objects.new("Focus", None); sc.collection.objects.link(f); f.location = target
    tr = c.constraints.new("TRACK_TO"); tr.target = f; tr.track_axis = "TRACK_NEGATIVE_Z"; tr.up_axis = "UP_Y"
    cd.clip_start = 0.005; cd.clip_end = 50
    cd.dof.use_dof = True; cd.dof.focus_object = f; cd.dof.aperture_fstop = 2.8
    sc.camera = c
    for o in SPRITES:
        k = o.constraints.new("LOCKED_TRACK"); k.target = c; k.track_axis = "TRACK_NEGATIVE_Y"; k.lock_axis = "LOCK_Z"


def render_settings():
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = CFG["res"]
    sc.render.filepath = CFG["out"]
    if CFG["engine"] == "EEVEE":
        ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in ids else "BLENDER_EEVEE"
    else:
        sc.render.engine = "CYCLES"; sc.cycles.samples = CFG["samples"]; sc.cycles.use_denoising = True
        sc.cycles.volume_step_rate = 4.0; sc.cycles.max_bounces = 6
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for dev in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
                try:
                    prefs.compute_device_type = dev; prefs.get_devices()
                    if any(d.type == dev for d in prefs.devices):
                        for d in prefs.devices: d.use = True
                        sc.cycles.device = "GPU"; break
                except Exception:
                    continue
        except Exception:
            pass
    vs = sc.view_settings
    for vt in ("AgX", "Filmic"):
        try: vs.view_transform = vt; break
        except Exception: pass
    for lk in ("AgX - Medium High Contrast", "Medium High Contrast"):
        try: vs.look = lk; break
        except Exception: pass
    vs.exposure = -0.35
    # Compositor: Glare (Fog Glow) sutil
    if hasattr(sc, "compositing_node_group"):
        tree = bpy.data.node_groups.new("Post", "CompositorNodeTree"); sc.compositing_node_group = tree
        out = tree.nodes.new("NodeGroupOutput"); tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor"); oin = out.inputs[0]
    else:
        sc.use_nodes = True; tree = sc.node_tree
        for n in list(tree.nodes): tree.nodes.remove(n)
        out = tree.nodes.new("CompositorNodeComposite"); oin = out.inputs["Image"]
    rl = tree.nodes.new("CompositorNodeRLayers"); gl = tree.nodes.new("CompositorNodeGlare")
    for at, v in [("glare_type", "FOG_GLOW"), ("mix", -0.8), ("threshold", 1.5)]:
        try: setattr(gl, at, v)
        except Exception: pass
    for nm, v in [("Type", "Fog Glow"), ("Threshold", 1.5), ("Strength", 0.25)]:
        if nm in gl.inputs:
            try: gl.inputs[nm].default_value = v
            except Exception: pass
    tree.links.new(rl.outputs["Image"], gl.inputs["Image"]); tree.links.new(gl.outputs[0], oin)


def add_vignette(strength=0.6, size=(0.95, 0.82), blur=260):
    """Inserta una viñeta suave antes de la salida del compositor (Blender 4 y 5)."""
    sc = bpy.context.scene
    tree = getattr(sc, "compositing_node_group", None) or (sc.node_tree if getattr(sc, "use_nodes", False) else None)
    if tree is None:
        return
    out = next((n for n in tree.nodes if n.bl_idname in ("NodeGroupOutput", "CompositorNodeComposite")), None)
    if out is None or not out.inputs[0].links:
        return
    src = out.inputs[0].links[0].from_socket
    el = tree.nodes.new("CompositorNodeEllipseMask")
    if "Size" in el.inputs:
        el.inputs["Size"].default_value = size
    else:
        el.width, el.height = size
    bl = tree.nodes.new("CompositorNodeBlur")
    if "Size" in bl.inputs:
        try: bl.inputs["Size"].default_value = (blur, blur)
        except Exception: pass
    else:
        bl.size_x = bl.size_y = blur
    tree.links.new(el.outputs[0], bl.inputs[0])
    mx = tree.nodes.new("ShaderNodeMix") if "ShaderNodeMix" in dir(bpy.types) else None
    try:
        mx.data_type = "RGBA"; mx.blend_type = "MULTIPLY"; mx.inputs[0].default_value = strength
        tree.links.new(src, mx.inputs[6]); tree.links.new(bl.outputs[0], mx.inputs[7]); tree.links.new(mx.outputs[2], out.inputs[0])
    except Exception:
        tree.nodes.remove(mx) if mx else None
        mx = tree.nodes.new("CompositorNodeMixRGB"); mx.blend_type = "MULTIPLY"; mx.inputs[0].default_value = strength
        tree.links.new(src, mx.inputs[1]); tree.links.new(bl.outputs[0], mx.inputs[2]); tree.links.new(mx.outputs[0], out.inputs[0])


TIMES = {  # elevación y acimut del sol, energía, color, fuerza del cielo, multiplicador de luces cálidas, exposición extra
    "day": (34, -40, 4.5, (1.0, 0.86, 0.68), 1.0, 1.0, 0.0, 1.0),
    "dawn": (14, 60, 3.4, (1.0, 0.66, 0.5), 0.6, 1.6, 0.1, 0.55),
    "dusk": (12, -70, 3.6, (1.0, 0.45, 0.18), 0.5, 2.0, 0.05, 0.3),
    "night": (40, 30, 0.12, (0.5, 0.62, 1.0), 0.1, 3.0, -0.15, 0.08),
}


def apply_time(t, sun_obj=None):
    """Hora del día coherente: sol, cielo, faroles y ventanas."""
    if t not in TIMES:
        return
    el, az, en, col, skym, lmul, expo, fillm = TIMES[t]
    sc = bpy.context.scene
    so = sun_obj or bpy.data.objects.get("Sun")
    if so:
        so.rotation_euler = (math.radians(90 - el), 0, math.radians(az)); so.data.energy = en; so.data.color = col
    w = sc.world
    if w and w.use_nodes:
        for n in w.node_tree.nodes:
            if n.type == "TEX_SKY":
                try: n.sun_elevation = math.radians(max(el, 2) if t != "night" else -4)
                except Exception: pass
                try: n.sun_rotation = math.radians(az + 180)
                except Exception: pass
            if n.type == "BACKGROUND":
                n.inputs[1].default_value *= skym
                if t == "night" and not n.inputs[0].links:
                    n.inputs[0].default_value = (0.02, 0.03, 0.08, 1)
        if t == "night":
            bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
            if bg and bg.inputs[0].links:  # cielo nocturno azul en vez del Nishita negro
                w.node_tree.links.remove(bg.inputs[0].links[0]); bg.inputs[0].default_value = (0.03, 0.05, 0.13, 1); bg.inputs[1].default_value = 1.0
    for o in sc.objects:
        if o.type == "LIGHT" and o.data.type == "POINT":
            o.data.energy *= lmul
        elif o.type == "LIGHT" and o.data.type == "SUN" and o != so:  # relleno y contraluz siguen la hora
            o.data.energy *= fillm
            if t == "night":
                o.data.color = (0.35, 0.45, 1.0)
    if t in ("night", "dusk"):
        for m in bpy.data.materials:
            if not m.use_nodes:
                continue
            for n in m.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED" and "Emission Strength" in n.inputs and n.inputs["Emission Strength"].default_value > 0.5:
                    n.inputs["Emission Strength"].default_value *= 2.0 if t == "night" else 1.4
    return expo


def materials():
    return {
        "wall": detail_mat("Wall", "wall", "box", repeat=0.16, grime=2.5),
        "tower": detail_mat("TowerFacade", "tower_facade", "uv", grime=2.5, ao=0.4),
        "keep": detail_mat("KeepFacade", "keep_facade", "uv", grime=2.0, ao=0.35, emission_boost=6.0),
        "gate": detail_mat("Gate", "gate", "uv", grime=1.0, ao=0.4),
        "house": detail_mat("HouseFacade", "house_facade", "uv", grime=1.0, ao=0.35),
        "house_side": detail_mat("HouseSide", "house_side", "uv", grime=1.0, ao=0.35),
        "roof": detail_mat("Slate", "roof", "box", repeat=0.35, rough=0.5, grime=0, edge=0.1),
        "paving": detail_mat("Paving", "paving", "box", repeat=0.22, grime=0, edge=0.05),
        "cliff": detail_mat("Cliff", "moss_rock", "box", repeat=0.16, grime=0, edge=0.3, grass_key="grass", ao=0.8, tint=(0.62, 0.62, 0.68)),
        "cliff_b": detail_mat("CliffB", "moss_rock", "box", repeat=0.13, grime=0, edge=0.3, grass_key="grass", ao=0.8, tint=(0.7, 0.64, 0.58)),
        "ground": detail_mat("Ground", "grass", "box", repeat=0.05, grime=0, edge=0, tint=(0.8, 0.9, 0.7)),
        "road": detail_mat("Road", "dirt", "box", repeat=0.12, grime=0, edge=0),
        "dirt_side": detail_mat("DirtSide", "dirt", "box", repeat=0.25, grime=0, edge=0.25, ao=0.6, tint=(0.75, 0.68, 0.6)),
        "ledge": detail_mat("Ledge", "grass", "box", repeat=0.2, grime=0, edge=0.1, ao=0.7, tint=(0.7, 0.8, 0.6)),
        "mountain": detail_mat("Mountain", "cliff", "box", repeat=0.03, grime=0, edge=0.2, grass_key="snow", ao=0.5, tint=(0.55, 0.58, 0.68)),
        "water": water_mat("Water", (0.06, 0.2, 0.26), 0.04, foam=0.0),
        "falls": water_mat("Falls", (0.55, 0.7, 0.78), 0.15, foam=1.0),
    }


def make_snow():
    r = random.Random(5)
    n = 16
    im = bpy.data.images.new("snow", n, n)
    px = []
    for i in range(n * n):
        v = r.uniform(0.86, 1.0)
        px += [v * 0.93, v * 0.96, v, 1.0]
    im.pixels = px
    IMGS["snow"] = im


def prepare_facades():
    """Recorta las imágenes de fachada a su zona útil (sin cielo ni márgenes)."""
    crops = {"tower_facade": (0.14, 0.12, 0.86, 1.0), "house_facade": (0.03, 0.2, 0.97, 0.96), "house_side": (0.03, 0.05, 0.97, 0.96), "gate": (0.0, 0.0, 1.0, 1.0)}
    for key, (x0, y0, x1, y1) in crops.items():
        im = image(key)
        if im is None:
            continue
        w, h = im.size
        px = list(im.pixels)
        nx0, nx1 = int(x0 * w), int(x1 * w); ny0, ny1 = int((1 - y1) * h), int((1 - y0) * h)
        nw, nh = nx1 - nx0, ny1 - ny0
        out = []
        for y in range(ny0, ny1):
            row = px[(y * w + nx0) * 4:(y * w + nx1) * 4]
            out.extend(row)
        new = bpy.data.images.new(key + "_crop", nw, nh)
        new.pixels = out
        IMGS[key] = new


def export_modules():
    out_dir = os.path.join(HERE, "modules")
    os.makedirs(out_dir, exist_ok=True)
    for name, col in MODULES.items():
        tmp = bpy.data.objects.new("tmp", None)
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        objs = []
        for o in col.objects:
            c = o.copy(); c.data = o.data.copy() if o.data else None
            bpy.context.scene.collection.objects.link(c); c.select_set(True); objs.append(c)
        bpy.context.view_layer.objects.active = objs[0]
        bpy.ops.export_scene.gltf(filepath=os.path.join(out_dir, name + ".glb"), export_format="GLB", use_selection=True, export_apply=True)
        bpy.ops.export_scene.fbx(filepath=os.path.join(out_dir, name + ".fbx"), use_selection=True, apply_scale_options="FBX_SCALE_ALL",
                                 axis_forward="-Z", axis_up="Y", path_mode="COPY", embed_textures=True, add_leaf_bones=False, bake_anim=False)
        for c in objs:
            bpy.data.objects.remove(c, do_unlink=True)
        log("Exportado módulo " + name)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    prepare_facades()
    make_snow()
    M = materials()
    for fn in (wall_segment, wall_tower, gatehouse, keep, house, ramp, cliff, boulder, strata_cliff, mountain, waterfall, stream):
        fn(M)
    log("Módulos: " + ", ".join(MODULES))
    if CFG["export"]:
        export_modules()
    assemble(M)
    finalize()
    camera()
    render_settings()
    log("Escena montada: %d instancias/props" % len(PLACED))
    if CFG["render"]:
        bpy.ops.render.render(write_still=True)
        log("Render → " + CFG["out"])


if __name__ == "__main__":
    main()
