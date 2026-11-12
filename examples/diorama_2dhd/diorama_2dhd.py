"""
Diorama 2D-HD de fantasía oscura · NV Asset Forge
==================================================
Demonios, elfos, humanos, enanos y orcos en un mapa escalonado estilo
Octopath Traveler / Triangle Strategy.

Uso:
    blender -b -P diorama_2dhd.py -- [--engine CYCLES|EEVEE] [--res 1920x1080] [--samples 96] [--out render.png] [--shot hero|humans|demons]
o ábrelo en Blender 4.x / 5.x → Scripting → Run Script (genera la escena sin renderizar).

Requisitos cubiertos:
 1. Geometría modular: terreno escalonado por celdas, edificios por facción, caminos, agua y vegetación.
 2. Materiales pixel-art PBR: Principled BSDF, texturas con interpolación Closest, Bump y variación de Roughness
    (agua, adoquines mojados y metales reflejan la luz).
 3. Billboards: planos verticales que miran a la cámara (Locked Track), Alpha Clip y sombras proyectadas.
 4. Cámara tilt-shift: 65 mm, picado de 40°, DOF a f/1.8 enfocado al centro. La escena se escala 1:20
    para que f/1.8 produzca el desenfoque real de una maqueta.
 5. Luz cinematográfica: Sun con sombras suaves, luces puntuales cálidas de alto contraste, volumen de baja
    densidad, AgX, y Compositor con Glare (Fog Glow) y viñeteado.

Las texturas y sprites (carpeta ./assets) se generaron con FLUX.2 en NVIDIA Build desde NV Asset Forge.
"""
import math
import os
import random
import sys

import bpy
import bmesh
from mathutils import Vector, Euler

# ───────────────────────── configuración ─────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else bpy.path.abspath("//")
CFG = {
    "assets": os.path.join(HERE, "assets"),
    "engine": "CYCLES",          # CYCLES (con denoising) o EEVEE
    "res": (1600, 900),
    "samples": 96,
    "out": os.path.join(HERE, "render_2dhd.png"),
    "shot": "hero",              # hero | humans | demons
    "miniature_scale": 0.05,     # 1:20 → desenfoque de maqueta real a f/1.8
    "cell": 2.0,                 # tamaño de celda en metros (escala real)
    "step": 0.8,                 # altura de cada nivel del terreno
    "px_per_m": 36,              # densidad de píxel de los sprites (50 px = 1 m)
    "render": True,
}
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
for i, a in enumerate(argv):
    if a == "--engine": CFG["engine"] = argv[i + 1].upper()
    if a == "--res": CFG["res"] = tuple(int(v) for v in argv[i + 1].split("x"))
    if a == "--samples": CFG["samples"] = int(argv[i + 1])
    if a == "--out": CFG["out"] = argv[i + 1]
    if a == "--shot": CFG["shot"] = argv[i + 1]
    if a == "--no-render": CFG["render"] = False
if bpy.app.background is False:
    CFG["render"] = False

rnd = random.Random(1337)
S = CFG["miniature_scale"]
B4 = bpy.app.version >= (4, 0, 0)
B42 = bpy.app.version >= (4, 2, 0)
ALL = []  # todo lo que cuelga de la raíz de la maqueta


def log(m):
    print("2DHD:", m, flush=True)


# ───────────────────────── utilidades de escena ─────────────────────────
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def link(o):
    bpy.context.scene.collection.objects.link(o)
    ALL.append(o)
    return o


def mesh_obj(name, bm, mats):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    return link(bpy.data.objects.new(name, me))


def add_bevel(o, w=0.03, seg=1):
    m = o.modifiers.new("Bevel", "BEVEL")
    m.width = w
    m.segments = seg
    m.limit_method = "ANGLE"
    return o


def box(name, size, loc, mat, top=None, rot=0.0, bevel=0.02):
    """Caja apoyada en loc.z. top = material distinto para la cara superior (índice 1)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector((0, 0, size[2] / 2)), verts=bm.verts)
    if top is not None:
        for f in bm.faces:
            f.material_index = 1 if f.normal.z > 0.5 else 0
    o = mesh_obj(name, bm, [mat] + ([top] if top is not None else []))
    o.location = loc
    o.rotation_euler = (0, 0, math.radians(rot))
    if bevel:
        add_bevel(o, bevel)
    return o


def cyl(name, r, h, loc, mat, verts=16, r_top=None, rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r if r_top is None else r_top, depth=h)
    bmesh.ops.translate(bm, vec=Vector((0, 0, h / 2)), verts=bm.verts)
    o = mesh_obj(name, bm, [mat])
    o.location = loc
    o.rotation_euler = [math.radians(a) for a in rot]
    return o


def gable(name, w, d, h, loc, mat, overhang=0.3, rot=0.0):
    bm = bmesh.new()
    W, D = w / 2 + overhang, d / 2 + overhang
    v = [bm.verts.new(p) for p in [(-W, -D, 0), (W, -D, 0), (0, -D, h), (-W, D, 0), (W, D, 0), (0, D, h)]]
    for f in [(v[0], v[1], v[2]), (v[5], v[4], v[3]), (v[0], v[2], v[5], v[3]), (v[1], v[4], v[5], v[2]), (v[0], v[3], v[4], v[1])]:
        bm.faces.new(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = mesh_obj(name, bm, [mat])
    sol = o.modifiers.new("Solid", "SOLIDIFY")
    sol.thickness = 0.12
    o.location = loc
    o.rotation_euler = (0, 0, math.radians(rot))
    return o


def point_light(name, loc, color, power, radius=0.15):
    d = bpy.data.lights.new(name, "POINT")
    d.color = color
    d.energy = power * S * S          # potencia corregida para la escala de maqueta
    d.shadow_soft_size = radius * S
    o = link(bpy.data.objects.new(name, d))
    o.location = loc
    return o


# ───────────────────────── 2. materiales pixel-art PBR ─────────────────────────
IMG = {}


def img(key):
    if key not in IMG:
        p = os.path.join(CFG["assets"], key + ".png")
        IMG[key] = bpy.data.images.load(p, check_existing=True) if os.path.exists(p) else None
    return IMG[key]


def tex_node(nt, image, coord="Object", repeat=0.5):
    """Imagen con interpolación Closest (píxel nítido) y proyección en caja."""
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = image
    t.interpolation = "Closest"
    t.projection = "BOX"
    t.projection_blend = 0.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (repeat, repeat, repeat)
    nt.links.new(tc.outputs[coord], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
    return t


def bsdf_input(b, *names):
    for n in names:
        if n in b.inputs:
            return b.inputs[n]
    return None


def pixel_mat(name, key, rough=(0.55, 0.9), bump=0.35, metal=0.0, repeat=0.5, tint=None, emission=0.0, wet=False):
    """Principled BSDF + textura Closest + Bump desde la luminancia + variación de Roughness por ruido."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Metallic"].default_value = metal
    image = img(key)
    if image is None:
        b.inputs["Base Color"].default_value = tuple(tint or (0.5, 0.5, 0.5)) + (1,)
        return m
    t = tex_node(nt, image, repeat=repeat)
    col = t.outputs["Color"]
    if tint:
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        nt.links.new(col, mix.inputs[6])
        mix.inputs[7].default_value = tuple(tint) + (1,)
        col = mix.outputs[2]
    nt.links.new(col, b.inputs["Base Color"])
    # Bump con la luminancia del propio píxel (relieve "bloque a bloque")
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(t.outputs["Color"], bw.inputs[0])
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = bump
    bp.inputs["Distance"].default_value = 0.04 * S
    nt.links.new(bw.outputs[0], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    # Roughness: ruido pixelado (Closest via snap) + luminancia → charcos/zonas pulidas
    nz = nt.nodes.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 3.0
    tc = nt.nodes.new("ShaderNodeTexCoord")
    snap = nt.nodes.new("ShaderNodeVectorMath")
    snap.operation = "SNAP"
    snap.inputs[1].default_value = (0.0625, 0.0625, 0.0625)
    nt.links.new(tc.outputs["Object"], snap.inputs[0])
    nt.links.new(snap.outputs[0], nz.inputs["Vector"])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["To Min"].default_value = rough[0]
    mr.inputs["To Max"].default_value = rough[1]
    mr.inputs["From Min"].default_value = 0.35
    mr.inputs["From Max"].default_value = 0.65
    nt.links.new(nz.outputs["Fac"], mr.inputs["Value"])
    if wet:  # las juntas oscuras (bajas) quedan más húmedas → más brillo
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY_ADD"
        nt.links.new(mr.outputs[0], mul.inputs[0])
        nt.links.new(bw.outputs[0], mul.inputs[1])
        mul.inputs[2].default_value = 0.05
        nt.links.new(mul.outputs[0], b.inputs["Roughness"])
    else:
        nt.links.new(mr.outputs[0], b.inputs["Roughness"])
    if emission:
        e = bsdf_input(b, "Emission Color", "Emission")
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(t.outputs["Color"], sep.inputs[0])
        sub = nt.nodes.new("ShaderNodeMath")   # solo emiten los píxeles rojos (grietas de lava)
        sub.operation = "SUBTRACT"
        nt.links.new(sep.outputs[0], sub.inputs[0])
        nt.links.new(sep.outputs[1], sub.inputs[1])
        gain = nt.nodes.new("ShaderNodeMath")
        gain.operation = "MULTIPLY"
        gain.inputs[1].default_value = 3.0
        gain.use_clamp = True
        nt.links.new(sub.outputs[0], gain.inputs[0])
        c = nt.nodes.new("ShaderNodeVectorMath")   # color de lava escalado por la máscara (negro = sin emisión)
        c.operation = "SCALE"
        c.inputs[0].default_value = (1.0, 0.12, 0.02)
        nt.links.new(gain.outputs[0], c.inputs["Scale"])
        nt.links.new(c.outputs[0], e)
        b.inputs["Emission Strength"].default_value = emission
    return m


def flat_mat(name, color, rough=0.6, metal=0.0, emission=None, strength=6.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = tuple(color) + (1,)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emission:
        bsdf_input(b, "Emission Color", "Emission").default_value = tuple(emission) + (1,)
        b.inputs["Emission Strength"].default_value = strength
    return m


def water_mat():
    m = bpy.data.materials.new("Water")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.02, 0.09, 0.12, 1)
    b.inputs["Roughness"].default_value = 0.03
    b.inputs["IOR"].default_value = 1.33
    sp = bsdf_input(b, "Specular IOR Level", "Specular")
    if sp: sp.default_value = 0.8
    # olas pixeladas: coordenadas "snap" + ondas → Bump
    tc = nt.nodes.new("ShaderNodeTexCoord")
    snap = nt.nodes.new("ShaderNodeVectorMath")
    snap.operation = "SNAP"
    snap.inputs[1].default_value = (0.12, 0.12, 0.12)
    nt.links.new(tc.outputs["Object"], snap.inputs[0])
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.inputs["Scale"].default_value = 0.6
    wv.inputs["Distortion"].default_value = 6.0
    nt.links.new(snap.outputs[0], wv.inputs["Vector"])
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.25
    bp.inputs["Distance"].default_value = 0.05 * S
    nt.links.new(wv.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def sprite_mat(key):
    """Billboard: Closest, Alpha Clip (umbral 0.5) y sombra recortada."""
    m = bpy.data.materials.new("Sprite_" + key)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img(key)
    t.interpolation = "Closest"
    t.extension = "CLIP"
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    clip = nt.nodes.new("ShaderNodeMath")
    clip.operation = "GREATER_THAN"
    clip.inputs[1].default_value = 0.5
    nt.links.new(t.outputs["Alpha"], clip.inputs[0])
    nt.links.new(clip.outputs[0], b.inputs["Alpha"])
    b.inputs["Roughness"].default_value = 0.8
    if B42:
        m.surface_render_method = "DITHERED"
        if hasattr(m, "use_transparent_shadow"):
            m.use_transparent_shadow = True
    else:
        m.blend_method = "CLIP"
        m.alpha_threshold = 0.5
        m.shadow_method = "CLIP"
    return m


# ───────────────────────── 3. billboards ─────────────────────────
BILLBOARDS = []


def billboard(key, loc, scale=1.0, flip=False):
    image = img(key)
    if image is None:
        return None
    w, h = image.size
    W, H = w / CFG["px_per_m"] * scale, h / CFG["px_per_m"] * scale
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in [(-W / 2, 0, 0), (W / 2, 0, 0), (W / 2, 0, H), (-W / 2, 0, H)]]
    f = bm.faces.new(vs)
    uv = bm.loops.layers.uv.new("UVMap")
    for loop, c in zip(f.loops, [(1, 0), (0, 0), (0, 1), (1, 1)] if flip else [(0, 0), (1, 0), (1, 1), (0, 1)]):
        loop[uv].uv = c
    o = mesh_obj("BB_" + key, bm, [sprite_mat(key)])
    o.location = loc
    if hasattr(o, "visible_shadow"):
        o.visible_shadow = True
    BILLBOARDS.append(o)
    return o


def aim_billboards(cam):
    """Rotación solo en Z hacia la cámara (sprites siempre verticales)."""
    for o in BILLBOARDS:
        c = o.constraints.new("LOCKED_TRACK")
        c.target = cam
        c.track_axis = "TRACK_NEGATIVE_Y"
        c.lock_axis = "LOCK_Z"


# ───────────────────────── 1. geometría del mapa ─────────────────────────
# Filas de norte (arriba) a sur (abajo). Alturas en niveles; superficies:
# g hierba · c adoquín mojado · p camino de tierra · x barro orco · m mármol élfico
# o obsidiana demoníaca · K granito enano · w río
HEIGHTS = [
    "222225555444",
    "222225555444",
    "222223443444",
    "222222333433",
    "221111111332",
    "000000000000",
    "111111111111",
    "111111111111",
    "111111111111",
]
SURF = [
    "mmmmmooooKKK",
    "mmmmmooooKKK",
    "mmmgpppopKKK",
    "gmggpgppgKKg",
    "ggpgppgggggg",
    "wwwwwwwwwwww",
    "ccccpgggxxxx",
    "ccccpgggxxxx",
    "gcccpgggxxxx",
]
NX, NY = len(HEIGHTS[0]), len(HEIGHTS)
C = CFG["cell"]


def cell_xy(i, j):
    """i = columna (oeste→este), j = fila desde el sur."""
    return (-NX * C / 2 + C * i + C / 2, -NY * C / 2 + C * j + C / 2)


def level(i, j):
    return int(HEIGHTS[NY - 1 - j][i])


def surf(i, j):
    return SURF[NY - 1 - j][i]


def top_z(i, j):
    return 0.15 if surf(i, j) == "w" else 0.4 + level(i, j) * CFG["step"]


def build_terrain(M):
    base = -1.2
    tops = {"g": M["grass"], "c": M["cobble"], "p": M["dirt"], "x": M["mud"], "m": M["marble"], "o": M["obsidian"], "K": M["granite"], "w": M["riverbed"]}
    for j in range(NY):
        for i in range(NX):
            x, y = cell_xy(i, j)
            z = top_z(i, j)
            box(f"cell_{i}_{j}", (C, C, z - base), (x, y, base), M["cliff"], top=tops[surf(i, j)], bevel=0.04)
    # zócalo de la maqueta (madera oscura con moldura)
    box("plinth", (NX * C + 0.6, NY * C + 0.6, 0.45), (0, 0, base - 0.45), M["plinth"], bevel=0.08)
    box("plinth_trim", (NX * C + 0.9, NY * C + 0.9, 0.12), (0, 0, base - 0.57), M["bronze"], bevel=0.04)
    # agua: lámina continua en el cauce
    y_r = cell_xy(0, 3)[1]
    box("river", (NX * C - 0.02, C - 0.02, 0.32), (0, y_r, 0.15), M["water"], bevel=0)
    # escalones donde los caminos cambian de nivel
    for (i, j, d) in [(4, 4, +1), (2, 4, +1), (5, 6, +1), (8, 6, +1), (6, 6, +1)]:
        stairs(i, j, d, M["stone_step"])


def stairs(i, j, d, mat):
    x, y = cell_xy(i, j)
    z0, z1 = top_z(i, j), top_z(i, j + d)
    if z1 <= z0:
        return
    n = max(2, int((z1 - z0) / 0.2))
    for k in range(n):
        h = (z1 - z0) * (k + 1) / n
        box(f"step_{i}_{j}_{k}", (1.2, C / 2 / n * (n - k), h), (x, y + d * (C / 2 - C / 4 / n * (n - k)), z0), mat, bevel=0.015)


# ── facciones ──
def half_timber_house(name, x, y, z, w, d, M, rot=0.0, floors=2):
    h1 = 2.2
    box(name + "_base", (w, d, h1), (x, y, z), M["cliff_wall"], rot=rot)
    box(name + "_upper", (w + 0.3, d + 0.3, 2.0 * (floors - 1)), (x, y, z + h1), M["wood"], rot=rot)
    for k, dx in enumerate((-w / 2 + 0.2, 0, w / 2 - 0.2)):
        box(f"{name}_post{k}", (0.16, 0.08, 2.0), (x + dx, y - d / 2 - 0.19, z + h1), M["dark_wood"], rot=rot, bevel=0.01)
    gable(name + "_roof", w + 0.3, d + 0.3, 2.0, (x, y, z + h1 + 2.0 * (floors - 1)), M["slate"], rot=rot + 90 if w > d else rot)
    box(name + "_chimney", (0.5, 0.5, 2.6), (x + w / 4, y + d / 4, z + h1 + 1.0), M["cliff_wall"], rot=rot)
    for k, dx in enumerate((-w / 4, w / 4)):
        box(f"{name}_win{k}", (0.55, 0.06, 0.7), (x + dx, y - d / 2 - 0.03, z + 1.0), M["window"], rot=rot, bevel=0)
        box(f"{name}_win_up{k}", (0.5, 0.06, 0.6), (x + dx, y - d / 2 - 0.18, z + h1 + 0.7), M["window"], rot=rot, bevel=0)
    box(name + "_door", (0.9, 0.08, 1.7), (x, y - d / 2 - 0.04, z), M["dark_wood"], rot=rot, bevel=0.01)
    point_light(name + "_glow", (x, y - d / 2 - 0.8, z + 1.2), (1.0, 0.62, 0.3), 120, 0.2)


def humans(M):
    z = top_z(1, 1)
    half_timber_house("house_a", *cell_xy(0, 1), z, 3.0, 2.6, M)
    half_timber_house("house_b", cell_xy(2, 2)[0] + 0.6, cell_xy(2, 2)[1] - 0.2, z, 3.4, 2.4, M)
    half_timber_house("house_c", cell_xy(3, 0)[0], cell_xy(3, 0)[1] + 0.2, z, 2.6, 2.2, M, floors=3)
    # pozo y farolas en la plaza
    wx, wy = cell_xy(1, 0)
    cyl("well", 0.6, 0.8, (wx + 0.8, wy, z), M["cliff_wall"], 12)
    cyl("well_water", 0.48, 0.81, (wx + 0.8, wy, z), M["water"], 12)
    for k, (lx, ly) in enumerate([cell_xy(3, 2), cell_xy(0, 2)]):
        cyl(f"lamp_post{k}", 0.06, 2.4, (lx + 0.7, ly - 0.6, z), M["iron"], 6)
        box(f"lamp{k}", (0.25, 0.25, 0.3), (lx + 0.7, ly - 0.6, z + 2.4), M["lantern"], bevel=0.01)
        point_light(f"lamp_light{k}", (lx + 0.7, ly - 0.6, z + 2.3), (1.0, 0.7, 0.35), 160, 0.1)
    billboard("s_human", (cell_xy(2, 1)[0] - 0.4, cell_xy(2, 1)[1] - 0.3, z))


def orcs(M):
    z = top_z(9, 1)
    for k, (i, j, r) in enumerate([(8, 2, 1.3), (10, 1, 1.5), (11, 2, 1.1)]):
        x, y = cell_xy(i, j)
        cyl(f"hut_wall{k}", r, 1.4, (x, y, z), M["wood"], 10)
        cyl(f"hut_roof{k}", r + 0.35, 1.9, (x, y, z + 1.4), M["thatch"], 10, r_top=0.05)
        for s in range(5):
            a = s / 5 * math.tau + 0.3
            cyl(f"hut_spike{k}_{s}", 0.07, 1.0, (x + math.cos(a) * r * 0.7, y + math.sin(a) * r * 0.7, z + 2.2), M["bone"], 6, r_top=0.0, rot=(math.degrees(math.cos(a)) * 0.4, math.degrees(math.sin(a)) * -0.4, 0))
    # empalizada en el borde sur y este
    for s in range(16):
        x = cell_xy(8, 0)[0] - C / 2 + 0.3 + s * 0.5
        cyl(f"palisade_s{s}", 0.13, 1.4 + rnd.uniform(-0.2, 0.3), (x, -NY * C / 2 + 0.25, z), M["dark_wood"], 6, r_top=0.0)
    for s in range(11):
        y = -NY * C / 2 + 0.3 + s * 0.5
        cyl(f"palisade_e{s}", 0.13, 1.4 + rnd.uniform(-0.2, 0.3), (NX * C / 2 - 0.25, y, z), M["dark_wood"], 6, r_top=0.0)
    fx, fy = cell_xy(9, 0)
    for s in range(8):
        a = s / 8 * math.tau
        box(f"firepit_stone{s}", (0.3, 0.22, 0.2), (fx + math.cos(a) * 0.55, fy + 0.4 + math.sin(a) * 0.55, z), M["cliff_wall"], rot=math.degrees(a), bevel=0.03)
    cyl("fire", 0.32, 0.5, (fx, fy + 0.4, z), M["fire"], 8, r_top=0.0)
    point_light("fire_light", (fx, fy + 0.4, z + 0.8), (1.0, 0.45, 0.12), 520, 0.25)
    billboard("s_orc", (fx + 1.1, fy - 0.2, z))


def elves(M):
    z = top_z(1, 7)
    for k, (i, j, h) in enumerate([(1, 7, 7.5), (3, 8, 5.5)]):
        x, y = cell_xy(i, j)
        cyl(f"elf_tower{k}", 0.75, h, (x, y, z), M["marble_wall"], 8, r_top=0.6)
        cyl(f"elf_ring{k}", 0.95, 0.25, (x, y, z + h * 0.62), M["bronze"], 8)
        cyl(f"elf_roof{k}", 1.05, 2.6, (x, y, z + h), M["elf_roof"], 8, r_top=0.0)
        for s in range(3):
            box(f"elf_win{k}_{s}", (0.25, 0.06, 0.6), (x, y - 0.72, z + 1.2 + s * h * 0.28), M["teal_glow"], bevel=0)
        point_light(f"elf_light{k}", (x, y - 1.2, z + h * 0.6), (0.25, 0.95, 0.85), 260, 0.2)
    # cristales flotantes
    for k in range(5):
        x, y = cell_xy(rnd.randint(0, 3), rnd.randint(5, 6))
        cyl(f"crystal{k}", 0.22, 0.9, (x + rnd.uniform(-0.6, 0.6), y + rnd.uniform(-0.6, 0.6), z + 0.4), M["teal_glow"], 4, r_top=0.0)
    # arco élfico sobre el camino
    ax, ay = cell_xy(4, 6)
    for dx in (-0.8, 0.8):
        cyl(f"elf_arch_col{dx}", 0.15, 2.6, (ax + dx, ay, top_z(4, 6)), M["marble_wall"], 8)
    box("elf_arch_top", (2.0, 0.3, 0.25), (ax, ay, top_z(4, 6) + 2.6), M["marble_wall"], bevel=0.04)
    billboard("s_elf", (cell_xy(2, 6)[0], cell_xy(2, 6)[1] - 0.4, top_z(2, 6)))


def dwarves(M):
    z = top_z(10, 7)
    x0, y0 = cell_xy(10, 7)
    box("dwarf_hold", (5.4, 3.4, 3.2), (x0, y0 + 0.6, z), M["granite_wall"], bevel=0.06)
    for k in range(7):
        box(f"dwarf_merlon{k}", (0.5, 3.4, 0.55), (x0 - 2.45 + k * 0.82, y0 + 0.6, z + 3.2), M["granite_wall"], bevel=0.03)
    box("dwarf_gate", (1.6, 0.25, 2.3), (x0, y0 - 1.12, z), M["forge_glow"], bevel=0.02)
    box("dwarf_gate_frame", (2.2, 0.35, 2.7), (x0, y0 - 1.0, z), M["bronze"], bevel=0.04)
    for k, dx in enumerate((-1.8, 1.8)):
        box(f"dwarf_chimney{k}", (0.7, 0.7, 2.4), (x0 + dx, y0 + 1.4, z + 3.2), M["granite_wall"], bevel=0.03)
        box(f"dwarf_chimney_fire{k}", (0.5, 0.5, 0.15), (x0 + dx, y0 + 1.4, z + 5.6), M["forge_glow"], bevel=0)
    # forja exterior y canal de lava
    fx, fy = cell_xy(9, 5)
    box("anvil_base", (0.4, 0.3, 0.55), (fx, fy, top_z(9, 5)), M["iron"], bevel=0.02)
    box("anvil_top", (0.8, 0.3, 0.18), (fx, fy, top_z(9, 5) + 0.55), M["iron"], bevel=0.03)
    box("lava_trough", (3.6, 0.5, 0.12), (cell_xy(10, 5)[0] + 0.5, fy + 0.6, top_z(10, 5)), M["lava"], bevel=0)
    point_light("forge_light", (x0, y0 - 1.7, z + 1.4), (1.0, 0.5, 0.15), 700, 0.3)
    point_light("anvil_light", (fx, fy + 0.6, top_z(9, 5) + 0.6), (1.0, 0.4, 0.1), 260, 0.2)
    billboard("s_dwarf", (fx - 0.7, fy - 0.3, top_z(9, 5)))


def demons(M):
    z = top_z(7, 8)
    x0, y0 = (cell_xy(6, 8)[0] + cell_xy(7, 8)[0]) / 2, cell_xy(7, 8)[1] - 0.4
    # aguja de obsidiana: bloques cada vez más finos y girados
    h = z
    for k in range(9):
        s = 2.6 * (1 - k / 10.5)
        hh = 1.3 if k < 7 else 1.0
        box(f"spire_{k}", (s, s, hh), (x0, y0, h), M["obsidian_wall"], rot=k * 9, bevel=0.03)
        h += hh
    cyl("spire_tip", 0.5, 2.4, (x0, y0, h), M["obsidian_wall"], 4, r_top=0.0, rot=(0, 0, 45))
    # púas laterales
    for k in range(6):
        a = k / 6 * math.tau
        cyl(f"spire_horn{k}", 0.18, 1.6, (x0 + math.cos(a) * 1.3, y0 + math.sin(a) * 1.3, z + 2.0 + k % 2), M["obsidian_wall"], 5, r_top=0.0, rot=(math.degrees(math.sin(a)) * 0.6, -math.degrees(math.cos(a)) * 0.6, 0))
    # portal y foso de lava
    px, py = cell_xy(8, 6)
    bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.14, location=(px, py, top_z(8, 6) + 1.2), rotation=(math.radians(90), 0, 0))
    t = bpy.context.active_object
    bpy.context.scene.collection.objects.unlink(t) if False else None
    t.data.materials.append(M["demon_glow"])
    ALL.append(t)
    cyl("portal_core", 0.86, 0.04, (px, py + 0.02, top_z(8, 6) + 1.2), M["portal"], 24, rot=(90, 0, 0))
    lx, ly = cell_xy(5, 7)
    box("lava_pool", (1.6, 1.6, 0.1), (lx, ly, top_z(5, 7)), M["lava"], bevel=0)
    point_light("portal_light", (px, py - 0.8, top_z(8, 6) + 1.2), (1.0, 0.08, 0.05), 900, 0.3)
    point_light("spire_light", (x0, y0 - 2.0, z + 3.0), (1.0, 0.1, 0.05), 600, 0.4)
    billboard("s_demon", (cell_xy(6, 6)[0] + 0.3, cell_xy(6, 6)[1] - 0.2, top_z(6, 6)))


def vegetation(M):
    trunk, dead = M["bark"], M["dead_wood"]
    def pine(x, y, z, h, leaf):
        cyl("pine_trunk", 0.12, h * 0.35, (x, y, z), trunk, 6)
        for k in range(3):
            cyl("pine_cone", h * (0.32 - k * 0.07), h * 0.42, (x, y, z + h * (0.25 + k * 0.2)), leaf, 7, r_top=0.0)
    def dead_tree(x, y, z, h):
        cyl("dead_trunk", 0.14, h, (x, y, z), dead, 6, r_top=0.05)
        for k in range(4):
            a = rnd.uniform(0, math.tau)
            cyl("dead_branch", 0.05, h * 0.45, (x, y, z + h * rnd.uniform(0.45, 0.8)), dead, 5, r_top=0.01, rot=(math.degrees(math.cos(a)) * 0.9, math.degrees(math.sin(a)) * 0.9, 0))
    for j in range(NY):
        for i in range(NX):
            s = surf(i, j)
            x, y = cell_xy(i, j)
            z = top_z(i, j)
            if s == "g" and rnd.random() < 0.5:
                pine(x + rnd.uniform(-0.6, 0.6), y + rnd.uniform(-0.6, 0.6), z, rnd.uniform(2.2, 3.6), M["pine"])
                if rnd.random() < 0.6:
                    billboard("s_bush", (x + rnd.uniform(-0.8, 0.8), y + rnd.uniform(-0.8, 0.8), z), scale=rnd.uniform(0.7, 1.1), flip=rnd.random() < 0.5)
            elif s == "m" and rnd.random() < 0.35:
                pine(x + rnd.uniform(-0.7, 0.7), y + rnd.uniform(-0.7, 0.7), z, rnd.uniform(3.0, 4.2), M["elf_leaf"])
            elif s in "oK" and rnd.random() < 0.25:
                dead_tree(x + rnd.uniform(-0.6, 0.6), y + rnd.uniform(-0.6, 0.6), z, rnd.uniform(1.8, 2.6))
    # puente de madera sobre el río
    bx, by = cell_xy(4, 3)
    box("bridge_deck", (1.5, C + 1.4, 0.2), (bx, by, top_z(4, 2) - 0.1), M["wood"], bevel=0.02)
    for s in (-1, 1):
        box(f"bridge_rail{s}", (0.1, C + 1.4, 0.1), (bx + s * 0.7, by, top_z(4, 2) + 0.7), M["dark_wood"], bevel=0.01)
        for k in range(4):
            box(f"bridge_post{s}_{k}", (0.12, 0.12, 0.8), (bx + s * 0.7, by - C / 2 - 0.5 + k * 1.0, top_z(4, 2)), M["dark_wood"], bevel=0.01)


# ───────────────────────── 4·5. cámara, luz, volumen, color y compositor ─────────────────────────
def setup_world():
    w = bpy.data.worlds.new("Night")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background") or w.node_tree.nodes.new("ShaderNodeBackground")
    bg.inputs[0].default_value = (0.03, 0.035, 0.07, 1)
    bg.inputs[1].default_value = 1.2


def setup_sun():
    d = bpy.data.lights.new("Sun", "SUN")
    d.energy = 4.0
    d.color = (1.0, 0.78, 0.6)       # sol bajo de atardecer
    d.angle = math.radians(5)       # sombras suaves
    o = link(bpy.data.objects.new("Sun", d))
    o.rotation_euler = (math.radians(52), 0, math.radians(-30))
    rim = bpy.data.lights.new("Moon", "SUN")
    rim.energy = 0.6
    rim.color = (0.45, 0.55, 1.0)
    rim.angle = math.radians(10)
    r = link(bpy.data.objects.new("Moon", rim))
    r.rotation_euler = (math.radians(60), 0, math.radians(40))


def setup_volume():
    """Cubo con Principled Volume de baja densidad (atmósfera)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    m = bpy.data.materials.new("Atmos")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    v = nt.nodes.new("ShaderNodeVolumePrincipled")
    v.inputs["Density"].default_value = 0.012
    v.inputs["Color"].default_value = (0.7, 0.72, 0.9, 1)
    v.inputs["Anisotropy"].default_value = 0.35
    nt.links.new(v.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    o = mesh_obj("Atmosphere", bm, [m])
    o.scale = (NX * C + 6, NY * C + 6, 22)
    o.location = (0, 0, 6)
    return o


def finalize_scale():
    """Escala 1:20 de maqueta: todo cuelga de una raíz escalada."""
    root = bpy.data.objects.new("Diorama", None)
    bpy.context.scene.collection.objects.link(root)
    for o in ALL:
        if o.parent is None and o.type != "LIGHT" or (o.type == "LIGHT" and o.data.type != "SUN"):
            o.parent = root
    root.scale = (S, S, S)
    bpy.context.view_layer.update()
    # la densidad del volumen se mide por unidad de mundo → compensar la escala
    atm = bpy.data.objects.get("Atmosphere")
    if atm:
        atm.active_material.node_tree.nodes["Principled Volume"].inputs["Density"].default_value /= S
    return root


SHOTS = {  # (objetivo en celdas i, j, elevación, azimut, ajuste de encuadre)
    "hero": ((5.5, 4.3), 40, -28, 1.5),
    "humans": ((2.0, 1.2), 36, -18, 0.42),
    "demons": ((6.8, 6.9), 40, -30, 0.5),
}


def setup_camera():
    (ci, cj), elev, azim, frac = SHOTS.get(CFG["shot"], SHOTS["hero"])
    cx, cy = (-NX * C / 2 + C * ci + C / 2) * S, (-NY * C / 2 + C * cj + C / 2) * S
    cz = 1.6 * S
    lens = 65.0
    cam_d = bpy.data.cameras.new("Cam")
    cam_d.lens = lens
    cam_d.sensor_width = 36
    half = (NX * C) * S * 0.5 * frac
    fov = 2 * math.atan(18 / lens)
    dist = half / math.tan(fov / 2) * 1.05
    e, a = math.radians(elev), math.radians(azim)
    cam = bpy.data.objects.new("Cam", cam_d)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = (cx + math.sin(a) * math.cos(e) * dist, cy - math.cos(a) * math.cos(e) * dist, cz + math.sin(e) * dist)
    focus = bpy.data.objects.new("Focus", None)
    bpy.context.scene.collection.objects.link(focus)
    focus.location = (cx, cy, cz)
    tr = cam.constraints.new("TRACK_TO")
    tr.target = focus
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    cam_d.clip_start = 0.01
    cam_d.clip_end = 100
    cam_d.dof.use_dof = True
    cam_d.dof.focus_object = focus
    cam_d.dof.aperture_fstop = 1.8
    cam_d.dof.aperture_blades = 7
    bpy.context.scene.camera = cam
    return cam


def setup_render():
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = CFG["res"]
    sc.render.resolution_percentage = 100
    sc.render.filepath = CFG["out"]
    sc.render.image_settings.file_format = "PNG"
    if CFG["engine"] == "EEVEE":
        ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in ids else "BLENDER_EEVEE"
        ee = sc.eevee
        for attr, val in [("taa_render_samples", CFG["samples"]), ("use_volumetric_shadows", True), ("volumetric_tile_size", "4"), ("use_gtao", True), ("use_shadows", True), ("use_raytracing", True)]:
            try: setattr(ee, attr, val)
            except Exception: pass
    else:
        sc.render.engine = "CYCLES"
        sc.cycles.samples = CFG["samples"]
        sc.cycles.use_denoising = True
        sc.cycles.max_bounces = 6
        sc.cycles.volume_bounces = 1
        sc.cycles.volume_step_rate = 4.0
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for dev in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
                try:
                    prefs.compute_device_type = dev
                    prefs.get_devices()
                    if any(d.type == dev for d in prefs.devices):
                        for d in prefs.devices: d.use = True
                        sc.cycles.device = "GPU"
                        log("GPU: " + dev)
                        break
                except Exception:
                    continue
        except Exception:
            pass
    vs = sc.view_settings
    for vt in ("AgX", "Filmic"):
        try:
            vs.view_transform = vt
            break
        except Exception:
            continue
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "AgX - Punchy", "Punchy"):
        try:
            vs.look = look
            break
        except Exception:
            continue
    vs.exposure = 0.6


def setup_compositor():
    """Glare (Fog Glow) sutil + viñeteado. Compatible con el compositor de 4.x y el de 5.x."""
    sc = bpy.context.scene
    if hasattr(sc, "compositing_node_group"):          # Blender 5.x
        tree = bpy.data.node_groups.new("Post2DHD", "CompositorNodeTree")
        sc.compositing_node_group = tree
        out = tree.nodes.new("NodeGroupOutput")
        tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        out_in = out.inputs[0]
    else:                                              # Blender 4.x
        sc.use_nodes = True
        tree = sc.node_tree
        for n in list(tree.nodes):
            tree.nodes.remove(n)
        out = tree.nodes.new("CompositorNodeComposite")
        out_in = out.inputs["Image"]
    rl = tree.nodes.new("CompositorNodeRLayers")
    gl = tree.nodes.new("CompositorNodeGlare")
    for attr, val in [("glare_type", "FOG_GLOW"), ("quality", "HIGH"), ("mix", -0.75), ("threshold", 1.2), ("size", 7)]:
        try: setattr(gl, attr, val)
        except Exception: pass
    for name, val in [("Type", "Fog Glow"), ("Quality", "High"), ("Threshold", 1.2), ("Strength", 0.35), ("Size", 0.6)]:
        if name in gl.inputs:
            try: gl.inputs[name].default_value = val
            except Exception: pass
    tree.links.new(rl.outputs["Image"], gl.inputs["Image"])
    img_out = gl.outputs["Image"] if "Image" in gl.outputs else gl.outputs[0]
    # viñeta: máscara elíptica desenfocada multiplicada
    try:
        el = tree.nodes.new("CompositorNodeEllipseMask")
        for attr, val in [("width", 0.92), ("height", 0.85)]:
            try: setattr(el, attr, val)
            except Exception: pass
        for name, val in [("Size", (0.92, 0.85))]:
            if name in el.inputs:
                try: el.inputs[name].default_value = val
                except Exception: pass
        bl = tree.nodes.new("CompositorNodeBlur")
        for attr, val in [("size_x", 300), ("size_y", 300), ("use_relative", False)]:
            try: setattr(bl, attr, val)
            except Exception: pass
        if "Size" in bl.inputs:
            try: bl.inputs["Size"].default_value = (300, 300)
            except Exception: pass
        tree.links.new(el.outputs[0], bl.inputs[0])
        try:
            mx = tree.nodes.new("CompositorNodeMixRGB")
            mx.blend_type = "MULTIPLY"
            mx.inputs[0].default_value = 0.55
            a, b2, o = mx.inputs[1], mx.inputs[2], mx.outputs[0]
        except Exception:
            mx = tree.nodes.new("ShaderNodeMix")
            mx.data_type = "RGBA"
            mx.blend_type = "MULTIPLY"
            mx.inputs[0].default_value = 0.55
            a, b2, o = mx.inputs[6], mx.inputs[7], mx.outputs[2]
        tree.links.new(img_out, a)
        tree.links.new(bl.outputs[0], b2)
        tree.links.new(o, out_in)
        log("Compositor: Glare Fog Glow + viñeta")
    except Exception as e:
        tree.links.new(img_out, out_in)
        log("Compositor: Glare (viñeta no disponible en esta versión: %s)" % e)


# ───────────────────────── montaje ─────────────────────────
def materials():
    sc = 0.5  # repeticiones por metro (64 px cada 2 m → 32 px/m)
    return {
        "grass": pixel_mat("Grass", "grass", (0.7, 0.95), 0.3, repeat=sc),
        "cobble": pixel_mat("WetCobble", "cobble", (0.08, 0.5), 0.6, repeat=sc, wet=True),
        "dirt": pixel_mat("Dirt", "dirt", (0.6, 0.9), 0.4, repeat=sc),
        "mud": pixel_mat("Mud", "dirt", (0.15, 0.6), 0.5, repeat=sc, tint=(0.55, 0.45, 0.35), wet=True),
        "marble": pixel_mat("ElfMarble", "marble", (0.15, 0.35), 0.25, repeat=sc),
        "obsidian": pixel_mat("Obsidian", "obsidian", (0.05, 0.3), 0.4, repeat=sc, emission=4.0),
        "granite": pixel_mat("Granite", "dwarf", (0.4, 0.75), 0.5, repeat=sc),
        "riverbed": pixel_mat("Riverbed", "cliff", (0.3, 0.6), 0.4, repeat=sc, tint=(0.35, 0.4, 0.4)),
        "cliff": pixel_mat("Cliff", "cliff", (0.55, 0.9), 0.7, repeat=sc, tint=(0.75, 0.72, 0.8)),
        "cliff_wall": pixel_mat("StoneWall", "cliff", (0.5, 0.85), 0.6, repeat=0.8),
        "stone_step": pixel_mat("Steps", "cobble", (0.3, 0.7), 0.4, repeat=0.8),
        "plinth": pixel_mat("Plinth", "wood", (0.35, 0.6), 0.3, repeat=0.3, tint=(0.4, 0.3, 0.25)),
        "wood": pixel_mat("Wood", "wood", (0.55, 0.85), 0.5, repeat=0.8),
        "dark_wood": flat_mat("DarkWood", (0.07, 0.04, 0.03), 0.8),
        "slate": pixel_mat("Slate", "slate", (0.2, 0.55), 0.6, repeat=0.8),
        "thatch": pixel_mat("Hide", "thatch", (0.7, 0.95), 0.6, repeat=0.9),
        "marble_wall": pixel_mat("ElfWall", "marble", (0.15, 0.35), 0.25, repeat=0.9),
        "elf_roof": pixel_mat("ElfRoof", "slate", (0.15, 0.4), 0.4, repeat=0.9, tint=(0.25, 0.85, 0.75)),
        "granite_wall": pixel_mat("DwarfWall", "dwarf", (0.35, 0.7), 0.6, repeat=0.7),
        "obsidian_wall": pixel_mat("ObsidianWall", "obsidian", (0.04, 0.25), 0.45, repeat=0.7, emission=5.0),
        "water": water_mat(),
        "window": flat_mat("Window", (1.0, 0.6, 0.25), 0.3, emission=(1.0, 0.55, 0.2), strength=8.0),
        "lantern": flat_mat("Lantern", (1.0, 0.7, 0.35), 0.3, emission=(1.0, 0.65, 0.3), strength=12.0),
        "fire": flat_mat("Fire", (1.0, 0.4, 0.1), 0.5, emission=(1.0, 0.35, 0.05), strength=25.0),
        "forge_glow": flat_mat("Forge", (1.0, 0.45, 0.1), 0.4, emission=(1.0, 0.4, 0.08), strength=8.0),
        "lava": flat_mat("Lava", (1.0, 0.25, 0.03), 0.2, emission=(1.0, 0.18, 0.02), strength=5.0),
        "teal_glow": flat_mat("ElfCrystal", (0.3, 1.0, 0.9), 0.1, emission=(0.2, 1.0, 0.85), strength=10.0),
        "demon_glow": flat_mat("DemonRune", (1.0, 0.05, 0.03), 0.2, emission=(1.0, 0.04, 0.02), strength=20.0),
        "portal": flat_mat("Portal", (0.25, 0.0, 0.05), 0.0, emission=(0.7, 0.02, 0.12), strength=3.0),
        "iron": flat_mat("Iron", (0.12, 0.12, 0.13), 0.25, metal=1.0),
        "bronze": flat_mat("Bronze", (0.55, 0.35, 0.12), 0.28, metal=1.0),
        "bone": flat_mat("Bone", (0.85, 0.8, 0.65), 0.6),
        "bark": flat_mat("Bark", (0.12, 0.08, 0.05), 0.9),
        "dead_wood": flat_mat("DeadWood", (0.18, 0.15, 0.14), 0.9),
        "pine": pixel_mat("Pine", "grass", (0.6, 0.9), 0.4, repeat=1.5, tint=(0.35, 0.55, 0.45)),
        "elf_leaf": pixel_mat("ElfLeaf", "grass", (0.5, 0.8), 0.4, repeat=1.5, tint=(0.4, 1.0, 0.85)),
    }


def build():
    reset()
    log("Materiales")
    M = materials()
    log("Terreno")
    build_terrain(M)
    log("Facciones: humanos, orcos, elfos, enanos, demonios")
    humans(M); orcs(M); elves(M); dwarves(M); demons(M)
    log("Vegetación y puente")
    vegetation(M)
    setup_volume()
    setup_world()
    setup_sun()
    finalize_scale()
    cam = setup_camera()
    aim_billboards(cam)
    setup_render()
    setup_compositor()
    log("Escena lista: %d objetos" % len(ALL))


build()
if CFG["render"]:
    log("Render %s %dx%d, %d muestras → %s" % (CFG["engine"], CFG["res"][0], CFG["res"][1], CFG["samples"], CFG["out"]))
    bpy.ops.render.render(write_still=True)
    log("Hecho")
