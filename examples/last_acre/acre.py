"""
The Last Acre · el Acre en Blender (3D estilizado)
==================================================
Isla flotante del jugador: huertos y trigal, herrería con fragua, invernadero de
cristal, torre de alquimia, observatorio envuelto en raíces, Portal de las Raíces,
Cámara Comercial y casas; raíces doradas colgando que conectan con los Acres de
otros jugadores (la Red de las Raíces) en un vacío cósmico violeta.

Estados (consecuencias visibles de las decisiones):
  --state neutral   el Acre al empezar
  --state conquer   tras conquistar Sylvaran: invernadero élfico, madera primordial, árboles dorados
  --state destroy   tras destruir Sylvaran: altar carmesí, portal corrompido, campos marchitos

Uso:
  blender -b -P acre.py -- [--state neutral|conquer|destroy] [--shot hero|iso|network]
         [--res 1600x900] [--samples 64] [--out acre.png] [--save-blend acre.blend]
"""
import math
import os
import random
import sys

import bpy
import bmesh
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "fortress"))
import build_fortress as F  # noqa: E402  materiales de detalle y utilidades

A = {"state": "neutral", "shot": "hero", "res": (1600, 900), "samples": 64, "out": os.path.join(HERE, "acre.png"), "blend": None, "render": True}
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
for i, a in enumerate(argv):
    if a == "--state": A["state"] = argv[i + 1]
    if a == "--shot": A["shot"] = argv[i + 1]
    if a == "--res": A["res"] = tuple(int(v) for v in argv[i + 1].split("x"))
    if a == "--samples": A["samples"] = int(argv[i + 1])
    if a == "--out": A["out"] = argv[i + 1]
    if a == "--save-blend": A["blend"] = argv[i + 1]
    if a == "--no-render": A["render"] = False
    if a == "--time": A["time"] = argv[i + 1]
    if a == "--chars": A["chars"] = True
A.setdefault("time", "day")
ST = A["state"]
TIME = A["time"]
NIGHT = TIME == "night"
S = 0.05                     # escala de maqueta (40 m de isla → 2 unidades)
F.S = S
R = random.Random(9)
OBJS = []

# imágenes: carpeta propia → mundo → fortaleza
_orig = F.image


def image(key):
    if key not in F.IMGS:
        for d in (os.path.join(HERE, "images"), os.path.join(HERE, "..", "world", "images")):
            p = os.path.join(d, key + ".png")
            if os.path.exists(p):
                F.IMGS[key] = bpy.data.images.load(p, check_existing=True)
                return F.IMGS[key]
    return _orig(key)


F.image = image


def log(m):
    print("ACRE:", m, flush=True)


# ───────────────────────── utilidades ─────────────────────────
def link(o, mat=None):
    bpy.context.scene.collection.objects.link(o)
    if mat is not None and o.data is not None and hasattr(o.data, "materials"):
        o.data.materials.append(mat)
    OBJS.append(o)
    return o


def bevel(o, w=0.08, seg=2):
    m = o.modifiers.new("Bevel", "BEVEL"); m.width = w; m.segments = seg; m.limit_method = "ANGLE"
    return o


def smooth(o):
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def box(name, size, loc, mat, rot=(0, 0, 0), bev=0.06, base=True):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if base:
        bmesh.ops.translate(bm, vec=Vector((0, 0, size[2] / 2)), verts=bm.verts)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc; o.rotation_euler = [math.radians(a) for a in rot]
    link(o, mat)
    return bevel(o, bev) if bev else o


def cyl(name, r, h, loc, mat, verts=24, r2=None, rot=(0, 0, 0), sm=True, bev=0.03):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r if r2 is None else r2, depth=h)
    bmesh.ops.translate(bm, vec=Vector((0, 0, h / 2)), verts=bm.verts)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc; o.rotation_euler = [math.radians(a) for a in rot]
    link(o, mat)
    if sm:
        smooth(o)
    return bevel(o, bev, 1) if bev else o


def sphere(name, r, loc, mat, scale=(1, 1, 1), seg=24, half=False):
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)
    if half:
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z < -1e-4], context="VERTS")
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc; o.scale = scale
    link(o, mat)
    return smooth(o)


def gable(name, w, d, h, loc, mat, over=0.5, rot=0):
    bm = bmesh.new()
    W, D = w / 2 + over, d / 2 + over
    v = [bm.verts.new(p) for p in [(-W, -D, 0), (W, -D, 0), (0, -D, h), (-W, D, 0), (W, D, 0), (0, D, h)]]
    for f in [(v[0], v[1], v[2]), (v[5], v[4], v[3]), (v[0], v[2], v[5], v[3]), (v[1], v[4], v[5], v[2]), (v[0], v[3], v[4], v[1])]:
        bm.faces.new(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); o.location = loc; o.rotation_euler.z = math.radians(rot)
    link(o, mat)
    s = o.modifiers.new("Solid", "SOLIDIFY"); s.thickness = 0.3
    bevel(o, 0.06)
    # hileras de tejas sobre ambas aguas (detalle real, no solo textura)
    half = w / 2 + over; ln = math.hypot(half, h); ang = math.degrees(math.atan2(h, half))
    rows = max(3, int(ln / 0.55))
    for side in (-1, 1):
        for r in range(rows):
            t = (r + 0.5) / rows
            lx, lz = side * half * (1 - t), h * t + 0.18
            ca, sa = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            tile = box(f"{name}_tiles", (ln / rows * 1.15, d + over * 2 + 0.1, 0.12), (loc[0] + lx * ca, loc[1] + lx * sa, loc[2] + lz - 0.06),
                       mat, (0, side * ang, rot), bev=0.04, base=False)
    return o


def curve(name, pts, radius, mat, taper=(1.0, 0.25), res=12):
    """Raíz / tubo orgánico por puntos (spline NURBS con radio decreciente)."""
    cu = bpy.data.curves.new(name, "CURVE"); cu.dimensions = "3D"
    cu.bevel_depth = radius; cu.bevel_resolution = 3; cu.resolution_u = res
    sp = cu.splines.new("NURBS"); sp.points.add(len(pts) - 1)
    for k, p in enumerate(pts):
        sp.points[k].co = (p[0], p[1], p[2], 1)
        t = k / max(1, len(pts) - 1)
        sp.points[k].radius = taper[0] * (1 - t) + taper[1] * t
    sp.use_endpoint_u = True; sp.order_u = 3
    o = bpy.data.objects.new(name, cu)
    link(o, mat)
    return o


def plight(loc, color, power, radius=0.3):
    d = bpy.data.lights.new("pl", "POINT"); d.color = color; d.energy = power * S * S; d.shadow_soft_size = radius * S
    o = bpy.data.objects.new("pl", d); o.location = loc; link(o)


# ───────────────────────── materiales ─────────────────────────
def mats():
    D, fl = F.detail_mat, F.flat
    wither = ST == "destroy"
    M = {
        "grass": D("Grass", "meadow", "box", repeat=0.18, grime=0, edge=0.05, ao=0.6, tint=(0.62, 0.62, 0.42) if wither else (0.85, 1.0, 0.75)),
        "rock": D("Rock", "moss_rock", "box", repeat=0.12, grime=0, edge=0.35, ao=0.8, tint=(0.62, 0.55, 0.62)),
        "soil": D("Soil", "dirt", "box", repeat=0.4, grime=0, edge=0.1, ao=0.6, tint=(0.62, 0.5, 0.42)),
        "path": D("Path", "paving", "box", repeat=0.35, grime=0, edge=0.1),
        "wood": D("Wood", "wood", "box", repeat=0.5, grime=0.6, edge=0.25),
        "wood_dark": D("WoodDark", "wood", "box", repeat=0.5, grime=0.6, edge=0.25, tint=(0.45, 0.35, 0.3)),
        "stone": D("Stone", "wall", "box", repeat=0.4, grime=1.0, edge=0.3),
        "roof": D("Roof", "roof_red", "box", repeat=0.45, grime=0, edge=0.15, rough=0.55),
        "slate": D("SlateRoof", "roof", "box", repeat=0.45, grime=0, edge=0.15, rough=0.5),
        "bark": D("Bark", "wood", "box", repeat=0.8, grime=0, edge=0.3, tint=(0.55, 0.42, 0.32)),
        "leaves": D("Leaves", "leaves_cube", "box", repeat=0.6, grime=0, edge=0.05, ao=0.7, tint=(0.75, 0.62, 0.38) if wither else (0.6, 0.95, 0.5)),
        "wheat": D("Wheat", "crop", "box", repeat=0.8, grime=0, edge=0.1, tint=(0.7, 0.55, 0.4) if wither else (1.0, 0.92, 0.6)),
        "crop": fl("CropLeaf", (0.4, 0.35, 0.2) if wither else (0.25, 0.62, 0.22), 0.7),
        "pumpkin": fl("Pumpkin", (0.95, 0.5, 0.1), 0.5),
        "brass": fl("Brass", (0.85, 0.6, 0.25), 0.25, metal=1.0),
        "copper": fl("Copper", (0.85, 0.42, 0.25), 0.3, metal=1.0),
        "iron": fl("Iron", (0.15, 0.15, 0.17), 0.35, metal=1.0),
        "white_wood": fl("WhiteWood", (0.92, 0.9, 0.85), 0.5),
        "forge": fl("Forge", (1, 0.45, 0.1), 0.4, emission=(1, 0.42, 0.08), strength=14),
        "window": fl("Window", (1, 0.75, 0.4), 0.3, emission=(1, 0.7, 0.35), strength=6),
        "lantern": fl("Lantern", (1, 0.8, 0.45), 0.3, emission=(1, 0.75, 0.4), strength=16),
        "root_glow": fl("RootGlow", (0.95, 0.62, 0.2), 0.4, emission=(1.0, 0.6, 0.15), strength=2.6 if ST != "destroy" else 1.0),
        "root_red": fl("RootRed", (0.9, 0.1, 0.08), 0.3, emission=(1.0, 0.08, 0.05), strength=9),
        "potion_g": fl("PotionG", (0.3, 1, 0.5), 0.1, emission=(0.2, 1, 0.45), strength=6),
        "potion_p": fl("PotionP", (0.8, 0.3, 1), 0.1, emission=(0.7, 0.25, 1), strength=6),
        "potion_b": fl("PotionB", (0.3, 0.6, 1), 0.1, emission=(0.25, 0.55, 1), strength=6),
        "plant_glow": fl("PlantGlow", (0.9, 0.4, 1.0), 0.4, emission=(0.85, 0.35, 1.0), strength=5),
        "plant_teal": fl("PlantTeal", (0.3, 1.0, 0.85), 0.4, emission=(0.25, 1.0, 0.8), strength=5),
        "crimson": fl("Crimson", (0.9, 0.05, 0.1), 0.15, emission=(1.0, 0.05, 0.08), strength=10),
        "obsidian": fl("Obsidian", (0.05, 0.04, 0.06), 0.2),
        "cloth_r": fl("ClothR", (0.85, 0.2, 0.18), 0.8), "cloth_y": fl("ClothY", (0.95, 0.78, 0.3), 0.8), "cloth_t": fl("ClothT", (0.15, 0.6, 0.62), 0.8),
        "smoke": fl("Smoke", (0.85, 0.85, 0.9), 1.0),
        "gold_glow": fl("GoldGlow", (1, 0.85, 0.4), 0.2, emission=(1, 0.8, 0.35), strength=12),
    }
    M["path_soft"] = soft_mat("PathSoft", "dirt", 0.35, (1.05, 0.93, 0.78))
    M["plaza_soft"] = soft_mat("PlazaSoft", "paving", 0.45, (0.95, 0.92, 0.88), edge=0.12)
    M["blade2"] = fl("Blade2", (0.45, 0.4, 0.18) if wither else (0.42, 0.7, 0.25), 0.6)
    M["blade3"] = fl("Blade3", (0.38, 0.34, 0.16) if wither else (0.26, 0.5, 0.18), 0.6)
    M["leaves_b"] = D("LeavesB", "leaves_cube", "box", repeat=0.6, grime=0, edge=0.05, ao=0.7, tint=(0.75, 0.55, 0.3) if wither else (0.45, 0.8, 0.42))
    M["flower_r"] = fl("FlowerR", (0.9, 0.25, 0.22), 0.5)
    M["rope"] = fl("Rope", (0.75, 0.62, 0.4), 0.9)
    M["build_glow"] = fl("BuildGlow", (0.4, 1.0, 0.85), 0.3, emission=(0.35, 1.0, 0.8), strength=3.0)
    M["yard"] = D("Yard", "dirt", "box", repeat=0.3, grime=0, edge=0.05, ao=0.6, tint=(0.85, 0.72, 0.58))
    M["dirtband"] = D("DirtBand", "dirt", "box", repeat=0.25, grime=0, edge=0.25, ao=0.75, tint=(0.62, 0.48, 0.38))
    M["blade"] = fl("Blade", (0.42, 0.42, 0.18) if wither else (0.32, 0.62, 0.2), 0.6)
    M["vine"] = fl("Vine", (0.2, 0.42, 0.15), 0.7)
    M["flower_y"] = fl("FlowerY", (1.0, 0.82, 0.25), 0.5); M["flower_w"] = fl("FlowerW", (0.98, 0.96, 0.92), 0.5); M["flower_p"] = fl("FlowerP", (0.85, 0.45, 0.9), 0.5)
    M["crys_teal"] = fl("CrysTeal", (0.3, 1.0, 0.9), 0.1, emission=(0.25, 1.0, 0.85), strength=6)
    M["crys_violet"] = fl("CrysViolet", (0.7, 0.35, 1.0), 0.1, emission=(0.65, 0.3, 1.0), strength=6)
    M["firefly"] = fl("Firefly", (1.0, 0.9, 0.5), 0.3, emission=(1.0, 0.85, 0.4), strength=30)
    M["water"] = F.water_mat("PondWater", (0.08, 0.32, 0.4), 0.03)
    M["falls"] = F.water_mat("FallsW", (0.62, 0.8, 0.9), 0.12, foam=1.0)
    M["foam"] = fl("Foam", (0.95, 0.98, 1.0), 0.6)
    mist = bpy.data.materials.new("Mist"); mist.use_nodes = True
    mb = mist.node_tree.nodes["Principled BSDF"]; mb.inputs["Base Color"].default_value = (0.9, 0.95, 1, 1); mb.inputs["Alpha"].default_value = 0.25
    M["mist"] = mist
    # hierba con variación de tono (manchas claras/oscuras) sobre la textura
    gm = M["grass"]; nt = gm.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    base_link = next((l for l in nt.links if l.to_socket == bsdf.inputs["Base Color"]), None)
    if base_link:
        src = base_link.from_socket
        nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 0.08 / S * 0.05
        tcg = nt.nodes.new("ShaderNodeTexCoord"); nt.links.new(tcg.outputs["Object"], nz.inputs["Vector"])
        cr = nt.nodes.new("ShaderNodeValToRGB")
        cr.color_ramp.elements[0].color = (0.62, 0.7, 0.42, 1) if not wither else (0.6, 0.55, 0.4, 1)
        cr.color_ramp.elements[1].color = (1.1, 1.08, 0.75, 1) if not wither else (0.85, 0.75, 0.55, 1)
        nt.links.new(nz.outputs["Fac"], cr.inputs[0])
        mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.blend_type = "MULTIPLY"; mx.inputs[0].default_value = 1.0
        nt.links.new(src, mx.inputs[6]); nt.links.new(cr.outputs[0], mx.inputs[7])
        nt.links.new(mx.outputs[2], bsdf.inputs["Base Color"])
    # cristal
    g = bpy.data.materials.new("Glass"); g.use_nodes = True
    b = g.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.75, 0.92, 1.0, 1); b.inputs["Roughness"].default_value = 0.05
    tw = F.bsdf_in(b, "Transmission Weight", "Transmission")
    if tw: tw.default_value = 0.92
    b.inputs["IOR"].default_value = 1.45
    M["glass"] = g
    # vórtice del portal: espiral emisiva
    v = bpy.data.materials.new("Vortex"); v.use_nodes = True; nt = v.node_tree; L = nt.links.new
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ"); L(tc.outputs["Object"], sep.inputs[0])
    at = nt.nodes.new("ShaderNodeMath"); at.operation = "ARCTAN2"; L(sep.outputs["Z"], at.inputs[0]); L(sep.outputs["X"], at.inputs[1])
    ln = nt.nodes.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; L(tc.outputs["Object"], ln.inputs[0])
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 9.0; L(ln.outputs["Value"], mul.inputs[0])
    add = nt.nodes.new("ShaderNodeMath"); add.operation = "ADD"; L(at.outputs[0], add.inputs[0]); L(mul.outputs[0], add.inputs[1])
    sn = nt.nodes.new("ShaderNodeMath"); sn.operation = "SINE"; L(add.outputs[0], sn.inputs[0])
    cr = nt.nodes.new("ShaderNodeValToRGB")
    c1, c2 = ((0.05, 0.0, 0.0, 1), (1.0, 0.1, 0.05, 1)) if ST == "destroy" else ((0.15, 0.02, 0.35, 1), (1.0, 0.75, 0.3, 1))
    cr.color_ramp.elements[0].color = c1; cr.color_ramp.elements[1].color = c2
    L(sn.outputs[0], cr.inputs[0]); L(cr.outputs[0], b.inputs["Base Color"]); L(cr.outputs[0], F.bsdf_in(b, "Emission Color", "Emission"))
    b.inputs["Emission Strength"].default_value = 6
    M["vortex"] = v
    # rayas de toldo
    for name, a_, b_ in (("Awning1", (0.9, 0.22, 0.2), (0.98, 0.9, 0.75)), ("Awning2", (0.15, 0.55, 0.6), (0.98, 0.9, 0.75)), ("Awning3", (0.95, 0.75, 0.25), (0.98, 0.9, 0.75))):
        m = bpy.data.materials.new(name); m.use_nodes = True; nt = m.node_tree
        w = nt.nodes.new("ShaderNodeTexWave"); w.wave_profile = "SAW" if hasattr(w, "wave_profile") else w.wave_profile
        w.inputs["Scale"].default_value = 3.0
        tc = nt.nodes.new("ShaderNodeTexCoord"); nt.links.new(tc.outputs["Object"], w.inputs["Vector"])
        mr = nt.nodes.new("ShaderNodeMath"); mr.operation = "GREATER_THAN"; mr.inputs[1].default_value = 0.5; nt.links.new(w.outputs["Fac"], mr.inputs[0])
        mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"; nt.links.new(mr.outputs[0], mx.inputs[0])
        mx.inputs[6].default_value = a_ + (1,); mx.inputs[7].default_value = b_ + (1,)
        nt.links.new(mx.outputs[2], nt.nodes["Principled BSDF"].inputs["Base Color"])
        M[name.lower()] = m
    return M


# ───────────────────────── isla flotante ─────────────────────────
FOOTPRINTS = []   # (x, y, r): patios de tierra batida bajo los edificios (sin hierba)
PATHS = [  # caminos de tierra (polilíneas) — red principal del Acre
    [(-6.5, -21), (-1.5, -15.5), (-0.5, -9), (1, -3), (2, 3), (3, 11)],
    [(1, -3), (-4, 0), (-8, 2.5)],
    [(2, 3), (6, 2), (12, -2)],
    [(2, 3), (-2, 8), (-3, 10.5)],
    [(-1.5, -15.5), (-6, -16.5), (-9.5, -14), (-11, -12.5)],
    [(6, 2), (8, 7), (12, 9.5)],
]
PATH_W = 2.6


def d_path(x, y):
    best = 1e9
    for pl in PATHS:
        for k in range(len(pl) - 1):
            (ax, ay), (bx, by) = pl[k], pl[k + 1]
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy + 1e-9)))
            best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
    return best


def island(name, R0, depth, M, center=(0, 0, 0), seed=1, top_mat="grass", footprints=None):
    """Isla flotante: cima ondulada, labio de hierba que vuela sobre una franja de tierra,
    y base de roca en estratos que se estrecha hacia abajo.
    Materiales: 0 hierba · 1 roca · 2 patio de tierra · 3 franja de tierra."""
    rnd = random.Random(seed)
    seg, rings = 96, 22
    footprints = footprints or []
    noise = [rnd.uniform(-1, 1) for _ in range(seg)]
    sm = [sum(noise[(i + k) % seg] for k in range(-4, 5)) / 9 for i in range(seg)]
    edge = [R0 * (1 + 0.18 * sm[i] + 0.05 * math.sin(i * 0.7)) for i in range(seg)]
    hfun = (lambda x, y: top_z(x, y, footprints)) if footprints else (lambda x, y: 0.3 * math.sin(x * 0.4) * math.cos(y * 0.3))
    verts, faces, mi = [(0, 0, hfun(0, 0))], [], []
    for r in range(1, rings + 1):
        t = r / rings
        for i in range(seg):
            a = i / seg * math.tau
            rr = edge[i] * t
            x, y = math.cos(a) * rr, math.sin(a) * rr
            verts.append((x, y, hfun(x, y) * (1 - t ** 4) + rnd.uniform(-0.03, 0.03)))

    def top_mat_for(ids):
        cx = sum(verts[v][0] for v in ids) / len(ids); cy = sum(verts[v][1] for v in ids) / len(ids)
        if footprints is FOOTPRINTS and d_path(cx, cy) < PATH_W * 0.42:
            return 2
        return 2 if any(math.hypot(cx - fx, cy - fy) < fr * (0.62 if footprints is FOOTPRINTS else 1) for fx, fy, fr in footprints) else 0
    for i in range(seg):
        f = (0, 1 + i, 1 + (i + 1) % seg); faces.append(f); mi.append(top_mat_for(f))
    for r in range(1, rings):
        o0, o1 = 1 + (r - 1) * seg, 1 + r * seg
        for i in range(seg):
            f = (o0 + i, o1 + i, o1 + (i + 1) % seg, o0 + (i + 1) % seg); faces.append(f); mi.append(top_mat_for(f))
    prev = 1 + (rings - 1) * seg

    def ring(scale, z, jitter=0.0, zj=0.0):
        start = len(verts)
        for i in range(seg):
            a = i / seg * math.tau
            rr = edge[i] * scale * (1 + rnd.uniform(-jitter, jitter))
            verts.append((math.cos(a) * rr, math.sin(a) * rr, z + rnd.uniform(-zj, zj)))
        return start

    def band(a_, b_, m):
        for i in range(seg):
            faces.append((a_ + i, a_ + (i + 1) % seg, b_ + (i + 1) % seg, b_ + i)); mi.append(m)
    lip = ring(1.035, -0.35, 0.01); band(prev, lip, 0)          # labio de hierba que sobresale
    under = ring(0.995, -0.8, 0.01); band(lip, under, 0)
    dirt = ring(0.97, -2.2, 0.02, 0.3); band(under, dirt, 3)     # franja de tierra con raíces
    prev = dirt
    levels = 12
    for k in range(1, levels + 1):
        t = k / levels
        shrink = 0.97 * (1 - t ** 1.25) * (0.93 if k % 2 else 1.0)
        nxt = ring(max(0.04, shrink), -2.2 - (depth - 2.2) * t, 0.08, 0.5)
        band(prev, nxt, 1)
        prev = nxt
    tip = len(verts); verts.append((0, 0, -depth * 1.12))
    for i in range(seg):
        faces.append((prev + i, prev + (i + 1) % seg, tip)); mi.append(1)
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces)
    me.polygons.foreach_set("material_index", mi); me.update()
    for k in (top_mat, "rock", "yard", "dirtband"):
        me.materials.append(M[k])
    o = bpy.data.objects.new(name, me); o.location = center
    link(o)
    o["hfun"] = 1
    return o, edge


def top_z(x, y, fps=None):
    """Relieve suave de la cima, aplanado bajo los edificios (FOOTPRINTS)."""
    h = 0.45 * math.sin(x * 0.21) * math.cos(y * 0.17) + 0.3 * math.sin((x + y) * 0.11)
    f = 1.0
    for fx, fy, fr in (fps if fps is not None else FOOTPRINTS):
        d = math.hypot(x - fx, y - fy)
        if d < fr + 3:
            f = min(f, max(0.0, (d - fr) / 3))
    return 0.1 + (h - 0.1) * f if f < 1 else h


# ───────────────────────── vida: dispersión con Geometry Nodes ─────────────────────────
def scatter_assets(M):
    """Colecciones ocultas para instanciar: hierba, flores, piedras y arbustos (capas con densidades distintas)."""
    cols = {k: bpy.data.collections.new("SRC_" + k) for k in ("grass", "flowers", "pebbles", "bushes", "ferns")}
    def add(o, k):
        if o.name in bpy.context.scene.collection.objects:
            bpy.context.scene.collection.objects.unlink(o)
        if o in OBJS:
            OBJS.remove(o)
        cols[k].objects.link(o)
        return o
    rr = random.Random(77)
    def merge(parts):
        with bpy.context.temp_override(active_object=parts[0], selected_editable_objects=parts, object=parts[0]):
            bpy.ops.object.join()
        for q in parts[1:]:
            if q in OBJS: OBJS.remove(q)
        return parts[0]
    for v, (mat, hmul) in enumerate((("blade", 1.0), ("blade2", 0.8), ("blade3", 1.25))):
        bm = bmesh.new()
        for k in range(11):
            a = rr.uniform(0, math.tau); h = rr.uniform(0.35, 0.8) * hmul; w = 0.05
            lean = rr.uniform(0.1, 0.35); ox, oy = rr.uniform(-0.12, 0.12), rr.uniform(-0.12, 0.12)
            p = lambda dx, dy, z: bm.verts.new((ox + dx, oy + dy, z))
            ca, sa = math.cos(a + 1.57), math.sin(a + 1.57)
            b0, b1 = p(ca * w, sa * w, 0), p(-ca * w, -sa * w, 0)
            m0 = p(math.cos(a) * lean * 0.5 + ca * w * 0.6, math.sin(a) * lean * 0.5 + sa * w * 0.6, h * 0.55)
            m1 = p(math.cos(a) * lean * 0.5 - ca * w * 0.6, math.sin(a) * lean * 0.5 - sa * w * 0.6, h * 0.55)
            tp = p(math.cos(a) * lean, math.sin(a) * lean, h)
            bm.faces.new((b0, b1, m1, m0)); bm.faces.new((m0, m1, tp))
        me = bpy.data.meshes.new(f"tuft{v}"); bm.to_mesh(me); bm.free(); me.materials.append(M[mat])
        add(bpy.data.objects.new(f"tuft{v}", me), "grass")
    for v, m in enumerate(("flower_y", "flower_w", "flower_p", "flower_r")):
        st = cyl(f"fl_stem{v}", 0.022, 0.42, (0, 0, 0), M["blade"], 5, sm=False, bev=0)
        hd = sphere(f"fl_head{v}", 0.1, (0, 0, 0.45), M[m], (1, 1, 0.55), 8)
        add(merge([st, hd]), "flowers")
    for v in range(3):
        add(F.rock(f"pebble{v}", (0.32 + v * 0.1, 0.28, 0.2), M["rock"], seed=200 + v, detail=1), "pebbles")
    for v in range(3):  # arbustos: varias esferas aplastadas con variación de tono
        parts = []
        for k in range(4):
            parts.append(sphere(f"bush{v}_{k}", rr.uniform(0.45, 0.7), (rr.uniform(-0.5, 0.5), rr.uniform(-0.5, 0.5), rr.uniform(0.25, 0.5)), M["leaves" if (v + k) % 3 else "leaves_b"], (1, 1, 0.75), 10))
        add(merge(parts), "bushes")
    for v in range(2):  # helechos: hojas planas en abanico
        bm = bmesh.new()
        for k in range(7):
            a = k / 7 * math.tau + rr.uniform(-0.2, 0.2); L_ = rr.uniform(0.6, 0.9)
            v0 = bm.verts.new((0, 0, 0.05)); v1 = bm.verts.new((math.cos(a + 0.25) * L_ * 0.5, math.sin(a + 0.25) * L_ * 0.5, 0.35))
            v2 = bm.verts.new((math.cos(a) * L_, math.sin(a) * L_, 0.2)); v3 = bm.verts.new((math.cos(a - 0.25) * L_ * 0.5, math.sin(a - 0.25) * L_ * 0.5, 0.35))
            bm.faces.new((v0, v1, v2, v3))
        me = bpy.data.meshes.new(f"fern{v}"); bm.to_mesh(me); bm.free(); me.materials.append(M["vine"])
        add(bpy.data.objects.new(f"fern{v}", me), "ferns")
    return cols


def gn_scatter(target, col, density, mat, scale=(0.7, 1.3), seed=0, name="Scatter"):
    """Geometry Nodes: reparte instancias de la colección sobre las caras con el material indicado."""
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links.new
    gi, go = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    sel = N.new("GeometryNodeMaterialSelection"); sel.inputs["Material"].default_value = mat
    dist = N.new("GeometryNodeDistributePointsOnFaces"); dist.inputs["Density"].default_value = density
    dist.inputs["Seed"].default_value = seed
    L(gi.outputs[0], dist.inputs["Mesh"]); L(sel.outputs[0], dist.inputs["Selection"])
    ci = N.new("GeometryNodeCollectionInfo"); ci.inputs["Collection"].default_value = col
    ci.inputs["Separate Children"].default_value = True; ci.inputs["Reset Children"].default_value = True
    inst = N.new("GeometryNodeInstanceOnPoints")
    L(dist.outputs["Points"], inst.inputs["Points"]); L(ci.outputs[0], inst.inputs["Instance"])
    inst.inputs["Pick Instance"].default_value = True
    def rand(dtype, lo, hi, sd):
        n = N.new("FunctionNodeRandomValue"); n.data_type = dtype
        ins = [i for i in n.inputs if i.enabled]
        mn = next(i for i in ins if i.name == "Min"); mx = next(i for i in ins if i.name == "Max")
        mn.default_value = lo; mx.default_value = hi
        next(i for i in ins if i.name == "Seed").default_value = sd
        return next(o for o in n.outputs if o.enabled)
    L(rand("INT", 0, 100, seed + 1), inst.inputs["Instance Index"])
    L(rand("FLOAT_VECTOR", (0, 0, 0), (0.15, 0.15, math.tau), seed + 2), inst.inputs["Rotation"])
    L(rand("FLOAT", scale[0], scale[1], seed + 3), inst.inputs["Scale"])
    j = N.new("GeometryNodeJoinGeometry")
    L(gi.outputs[0], j.inputs[0]); L(inst.outputs[0], j.inputs[0]); L(j.outputs[0], go.inputs[0])
    mod = target.modifiers.new(name, "NODES"); mod.node_group = ng
    return mod


def edge_life(edge, M, cx=0, cy=0, seed=12):
    """Enredaderas colgando del borde y cristales incrustados en la roca."""
    rr = random.Random(seed)
    seg = len(edge)
    for k in range(38):
        i = rr.randrange(seg); a = i / seg * math.tau; r = edge[i] * 1.02
        x, y = cx + math.cos(a) * r, cy + math.sin(a) * r
        L_ = rr.uniform(2.5, 9)
        pts = [(x, y, -0.4)] + [(x + math.cos(a) * 0.3 * s + rr.uniform(-0.3, 0.3), y + math.sin(a) * 0.3 * s + rr.uniform(-0.3, 0.3), -0.4 - L_ * s / 4) for s in range(1, 5)]
        curve(f"vine{k}", pts, 0.07, M["vine"], (1.0, 0.5))
        for s in range(3):
            p = pts[1 + s]
            sphere("vine_leaf", 0.22, p, M["leaves"], (1, 1, 0.6), 6)
    for k in range(16):
        i = rr.randrange(seg); a = i / seg * math.tau
        t = rr.uniform(0.15, 0.6)
        r = edge[i] * (1 - t ** 1.25) * 0.95
        z = -2.2 - 17 * t
        m = M["crys_teal" if k % 2 else "crys_violet"]
        c = cyl("rock_crystal", rr.uniform(0.35, 0.7), rr.uniform(1.5, 3.2), (cx + math.cos(a) * r, cy + math.sin(a) * r, z), m, 5, 0.0,
                (math.degrees(math.sin(a)) * -0.9, math.degrees(math.cos(a)) * 0.9, 0), sm=False, bev=0)
        if k % 4 == 0:
            plight((cx + math.cos(a) * (r + 2), cy + math.sin(a) * (r + 2), z), (0.4, 1, 0.9) if k % 2 else (0.75, 0.4, 1), 180, 0.3)


def waterfall_edge(edge, M, ang_deg=-120):
    """Estanque → arroyo → cascada que cae del borde al vacío, con espuma y bruma."""
    seg = len(edge); i = int((ang_deg % 360) / 360 * seg); a = math.radians(ang_deg)
    R_ = edge[i]
    px, py = math.cos(a) * R_ * 0.6, math.sin(a) * R_ * 0.6
    bm = bmesh.new(); bmesh.ops.create_circle(bm, cap_ends=True, segments=28, radius=2.4)
    me = bpy.data.meshes.new("pond"); bm.to_mesh(me); bm.free()
    pond = bpy.data.objects.new("pond", me); pond.location = (px, py, top_z(px, py) + 0.08); link(pond, M["water"])
    for k in range(12):
        q = k / 12 * math.tau
        F_rock = F.rock("pond_rock", (0.7, 0.6, 0.45), M["rock"], seed=300 + k, detail=1); F_rock.location = (px + math.cos(q) * 3.4, py + math.sin(q) * 3.4, top_z(px, py)); link(F_rock)
    # arroyo hasta el borde
    pts = []
    for s in range(8):
        t = s / 7
        x = px + (math.cos(a) * R_ * 1.0 - px) * t + math.sin(t * 5) * 0.6
        y = py + (math.sin(a) * R_ * 1.0 - py) * t
        pts.append((x, y, top_z(x, y) + 0.06))
    curve("stream", pts, 0.9, M["water"], (1.0, 0.9))
    # lámina de la cascada: tira que cae siguiendo una parábola
    ex, ey = math.cos(a) * R_ * 1.04, math.sin(a) * R_ * 1.04
    verts, faces = [], []
    n = 30; w = 1.4
    tx, ty = -math.sin(a), math.cos(a)
    for s in range(n + 1):
        t = s / n
        d = t * 7.0
        z = -0.2 - 34 * t ** 1.6
        cx_, cy_ = ex + math.cos(a) * d, ey + math.sin(a) * d
        ww = w * (1 + t * 1.8)
        verts += [(cx_ - tx * ww, cy_ - ty * ww, z), (cx_ + tx * ww, cy_ + ty * ww, z)]
        if s:
            faces.append((2 * s - 2, 2 * s - 1, 2 * s + 1, 2 * s))
    me = bpy.data.meshes.new("falls"); me.from_pydata(verts, [], faces); me.update()
    fo = bpy.data.objects.new("falls", me); link(fo, M["falls"])
    sol = fo.modifiers.new("Solid", "SOLIDIFY"); sol.thickness = 0.25
    for k in range(10):  # espuma en el labio y bruma abajo
        sphere("foam", 0.5 + 0.1 * k, (ex + R.uniform(-1, 1), ey + R.uniform(-1, 1), -0.3 - k * 0.1), M["foam"], (1, 1, 0.6), 10)
    for k in range(8):
        sphere("mist", R.uniform(2, 3.5), (ex + math.cos(a) * 7 + R.uniform(-2, 2), ey + math.sin(a) * 7 + R.uniform(-2, 2), -34 + R.uniform(-2, 2)), M["mist"], (1, 1, 0.6), 12)


def soft_mat(name, key, repeat, tint=(1, 1, 1), edge=0.35):
    """Material de suelo con borde que se funde con la hierba (alpha por distancia al eje + ruido)."""
    m = F.detail_mat(name, key, "box", repeat=repeat, grime=0, edge=0.05, ao=0.55, tint=tint)
    nt = m.node_tree; L = nt.links.new; b = nt.nodes["Principled BSDF"]
    uv = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ"); L(uv.outputs["UV"], sep.inputs[0])
    d = nt.nodes.new("ShaderNodeMath"); d.operation = "SUBTRACT"; d.inputs[1].default_value = 0.5; L(sep.outputs["Y"], d.inputs[0])
    ab = nt.nodes.new("ShaderNodeMath"); ab.operation = "ABSOLUTE"; L(d.outputs[0], ab.inputs[0])
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 18.0
    tco = nt.nodes.new("ShaderNodeTexCoord"); L(tco.outputs["Object"], nz.inputs["Vector"])
    mx = nt.nodes.new("ShaderNodeMath"); mx.operation = "MULTIPLY_ADD"; mx.inputs[2].default_value = -0.12
    L(nz.outputs["Fac"], mx.inputs[0]); mx.inputs[1].default_value = 0.24
    ad = nt.nodes.new("ShaderNodeMath"); ad.operation = "ADD"; L(ab.outputs[0], ad.inputs[0]); L(mx.outputs[0], ad.inputs[1])
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 0.5 - edge; mr.inputs["From Max"].default_value = 0.5
    mr.inputs["To Min"].default_value = 1.0; mr.inputs["To Max"].default_value = 0.0
    L(ad.outputs[0], mr.inputs["Value"]); L(mr.outputs[0], b.inputs["Alpha"])
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    elif hasattr(m, "blend_method"):
        m.blend_method = "BLEND"
    return m


def path_ribbons(M):
    """Caminos como cintas con UV transversal: centro de tierra y bordes fundidos con la hierba."""
    for n, pl in enumerate(PATHS):
        pts = []
        for k in range(len(pl) - 1):
            (ax, ay), (bx, by) = pl[k], pl[k + 1]
            steps = max(2, int(math.hypot(bx - ax, by - ay) / 0.5))
            for s_ in range(steps):
                t = s_ / steps
                pts.append((ax + (bx - ax) * t, ay + (by - ay) * t))
        pts.append(pl[-1])
        verts, faces, uvs = [], [], []
        across = 7
        for i, (x, y) in enumerate(pts):
            j = min(i + 1, len(pts) - 1); h = max(i - 1, 0)
            tx, ty = pts[j][0] - pts[h][0], pts[j][1] - pts[h][1]
            ln = math.hypot(tx, ty) or 1
            nx_, ny_ = -ty / ln, tx / ln
            wob = 1 + 0.18 * math.sin(i * 0.7 + n)
            for c in range(across):
                v = c / (across - 1)
                off = (v - 0.5) * PATH_W * 1.9 * wob
                X, Y = x + nx_ * off, y + ny_ * off
                verts.append((X, Y, top_z(X, Y) + 0.045))
                uvs.append((i * 0.5, v))
            if i:
                for c in range(across - 1):
                    a_ = (i - 1) * across + c
                    faces.append((a_, a_ + 1, a_ + across + 1, a_ + across))
        me = bpy.data.meshes.new(f"path{n}"); me.from_pydata(verts, [], faces)
        uvl = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                uvl.data[li].uv = uvs[me.loops[li].vertex_index]
        o = bpy.data.objects.new(f"path{n}", me); link(o, M["path_soft"])


def plaza(x, y, r, M):
    """Plaza de adoquines con borde orgánico alrededor del portal."""
    seg, rings = 48, 8
    verts, faces, uvs = [(x, y, top_z(x, y) + 0.05)], [], [(0, 0.5)]
    for k in range(1, rings + 1):
        t = k / rings
        for i in range(seg):
            a = i / seg * math.tau
            rr_ = r * t * (1 + 0.12 * math.sin(a * 5) * t)
            X, Y = x + math.cos(a) * rr_, y + math.sin(a) * rr_
            verts.append((X, Y, top_z(X, Y) + 0.05)); uvs.append((a, 0.5 + 0.5 * t))
    for i in range(seg):
        faces.append((0, 1 + i, 1 + (i + 1) % seg))
    for k in range(1, rings):
        o0, o1 = 1 + (k - 1) * seg, 1 + k * seg
        for i in range(seg):
            faces.append((o0 + i, o1 + i, o1 + (i + 1) % seg, o0 + (i + 1) % seg))
    me = bpy.data.meshes.new("plaza"); me.from_pydata(verts, [], faces)
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = uvs[me.loops[li].vertex_index]
    link(bpy.data.objects.new("plaza", me), M["plaza_soft"])


def build_plot(x, y, w, d, M, stage="empty"):
    """Solar construible: estacas y cuerda, marco de selección; 'frame' añade cimientos y andamio."""
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl("stake", 0.07, 0.9, (x + sx * w / 2, y + sy * d / 2, 0.1), M["wood"], 6, 0.03, sm=False, bev=0)
    for (ax, ay), (bx, by) in [((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))]:
        p0 = (x + ax * w / 2, y + ay * d / 2, 0.85); p1 = (x + bx * w / 2, y + by * d / 2, 0.85)
        curve("rope", [p0, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, 0.7), p1], 0.025, M["rope"], (1, 1))
        box("plot_frame", (abs(p1[0] - p0[0]) + 0.12, abs(p1[1] - p0[1]) + 0.12, 0.04), ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, 0.16), M["build_glow"], bev=0) if False else None
    for (ax, ay), (bx, by) in [((-1, -1), (1, -1)), ((1, 1), (-1, 1))]:
        box("plot_edge", (w, 0.08, 0.03), (x, y + ay * d / 2, top_z(x, y) + 0.08), M["build_glow"], bev=0)
    for (ax, ay) in [(-1, 0), (1, 0)]:
        box("plot_edge", (0.08, d, 0.03), (x + ax * w / 2, y, top_z(x, y) + 0.08), M["build_glow"], bev=0)
    box("plot_sign", (0.9, 0.08, 0.6), (x - w / 2 + 0.2, y - d / 2 - 0.4, 0.9), M["wood"], bev=0.02)
    cyl("plot_sign_post", 0.05, 0.9, (x - w / 2 + 0.2, y - d / 2 - 0.4, 0.1), M["wood"], 6, sm=False, bev=0)
    for k in range(4):
        cyl("lumber", 0.14, 2.4, (x + w / 2 + 0.7, y - 0.6 + k * 0.3, 0.25), M["wood"], 8, rot=(90, 0, 0), bev=0.02)
    if stage == "frame":
        box("found", (w - 0.6, d - 0.6, 0.5), (x, y, 0.1), M["stone"], bev=0.05)
        for px in (-1, 0, 1):
            for py in (-1, 1):
                box("frame_post", (0.22, 0.22, 3.4), (x + px * (w / 2 - 0.5), y + py * (d / 2 - 0.5), 0.6), M["wood"], bev=0.02)
        for py in (-1, 1):
            box("frame_beam", (w - 0.8, 0.2, 0.2), (x, y + py * (d / 2 - 0.5), 3.9), M["wood"], bev=0.02)
            box("scaffold", (w + 0.6, 0.12, 0.12), (x, y + py * (d / 2 + 0.3), 1.8), M["wood_dark"], bev=0)
            box("scaffold_plank", (w + 0.6, 0.6, 0.08), (x, y + py * (d / 2 + 0.55), 1.9), M["wood"], bev=0)
        box("wall_half", (w - 0.8, 0.3, 1.4), (x, y - d / 2 + 0.5, 0.6), M["stone"], bev=0.04)


SPRITES = []


def sprite(key, x, y, px_per_m=36.0, flip=False):
    """Personaje pixel art: tarjeta vertical que mira a cámara + sombra de contacto en el suelo."""
    im = image(key)
    if im is None:
        return
    h = im.size[1] / px_per_m
    z = top_z(x, y) + 0.04
    o = billboard(key, (x, y, z), h, None)
    if o is not None:
        SPRITES.append(o)
        if flip:
            o.scale.x = -1
    bm = bmesh.new(); bmesh.ops.create_circle(bm, cap_ends=True, segments=20, radius=1.0)
    me = bpy.data.meshes.new("shadow"); bm.to_mesh(me); bm.free()
    sh = bpy.data.objects.new("blob_shadow", me); sh.location = (x, y, z + 0.02); sh.scale = (h * 0.24, h * 0.13, 1)
    link(sh, SHADOW_MAT[0])


SHADOW_MAT = []


def shadow_material():
    m = bpy.data.materials.new("BlobShadow"); m.use_nodes = True; nt = m.node_tree; L = nt.links.new
    b = nt.nodes["Principled BSDF"]; b.inputs["Base Color"].default_value = (0.02, 0.025, 0.04, 1); b.inputs["Roughness"].default_value = 1
    tc = nt.nodes.new("ShaderNodeTexCoord"); ln = nt.nodes.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; L(tc.outputs["Object"], ln.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 0.2; mr.inputs["From Max"].default_value = 1.0
    mr.inputs["To Min"].default_value = 0.55; mr.inputs["To Max"].default_value = 0.0
    L(ln.outputs["Value"], mr.inputs["Value"]); L(mr.outputs[0], b.inputs["Alpha"])
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    SHADOW_MAT[:] = [m]


def post_process():
    """Posproceso suave como el del juego: Glare sutil, viñeta marcada y ligero grado de color."""
    sc = bpy.context.scene
    if hasattr(sc, "compositing_node_group"):
        tree = bpy.data.node_groups.new("Post", "CompositorNodeTree"); sc.compositing_node_group = tree
        out = tree.nodes.new("NodeGroupOutput"); tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor"); oin = out.inputs[0]
    else:
        sc.use_nodes = True; tree = sc.node_tree
        for n in list(tree.nodes): tree.nodes.remove(n)
        out = tree.nodes.new("CompositorNodeComposite"); oin = out.inputs["Image"]
    L = tree.links.new
    rl = tree.nodes.new("CompositorNodeRLayers")
    gl = tree.nodes.new("CompositorNodeGlare")
    for at, v in [("glare_type", "FOG_GLOW"), ("mix", -0.7), ("threshold", 1.0)]:
        try: setattr(gl, at, v)
        except Exception: pass
    for nm, v in [("Type", "Fog Glow"), ("Threshold", 1.0), ("Strength", 0.35)]:
        if nm in gl.inputs:
            try: gl.inputs[nm].default_value = v
            except Exception: pass
    L(rl.outputs["Image"], gl.inputs["Image"])
    el = tree.nodes.new("CompositorNodeEllipseMask")
    if "Size" in el.inputs:
        el.inputs["Size"].default_value = (0.95, 0.82)
    else:
        el.width, el.height = 0.95, 0.82
    bl = tree.nodes.new("CompositorNodeBlur")
    if "Size" in bl.inputs:
        try: bl.inputs["Size"].default_value = (260, 260)
        except Exception: pass
    else:
        bl.size_x = bl.size_y = 260
    L(el.outputs[0], bl.inputs[0])
    mx = tree.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.blend_type = "MULTIPLY"; mx.inputs[0].default_value = 0.62
    L(gl.outputs[0], mx.inputs[6]); L(bl.outputs[0], mx.inputs[7]); L(mx.outputs[2], oin)


def fireflies(M, n=140):
    for k in range(n):
        a = R.uniform(0, math.tau); r = R.uniform(4, 30)
        sphere("firefly", R.uniform(0.06, 0.12), (math.cos(a) * r, math.sin(a) * r, R.uniform(0.6, 9)), M["firefly"], (1, 1, 1), 6)


def god_rays():
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    me = bpy.data.meshes.new("Atmos"); bm.to_mesh(me); bm.free()
    m = bpy.data.materials.new("Atmos"); m.use_nodes = True; nt = m.node_tree; nt.nodes.remove(nt.nodes["Principled BSDF"])
    v = nt.nodes.new("ShaderNodeVolumePrincipled"); v.inputs["Density"].default_value = 0.0035 / S
    v.inputs["Color"].default_value = (1.0, 0.9, 0.8, 1); v.inputs["Anisotropy"].default_value = 0.55
    nt.links.new(v.outputs[0], nt.nodes["Material Output"].inputs["Volume"]); me.materials.append(m)
    o = bpy.data.objects.new("Atmos", me); o.scale = (90, 90, 70); o.location = (0, 0, 0)
    link(o)


def hanging_roots(center, R0, depth, M, n=18, seed=3, mat="root_glow"):
    rnd = random.Random(seed)
    cx, cy, cz = center
    for k in range(n):
        a = rnd.uniform(0, math.tau); r = rnd.uniform(0.15, 0.55) * R0
        x, y = cx + math.cos(a) * r, cy + math.sin(a) * r
        z0 = cz - depth * rnd.uniform(0.35, 0.8)
        L_ = rnd.uniform(10, 26)
        pts = [(x, y, z0)]
        for s in range(1, 6):
            pts.append((x + math.cos(a) * s * rnd.uniform(0.4, 1.4), y + math.sin(a) * s * rnd.uniform(0.4, 1.4), z0 - L_ * s / 5))
        curve(f"root{k}", pts, rnd.uniform(0.18, 0.4), M[mat if rnd.random() < 0.6 else "bark"], (1.0, 0.1))


def network_root(p0, p1, M, sag=14, r=0.35, mat="root_glow"):
    mid = [(p0[i] + p1[i]) / 2 for i in range(3)]
    pts = [p0, (p0[0] * 0.75 + p1[0] * 0.25, p0[1] * 0.75 + p1[1] * 0.25, (p0[2] * 0.75 + p1[2] * 0.25) - sag * 0.7), (mid[0], mid[1], mid[2] - sag),
           (p0[0] * 0.25 + p1[0] * 0.75, p0[1] * 0.25 + p1[1] * 0.75, (p0[2] * 0.25 + p1[2] * 0.75) - sag * 0.7), p1]
    curve("net_root", pts, r, M[mat], (1.0, 0.8))


# ───────────────────────── edificios ─────────────────────────
def forge(x, y, rot, M, level=1):
    box("forge_base", (6.5, 5, 0.6), (x, y, 0.1), M["stone"], (0, 0, rot))
    box("forge_walls", (5.5, 4.2, 3.2), (x, y + 0.4, 0.7), M["wood_dark"], (0, 0, rot))
    gable("forge_roof", 5.5, 4.2, 2.4, (x, y + 0.4, 3.9), M["slate"], 0.6, rot + 90)
    box("forge_chimney", (1.4, 1.4, 6.5), (x + 2.2, y + 1.6, 0.6), M["stone"], (0, 0, rot))
    box("forge_hearth", (2.2, 1.0, 1.2), (x - 1.2, y - 2.0, 0.7), M["stone"], (0, 0, rot))
    box("forge_fire", (1.6, 0.6, 0.5), (x - 1.2, y - 2.3, 1.2), M["forge"], (0, 0, rot), bev=0.02)
    box("anvil_base", (0.5, 0.4, 0.8), (x + 0.8, y - 2.8, 0.7), M["iron"]); box("anvil_top", (1.1, 0.45, 0.3), (x + 0.8, y - 2.8, 1.5), M["iron"])
    for k in range(2):
        box(f"forge_win{k}", (0.9, 0.1, 0.9), (x - 1.4 + k * 2.8, y - 1.73, 2.0), M["window"], (0, 0, rot), bev=0.01)
    plight((x - 1.2, y - 3.2, 2.0), (1, 0.45, 0.12), 900)
    if level >= 3:
        box("forge_hall", (4, 3.5, 4.5), (x - 4.5, y + 0.5, 0.6), M["stone"], (0, 0, rot))
        gable("forge_hall_roof", 4, 3.5, 2.2, (x - 4.5, y + 0.5, 5.1), M["slate"], 0.5, rot)


def greenhouse(x, y, M, elven=False):
    box("gh_base", (7, 5, 0.7), (x, y, 0.1), M["stone"])
    dome = sphere("gh_glass", 1.0, (x, y, 0.8), M["glass"], (3.4, 2.4, 3.2), 32, half=True)
    ribs = sphere("gh_ribs", 1.0, (x, y, 0.8), M["white_wood" if not elven else "bark"], (3.45, 2.45, 3.25), 12, half=True)
    w = ribs.modifiers.new("Wire", "WIREFRAME"); w.thickness = 0.06; w.use_replace = True
    for k in range(9):
        px, py = x + R.uniform(-2.3, 2.3), y + R.uniform(-1.4, 1.4)
        cyl("gh_stem", 0.08, R.uniform(0.8, 1.6), (px, py, 0.8), M["crop"], 6)
        sphere("gh_bloom", R.uniform(0.25, 0.45), (px, py, 0.8 + R.uniform(0.9, 1.7)), M["plant_glow" if k % 2 else "plant_teal"], (1, 1, 0.8), 12)
    plight((x, y, 2.2), (0.8, 0.5, 1.0) if not elven else (0.5, 1.0, 0.7), 500, 0.8)
    if elven:  # troncos vivos abrazando el invernadero + semillas doradas
        for k in range(5):
            a = k / 5 * math.tau
            pts = [(x + math.cos(a) * 3.6, y + math.sin(a) * 2.6, 0.5), (x + math.cos(a + 0.3) * 3.7, y + math.sin(a + 0.3) * 2.7, 2.2),
                   (x + math.cos(a + 0.7) * 2.6, y + math.sin(a + 0.7) * 1.9, 3.6), (x + math.cos(a + 1.1) * 1.0, y + math.sin(a + 1.1) * 0.7, 4.2)]
            curve(f"gh_trunk{k}", pts, 0.28, M["bark"], (1.0, 0.4))
        for k in range(8):
            sphere("gh_seed", 0.18, (x + R.uniform(-3, 3), y + R.uniform(-2, 2), R.uniform(3.6, 5.2)), M["gold_glow"], (1, 1, 1), 10)


def alchemy(x, y, M):
    z, tilt = 0.1, 0
    for k, (r, h) in enumerate([(1.9, 2.6), (1.65, 2.3), (1.45, 2.1)]):
        cyl(f"alch_t{k}", r, h, (x + tilt, y, z), M["stone"] if k == 0 else M["wood"], 10, r * 0.92, (0, 3 * (k % 2 * 2 - 1), 0), sm=False, bev=0.05)
        z += h; tilt += 0.25 * (1 if k % 2 else -1)
    cyl("alch_roof", 1.9, 2.8, (x + tilt, y, z), M["roof"], 10, 0.05, (0, -5, 0), sm=False)
    sphere("cauldron", 1.0, (x + 2.6, y - 1.2, 0.9), M["iron"], (1.1, 1.1, 0.8), 20)
    cyl("brew", 0.95, 0.05, (x + 2.6, y - 1.2, 1.55), M["potion_g"], 20)
    for k, m in enumerate(("potion_p", "potion_b", "potion_g", "potion_p")):
        sphere(f"bottle{k}", 0.25, (x - 1.8 + k * 0.5, y - 2.0, 0.4), M[m], (1, 1, 1.3), 10)
    curve("alch_pipe", [(x + 1.2, y - 0.4, 3.5), (x + 2.4, y - 0.8, 3.2), (x + 2.6, y - 1.2, 2.0)], 0.12, M["copper"], (1, 1))
    for k in range(4):
        sphere("smoke", 0.5 + k * 0.25, (x + 2.6 + k * 0.3, y - 1.2, 2.2 + k * 0.9), M["smoke"], (1, 1, 0.8), 12)
    plight((x + 2.6, y - 1.2, 2.2), (0.3, 1.0, 0.5), 300)


def observatory(x, y, M):
    cyl("obs_base", 2.4, 1.0, (x, y, 0.1), M["stone"], 8, sm=False)
    cyl("obs_tower", 1.8, 7.0, (x, y, 1.0), M["stone"], 8, 1.5, sm=False)
    sphere("obs_dome", 1.0, (x, y, 8.0), M["brass"], (1.7, 1.7, 1.4), 24, half=True)
    tel = cyl("telescope", 0.35, 4.2, (x + 0.4, y - 0.5, 8.8), M["brass"], 16, 0.22, (55, 0, 30))
    for k in range(3):  # raíces doradas en espiral
        pts = [(x + math.cos(t * 0.9 + k * 2.1) * (2.3 - t * 0.08), y + math.sin(t * 0.9 + k * 2.1) * (2.3 - t * 0.08), 0.2 + t * 0.85) for t in range(10)]
        curve(f"obs_root{k}", pts, 0.22, M["root_glow"], (1.0, 0.4))
    plight((x, y - 2.5, 6), (1, 0.8, 0.4), 250)


def portal(x, y, rot, M):
    rm = M["root_red"] if ST == "destroy" else M["bark"]
    for k in range(6):  # arco de raíces entrelazadas
        off = (k - 2.5) * 0.25
        pts = []
        for s in range(13):
            t = s / 12
            a = math.pi * t
            pts.append((x + math.cos(a) * (3.4 + 0.25 * math.sin(t * 9 + k)) + off * math.sin(a), y + 0.3 * math.sin(t * 7 + k * 1.3) + off * 0.3,
                        0.2 + math.sin(a) * (6.2 + 0.25 * math.cos(t * 8 + k))))
        curve(f"portal_root{k}", pts, 0.32, rm if k % 2 else (M["root_glow"] if ST != "destroy" else M["obsidian"]), (1.3, 1.3))
    bm = bmesh.new(); bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=1.0)
    me = bpy.data.meshes.new("vortex"); bm.to_mesh(me); bm.free()
    vo = bpy.data.objects.new("vortex", me); vo.location = (x, y, 0.2 + 3.1); vo.scale = (3.0, 1, 3.0); vo.rotation_euler = (math.radians(90), 0, math.radians(rot))
    link(vo, M["vortex"])
    for k in range(10):
        a = k / 10 * math.pi
        box(f"rune{k}", (0.35, 0.15, 0.35), (x + math.cos(a) * 3.0, y - 0.1, 0.2 + math.sin(a) * 5.6), M["crimson" if ST == "destroy" else "gold_glow"], bev=0.02)
    box("portal_dais", (8.5, 3.5, 0.4), (x, y, 0.0), M["stone"])
    plight((x, y - 2.5, 3.2), (1.0, 0.15, 0.1) if ST == "destroy" else (0.8, 0.5, 1.0), 1500, 1.0)


def market(x, y, M):
    box("mk_floor", (7, 5, 0.4), (x, y, 0.1), M["wood"])
    for px in (-3.2, 3.2):
        for py in (-2.2, 2.2):
            cyl("mk_post", 0.18, 3.6, (x + px, y + py, 0.5), M["wood_dark"], 8)
    for k, m in enumerate(("awning1", "awning2", "awning3")):
        a = box(f"mk_awning{k}", (2.4, 5.2, 0.12), (x - 2.4 + k * 2.4, y, 4.1), M[m], (0, 12 if k != 1 else -12, 0), bev=0.02)
    for k in range(7):
        box("crate", (R.uniform(0.7, 1.1),) * 3, (x + R.uniform(-2.8, 2.8), y + R.uniform(-1.8, 1.8), 0.5), M["wood"], (0, 0, R.uniform(0, 40)))
    for k, m in enumerate(("pumpkin", "potion_b", "crop", "potion_p")):
        sphere("goods", 0.3, (x - 1.5 + k * 1.0, y - 2.3, 1.5), M[m], (1, 1, 0.8), 10)
    cyl("scale_pole", 0.07, 1.6, (x + 2.2, y - 2.3, 1.0), M["brass"], 8)
    box("ledger", (1.0, 0.1, 1.3), (x, y - 2.6, 5.2), M["gold_glow"], (10, 0, 0), bev=0.02)


def cottage(x, y, rot, M, roof="roof"):
    box("ct_base", (5, 4.2, 1.0), (x, y, 0.1), M["stone"], (0, 0, rot))
    box("ct_walls", (4.6, 3.8, 2.6), (x, y, 1.1), M["wood"], (0, 0, rot))
    gable("ct_roof", 4.6, 3.8, 2.3, (x, y, 3.7), M[roof], 0.5, rot + 90)
    box("ct_door", (1.0, 0.15, 1.8), (x, y - 1.95, 1.1), M["wood_dark"], (0, 0, rot), bev=0.02)
    box("ct_win", (0.9, 0.12, 0.8), (x + 1.4, y - 1.92, 1.9), M["window"], (0, 0, rot), bev=0.01)
    box("ct_chim", (0.7, 0.7, 2.2), (x - 1.3, y + 0.8, 3.6), M["stone"], (0, 0, rot))


def tree(x, y, M, h=5.0, mat="leaves"):
    cyl("trunk", 0.35, h * 0.6, (x, y, 0.1), M["bark"], 8, 0.25)
    for k in range(4):
        sphere("crown", R.uniform(1.3, 2.0) * h / 5, (x + R.uniform(-0.8, 0.8), y + R.uniform(-0.8, 0.8), h * 0.6 + R.uniform(0.2, 1.6)), M[mat], (1, 1, 0.85), 14)


def fence_line(p0, p1, M, posts=8):
    for k in range(posts):
        t = k / (posts - 1)
        x, y = p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t
        box("post", (0.22, 0.22, 1.2), (x, y, 0.1), M["wood"], bev=0.03)
    ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
    ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    for z in (0.55, 1.0):
        box("rail", (ln, 0.12, 0.12), ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, z), M["wood"], (0, 0, ang), bev=0.02)


def fields(M):
    # huerto: hileras de plantas
    for r in range(5):
        box("bed", (8, 0.9, 0.35), (-6, -8 + r * 1.4, 0.1), M["soil"], bev=0.1)
        for c in range(9):
            sphere("veg", 0.38, (-9.6 + c * 0.9, -8 + r * 1.4, 0.55), M["crop"], (1, 1, 0.7), 8)
    for c in range(4):
        sphere("pumpkin", R.uniform(0.45, 0.62), (-11.4, -7.6 + c * 1.5, 0.45), M["pumpkin"], (1, 1, 0.72), 12)
    # trigal
    box("wheat_bed", (7, 6, 0.3), (5.5, -9, 0.1), M["soil"], bev=0.1)
    for k in range(110):  # matas de trigo: tallos finos con espiga
        wx, wy = 5.5 + R.uniform(-3.1, 3.1), -9 + R.uniform(-2.6, 2.6)
        for j in range(3):
            h = R.uniform(1.0, 1.45); ox, oy = R.uniform(-0.15, 0.15), R.uniform(-0.15, 0.15)
            tilt = (R.uniform(-12, 12), R.uniform(-12, 12), 0)
            cyl("wheat", 0.025, h, (wx + ox, wy + oy, 0.35), M["wheat"], 4, sm=False, bev=0, rot=tilt)
            sphere("ear", 0.07, (wx + ox + math.radians(tilt[1]) * h, wy + oy - math.radians(tilt[0]) * h, 0.35 + h), M["wheat"], (1, 1, 3.2), 6)
    fence_line((-10.8, -9.2), (-1.2, -9.2), M, 9)
    fence_line((1.8, -12.4), (9.2, -12.4), M, 7)


def paths(M):
    for k in range(26):
        t = k / 25
        x = -2 + math.sin(t * 5) * 1.2 + (t - 0.5) * 3
        y = -13 + t * 22
        box("stone", (R.uniform(0.9, 1.3), R.uniform(0.8, 1.1), 0.18), (x, y, 0.15), M["path"], (0, 0, R.uniform(0, 40)), bev=0.06)
    for k in range(14):
        a = k / 14 * math.pi
        box("stone2", (1.0, 0.9, 0.18), (math.cos(a) * 6 - 2, 5 + math.sin(a) * 3, 0.15), M["path"], (0, 0, R.uniform(0, 40)), bev=0.06)


def lantern(x, y, M):
    cyl("lpost", 0.1, 2.6, (x, y, 0.1), M["iron"], 6)
    box("lamp", (0.45, 0.45, 0.55), (x, y, 2.7), M["lantern"], bev=0.03)
    plight((x, y, 2.9), (1, 0.75, 0.4), 120, 0.15)


def billboard(img_key, loc, height, M):
    im = image(img_key)
    if im is None:
        return
    w, h = im.size
    W = height * w / h
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in [(-W / 2, 0, 0), (W / 2, 0, 0), (W / 2, 0, height), (-W / 2, 0, height)]]
    f = bm.faces.new(vs); uv = bm.loops.layers.uv.new("UVMap")
    for l, c in zip(f.loops, [(0, 0), (1, 0), (1, 1), (0, 1)]):
        l[uv].uv = c
    me = bpy.data.meshes.new("bb"); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new("bb_" + img_key, me); o.location = loc
    link(o, F.sprite_mat(img_key))
    return o


# ───────────────────────── vacío cósmico ─────────────────────────
def void_world():
    w = bpy.data.worlds.new("Void"); bpy.context.scene.world = w; w.use_nodes = True
    nt = w.node_tree; L = nt.links.new
    bg = nt.nodes["Background"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 2.2; nz.inputs["Detail"].default_value = 6
    L(tc.outputs["Generated"], nz.inputs["Vector"])
    cr = nt.nodes.new("ShaderNodeValToRGB")
    red = ST == "destroy"
    cr.color_ramp.elements[0].color = (0.02, 0.0, 0.0, 1) if red else (0.01, 0.006, 0.03, 1)
    cr.color_ramp.elements[1].color = (0.45, 0.04, 0.05, 1) if red else (0.3, 0.12, 0.55, 1)
    el = cr.color_ramp.elements.new(0.72); el.color = (0.6, 0.12, 0.08, 1) if red else (0.08, 0.32, 0.5, 1)
    cr.color_ramp.elements[0].position = 0.35
    L(nz.outputs["Fac"], cr.inputs[0])
    vo = nt.nodes.new("ShaderNodeTexVoronoi"); vo.inputs["Scale"].default_value = 160
    L(tc.outputs["Generated"], vo.inputs["Vector"])
    st = nt.nodes.new("ShaderNodeMapRange"); st.inputs["From Min"].default_value = 0.055; st.inputs["From Max"].default_value = 0.0
    L(vo.outputs["Distance"], st.inputs["Value"])
    add = nt.nodes.new("ShaderNodeMix"); add.data_type = "RGBA"; add.blend_type = "ADD"
    L(st.outputs[0], add.inputs[0]); L(cr.outputs[0], add.inputs[6]); add.inputs[7].default_value = (1, 0.95, 0.9, 1)
    L(add.outputs[2], bg.inputs[0]); bg.inputs[1].default_value = 1.0


def fragments(M):
    """Pedazos de otros mundos a la deriva (desierto, hielo, lava, bosque)."""
    kinds = [("sand_frag", "sand", (1, 0.85, 0.6)), ("ice_frag", "snow", (0.8, 0.9, 1)), ("lava_frag", "dark_stone", (0.6, 0.5, 0.5)), ("forest_frag", "meadow", (0.7, 0.9, 0.6))]
    for k in range(18):
        kind = kinds[k % 4]
        top = F.detail_mat(kind[0] + str(k), kind[1], "box", repeat=0.3, grime=0, edge=0.3, ao=0.6, tint=kind[2])
        a = R.uniform(0, math.tau); d = R.uniform(40, 110)
        o = F.rock("frag", (R.uniform(2, 5), R.uniform(2, 5), R.uniform(2.5, 5)), top, seed=50 + k, detail=1)
        o.data.materials.append(M["rock"])
        for poly in o.data.polygons:  # cara superior del bioma, resto roca
            poly.material_index = 0 if poly.normal.z > 0.45 else 1
        o.location = (math.cos(a) * d, math.sin(a) * d + 20, R.uniform(-30, 25))
        o.rotation_euler = (math.radians(R.uniform(-15, 15)), math.radians(R.uniform(-15, 15)), R.uniform(0, 6))
        link(o)


# ───────────────────────── montaje ─────────────────────────
def smoke_column(x, y, z, M, n=6):
    for k in range(n):
        sphere("smoke", 0.45 + k * 0.22, (x + k * 0.35 + R.uniform(-0.2, 0.2), y + k * 0.15, z + k * 0.85), M["mist"], (1, 1, 0.85), 12)


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    F.prepare_facades()
    M = mats()
    R0, depth = 22.0, 20.0
    FOOTPRINTS[:] = [(-11, 4, 5.8), (9, 2, 5.0), (13, 11, 4.0), (-3, 13, 3.6), (3, 16.5, 5.2), (15, -3, 4.8), (-14, 12, 3.8), (-17, -3, 3.8),
                     (-6, -5.6, 5.8), (5.5, -9, 4.8), (-13, -12, 3.6), (13.5, -10, 3.4), (1.5, 2.5, 4.2)]
    isl, edge = island("acre", R0, depth, M, (0, 0, 0), seed=4, footprints=FOOTPRINTS)
    src = scatter_assets(M)
    hi = A["res"][0] >= 1280
    # capas de vegetación con densidades propias (hierba densa, flores salpicadas, pocas piedras y arbustos)
    gn_scatter(isl, src["grass"], 24.0 if hi else 15.0, M["grass"], (0.35, 0.95), seed=3, name="Hierba")
    gn_scatter(isl, src["flowers"], 1.6, M["grass"], (0.7, 1.3), seed=8, name="Flores")
    gn_scatter(isl, src["ferns"], 0.5, M["grass"], (0.6, 1.2), seed=13, name="Helechos")
    gn_scatter(isl, src["pebbles"], 0.35, M["grass"], (0.5, 1.4), seed=21, name="Piedras")
    gn_scatter(isl, src["bushes"], 0.08, M["grass"], (0.6, 1.1), seed=34, name="Arbustos")
    hanging_roots((0, 0, 0), R0, depth, M, 20, 5, "root_red" if ST == "destroy" else "root_glow")
    edge_life(edge, M)
    waterfall_edge(edge, M, -112)
    fields(M)
    path_ribbons(M)
    plaza(1.5, 2.5, 4.0, M)
    cyl("plaza_fountain", 1.3, 0.6, (1.5, 2.5, 0.1), M["stone"], 20); cyl("fountain_water", 1.1, 0.62, (1.5, 2.5, 0.1), M["water"], 20)
    cyl("fountain_core", 0.35, 1.6, (1.5, 2.5, 0.6), M["stone"], 10)
    build_plot(-13, -12, 5.0, 4.0, M, "empty")      # solar libre: el jugador decide qué construir
    build_plot(13.5, -10, 4.4, 4.0, M, "frame")     # edificio en obras con andamio
    forge(-11, 4, 0, M, level=3 if ST == "conquer" else 1)
    smoke_column(-11 + 2.2, 4 + 1.6, 7.3, M)
    greenhouse(9, 2, M, elven=ST == "conquer")
    alchemy(13, 11, M)
    observatory(-3, 13, M)
    portal(3, 16.5, 0, M)
    market(15, -3, M)
    cottage(-14, 12, 15, M); cottage(-17, -3, -10, M, "slate")
    smoke_column(-15.2, 12.6, 6.0, M, 5)
    for x, y in [(-18, 7), (17, 9), (-8, -15), (11, -14), (19, 3), (-19, -9), (-7, 19), (16, 16)]:
        tree(x, y, M, R.uniform(4.5, 6.8), "leaves")
    for x, y in [(-3, -4), (4, 6), (-9, 8), (8, -5), (1, -13)]:
        lantern(x, y, M)
    # props de vida
    for x, y in [(-8, 1.2), (-8.6, 2.2), (12, -6.4), (17.5, -5.5)]:
        cyl("barrel", 0.5, 1.1, (x, y, 0.1), M["wood"], 14, 0.45)
    box("cart", (2.4, 1.4, 0.8), (18, 0.5, 0.7), M["wood"], (0, 0, 20)); cyl("wheel", 0.6, 0.15, (18.3, -0.4, 0.6), M["wood_dark"], 14, rot=(90, 0, 20))
    cyl("well", 1.1, 1.0, (-5, 7, 0.1), M["stone"], 16); cyl("well_water", 0.9, 1.02, (-5, 7, 0.1), M["water"], 16)
    box("well_roof_l", (0.2, 0.2, 2.4), (-6.1, 7, 0.1), M["wood"]); box("well_roof_r", (0.2, 0.2, 2.4), (-3.9, 7, 0.1), M["wood"])
    gable("well_roof", 2.4, 1.6, 0.9, (-5, 7, 2.5), M["roof"], 0.3, 90)
    for bx_, by_, br in [(-1.8, 5.2, -30), (4.8, 0.2, 60)]:
        box("bench", (2.0, 0.6, 0.45), (bx_, by_, 0.1), M["wood"], (0, 0, br))
    for x, y in [(-1, -6), (3.2, 6.8), (6.2, 1.2)]:
        cyl("planter", 0.45, 0.55, (x, y, 0.1), M["wood_dark"], 10); sphere("planter_fl", 0.5, (x, y, 0.75), M["leaves"], (1, 1, 0.7), 10)
    for k in range(3):
        box("crate", (0.8, 0.8, 0.8), (16.3 + k * 0.4, -6.5 + k * 0.9, 0.1 + (k == 2) * 0.8), M["wood"], (0, 0, k * 17), bev=0.03)
    if ST == "conquer":
        for x, y in [(-5, 20), (12, 17), (-17, 16), (20, -8)]:
            tree(x, y, M, 8.0, "leaves")  # madera primordial
        for k in range(3):
            box("banner", (0.1, 1.2, 3), (-6 + k * 6, -15, 3), M["gold_glow"], bev=0.02)
    if ST == "destroy":
        bx, by = -2, 8
        box("altar_base", (5, 5, 1.2), (bx, by, 0.1), M["obsidian"]); box("altar_top", (3.4, 3.4, 1.0), (bx, by, 1.3), M["obsidian"])
        for k in range(7):
            a = k / 7 * math.tau
            cyl("crystal", 0.5, R.uniform(2.5, 4.5), (bx + math.cos(a) * 1.6, by + math.sin(a) * 1.6, 2.0), M["crimson"], 5, 0.0,
                (math.degrees(math.cos(a)) * 0.3, math.degrees(math.sin(a)) * 0.3, 0), sm=False, bev=0)
        plight((bx, by, 4), (1, 0.05, 0.05), 1800, 1.0)
    box("raven_post", (0.4, 0.4, 2.2), (-6.5, -19.2, top_z(-6.5, -19.2) - 0.1), M["wood"], bev=0.04)
    if A.get("chars"):
        billboard("raven", (-6.5, -19.2, top_z(-6.5, -19.2) + 2.1), 1.8, M)
        billboard("player", (0.6, -12.3, 0.1), 2.4, M)
    if TIME in ("dusk", "night") or ST == "destroy":
        fireflies(M)
    god_rays()
    # la Red de las Raíces: Acres de otros jugadores
    others = [((-70, 55, 18), 9), ((75, 60, -8), 11), ((-60, -55, -22), 8), ((80, -40, 25), 7), ((5, 105, 30), 10)]
    for k, (c, r) in enumerate(others):
        o2, e2 = island(f"acre_other{k}", r, r * 0.9, M, c, seed=20 + k, top_mat="grass")
        cottage(c[0], c[1], R.uniform(0, 90), M)
        hanging_roots(c, r, r * 0.9, M, 6, 30 + k)
        network_root((0, 0, -depth * 0.85), (c[0], c[1], c[2] - r * 0.8), M, sag=26, r=0.28, mat="root_red" if ST == "destroy" and k % 2 else "root_glow")
    fragments(M)
    void_world()
    log("Acre construido (%s): %d objetos" % (ST, len(OBJS)))
    return depth


SHOTS = {"play": ((0, -1, 0), 40, -8, 34, 2.8, 40), "play_farm": ((-1, -9, 0), 42, -12, 30, 2.6, 40),
         "play_build": ((7, -9, 0), 40, 18, 28, 2.6, 40), "hero": ((0, 0, 0), 19, -28, 60, 3.2), "iso": ((0, 0, 2), 42, -35, 62, 5.6), "network": ((0, 20, -5), 20, -20, 240, 8.0)}


def camera_and_render(depth):
    sc = bpy.context.scene
    root = bpy.data.objects.new("Root", None); sc.collection.objects.link(root)
    for o in OBJS:
        if o.parent is None:
            o.parent = root
    root.scale = (S, S, S)
    bpy.context.view_layer.update()
    # luz principal cálida, contraluz violeta (o roja)
    TOD = {  # energía, color, inclinación, acimut del sol; fondo; multiplicador de luces cálidas; exposición
        "day": (4.5, (1.0, 0.86, 0.68), 52, -35, 1.0, 1.0, 0.15),
        "dawn": (2.6, (1.0, 0.62, 0.5), 76, 60, 0.7, 1.4, 0.25),
        "dusk": (3.0, (1.0, 0.5, 0.25), 78, -70, 0.6, 2.0, 0.2),
        "night": (0.5, (0.45, 0.58, 1.0), 40, 30, 0.35, 3.5, 0.35)}
    se, scol, stilt, saz, wmul, lmul, expo = TOD.get(TIME, TOD["day"])
    sun = bpy.data.lights.new("Sun", "SUN"); sun.energy = se; sun.color = scol; sun.angle = math.radians(3)
    so = bpy.data.objects.new("Sun", sun); sc.collection.objects.link(so); so.rotation_euler = (math.radians(stilt), 0, math.radians(saz))
    if sc.world:
        sc.world.node_tree.nodes["Background"].inputs[1].default_value *= wmul
    for ob in sc.objects:
        if ob.type == "LIGHT" and ob.data.type == "POINT":
            ob.data.energy *= lmul
    if TIME in ("night", "dusk"):
        for m in bpy.data.materials:
            if m.name in ("Window", "Lantern", "Forge") and m.use_nodes:
                b = m.node_tree.nodes.get("Principled BSDF")
                if b and "Emission Strength" in b.inputs:
                    b.inputs["Emission Strength"].default_value *= 1.8
    rim = bpy.data.lights.new("Rim", "SUN"); rim.energy = 2.2 * (0.5 if TIME == "night" else 1); rim.color = (1.0, 0.25, 0.2) if ST == "destroy" else (0.6, 0.4, 1.0)
    ro = bpy.data.objects.new("Rim", rim); sc.collection.objects.link(ro); ro.rotation_euler = (math.radians(70), 0, math.radians(160))
    sh = SHOTS.get(A["shot"], SHOTS["hero"])
    (tx, ty, tz), elev, az, width, fstop = sh[:5]
    lens = sh[5] if len(sh) > 5 else 50
    cd = bpy.data.cameras.new("Cam"); cd.lens = lens; cd.sensor_width = 36
    dist = (width * S / 2) / (18 / lens)
    e, a = math.radians(elev), math.radians(az)
    c = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(c)
    tgt = Vector((tx, ty, tz)) * S
    c.location = tgt + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
    f = bpy.data.objects.new("Focus", None); sc.collection.objects.link(f); f.location = tgt
    tr = c.constraints.new("TRACK_TO"); tr.target = f; tr.track_axis = "TRACK_NEGATIVE_Z"; tr.up_axis = "UP_Y"
    cd.clip_start = 0.01; cd.clip_end = 200
    cd.dof.use_dof = True; cd.dof.focus_object = f; cd.dof.aperture_fstop = fstop
    sc.camera = c
    for o in OBJS:
        if o.name.startswith("bb_"):
            k = o.constraints.new("LOCKED_TRACK"); k.target = c; k.track_axis = "TRACK_NEGATIVE_Y"; k.lock_axis = "LOCK_Z"
    F.CFG["res"], F.CFG["samples"], F.CFG["out"] = A["res"], A["samples"], A["out"]
    F.render_settings()
    sc.view_settings.exposure = expo
    post_process()
    for lk in ("AgX - Punchy", "Punchy"):
        try: sc.view_settings.look = lk; break
        except Exception: pass


def main():
    d = build()
    camera_and_render(d)
    if A["blend"]:
        bpy.ops.wm.save_as_mainfile(filepath=A["blend"], compress=True)
    if A["render"] and bpy.app.background:
        bpy.ops.render.render(write_still=True)
        log("Render → " + A["out"])


if __name__ == "__main__":
    main()
