"""
Aethermoor · continente JRPG en estilo cúbico 2D-HD
====================================================
Un mundo completo y coherente construido con cubos low poly + imágenes FLUX + shaders
que fingen detalle. Reutiliza los módulos de ../fortress (murallas, torres, torreón,
casas, cascada, estratos) como librería.

Geografía (de norte a sur):
  · Cordillera del Norte con el Abismo y la Fortaleza de Piedrahonda en su garganta
  · Noroeste helado: el Lago Escarcha entre pinos nevados y agujas de hielo
  · Cuevas de cristal al pie de las montañas
  · Bosque de Antaño con el Árbol del Mundo
  · Llanuras de Valdeoro: campos de trigo, aldea y molino, caminos
  · Este: Desierto de Ámbar con dunas escalonadas, mesetas rojas, oasis y pirámide escalonada
  · Oeste: el Castillo Real sobre la colina, junto a los acantilados y el faro
  · Sur y suroeste: el Mar de Plata con playas
  · Magia: islas flotantes con cascadas, cristales arcanos y nubes de cubos

Uso:
  blender -b -P build_world.py -- [--shot world|desert|frost|castle|fortress|isles|plains]
         [--res 1600x900] [--samples 48] [--pixel] [--out render.png]
"""
import math
import os
import random
import sys

import bpy
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "fortress"))
import build_fortress as F  # noqa: E402  (módulos, materiales y utilidades)

W = {"shot": "world", "res": (1600, 900), "samples": 48, "out": os.path.join(HERE, "render_world.png"), "render": True}
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
for i, a in enumerate(argv):
    if a == "--shot": W["shot"] = argv[i + 1]
    if a == "--res": W["res"] = tuple(int(v) for v in argv[i + 1].split("x"))
    if a == "--samples": W["samples"] = int(argv[i + 1])
    if a == "--out": W["out"] = argv[i + 1]
    if a == "--no-render": W["render"] = False

S = 0.004                      # escala de maqueta del continente (640 m → 2,56 unidades)
F.S = S
CELL = 4.0                     # tamaño del cubo de terreno (m)
X0, X1, Y0, Y1 = -320, 320, -240, 240
rnd = random.Random(2026)
PLACED = []

# imágenes: primero las del mundo, luego las de la fortaleza
_orig_image = F.image


def world_image(key):
    if key not in F.IMGS:
        p = os.path.join(HERE, "images", key + ".png")
        if os.path.exists(p):
            im = bpy.data.images.load(p, check_existing=True)
            if F.CFG["pixel"]:
                w, h = im.size
                k = 160 / max(w, h)
                im.scale(max(8, int(w * k)), max(8, int(h * k)))
            F.IMGS[key] = im
            return im
    return _orig_image(key)


F.image = world_image


def log(m):
    print("WORLD:", m, flush=True)


# ───────────────────────── geografía ─────────────────────────
def n2(x, y):
    """Ruido suave determinista en [-1, 1]."""
    return (math.sin(x * 0.021) + math.sin(y * 0.017 + 1.3) + 0.8 * math.sin((x + y) * 0.013 + 2.1)
            + 0.5 * math.sin(x * 0.047 - y * 0.039) + 0.35 * math.sin(x * 0.09 + y * 0.07)) / 3.65


GORGE_X = 20.0
CASTLE = (-205.0, -55.0)
VILLAGE = (55.0, -95.0)
OASIS = (205.0, 15.0)
PYRAMID = (250.0, -70.0)
LAKE = (-175.0, 140.0, 52.0)
WORLD_TREE = (-105.0, 25.0)
MESAS = [(170, 70, 34), (285, 55, 42), (190, -130, 28), (300, -10, 30)]
ROADS = [[CASTLE, (-150, -70), (-60, -85), VILLAGE], [VILLAGE, (40, -30), (GORGE_X + 6, 40), (GORGE_X + 6, 92)],
         [VILLAGE, (130, -60), (OASIS[0] - 20, OASIS[1] - 10)], [(-60, -85), (-95, -10), (WORLD_TREE[0], WORLD_TREE[1] - 12)]]


def river_x(y):  # río que baja del abismo hasta el mar
    return GORGE_X - 12 + 34 * math.sin((y - 95) * 0.018) - (95 - y) * 0.12


def dist_seg(px, py, a, b):
    ax, ay = a; bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy + 1e-9)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def on_road(x, y, w=3.2):
    return any(dist_seg(x, y, r[k], r[k + 1]) < w for r in ROADS for k in range(len(r) - 1))


def biome(x, y):
    coast = y + 168 + 34 * math.sin(x * 0.012) + 18 * math.sin(x * 0.031 + 1)
    west = x + 272 + 24 * math.sin(y * 0.02)
    if coast < 0 or west < 0:
        return "sea", min(coast, west)
    if coast < 12 or west < 12:
        return "beach", min(coast, west)
    if x < -80 and 55 < y < 205 + 10 * math.sin(x * 0.05):
        return "snow", 0
    if y > 95 + 18 * math.sin(x * 0.015):
        return "mount", 0
    if x > 128 + 24 * math.sin(y * 0.02):
        return "desert", 0
    if y > 55 and x < -60:
        return "snow", 0
    return "plains", 0


def q(h, step=2.0):
    return round(h / step) * step


def terrain(x, y):
    """Devuelve (altura, material_superior, material_lateral)."""
    b, d = biome(x, y)
    if b == "sea":
        return q(-3 - min(14, -d * 0.12)), "beach", "rock"
    if b == "beach":
        return 1.0, "beach", "beach"
    # río
    if 95 > y > -175 and abs(x - river_x(y)) < 5 + max(0, (40 - y) * 0.03):
        return -2.0, "beach", "rock"
    if on_road(x, y) and b in ("plains", "snow", "desert"):
        base = 2.0 if b != "desert" else 4.0
        return base, "dirt", "dirt_side"
    if b == "mount":
        h = 14 + (y - 95) * 0.55 + 16 * abs(n2(x * 1.7, y * 1.7))
        gw = 22 + (y - 95) * 0.12
        if abs(x - GORGE_X) < gw and y < 200:          # garganta del abismo
            return 6.0, "paving" if y < 170 else "grass", "rock"
        for cx, cy in ((-40, 104), (170, 108)):         # explanadas ante las cuevas
            if math.hypot(x - cx, y - cy) < 14:
                return 6.0, "grass", "rock"
        h = q(h, 4)
        top = "snow" if h > 62 else "rock" if h > 30 else "grass"
        return h, top, "rock"
    if b == "desert":
        h = 4 + 3 * math.sin(x * 0.06 + math.sin(y * 0.05) * 2) + 2 * n2(x, y)
        for mx, my, mh in MESAS:
            r = math.hypot(x - mx, y - my)
            if r < 26:
                h = max(h, mh - max(0, r - 10) * 2.2)
        if math.hypot(x - OASIS[0], y - OASIS[1]) < 13:
            return -2.0, "beach", "sand_side"
        if math.hypot(x - OASIS[0], y - OASIS[1]) < 20:
            return 2.0, "meadow", "sand_side"
        hq = q(h)
        return hq, "red_rock" if hq > 14 else "sand", "red_rock" if hq > 10 else "sand_side"
    if b == "snow":
        lx, ly, lr = LAKE
        r = math.hypot(x - lx, y - ly)
        if r < lr:
            return -2.0, "snow", "snow_side"
        h = 4 + 3 * n2(x * 1.3, y * 1.3) + max(0, (y - 60) * 0.12)
        return q(h), "snow", "snow_side"
    # llanuras
    h = 3 + 2.4 * n2(x, y)
    cr = math.hypot(x - CASTLE[0], y - CASTLE[1])
    h += max(0.0, 18 - cr * 0.32)                      # colina del castillo
    h = q(h)
    top = "meadow"
    if 15 < x < 120 and -150 < y < -60 and (int((x + 400) / 16) + int((y + 400) / 12)) % 3 != 0:
        top = "crop"                                    # campos de cultivo
    if -170 < x < -40 and -10 < y < 75:
        top = "forest"
    return h, top, "dirt_side"


# ───────────────────────── terreno de cubos ─────────────────────────
def build_terrain(M):
    keys = ["meadow", "forest", "crop", "beach", "sand", "red_rock", "snow", "rock", "grass", "dirt", "paving",
            "dirt_side", "sand_side", "snow_side"]
    idx = {k: i for i, k in enumerate(keys)}
    nx, ny = int((X1 - X0) / CELL), int((Y1 - Y0) / CELL)
    base = -20.0
    HEIGHTS.clear()
    verts, faces, mats = [], [], []
    hc = CELL / 2
    for i in range(nx):
        for j in range(ny):
            x, y = X0 + (i + 0.5) * CELL, Y0 + (j + 0.5) * CELL
            h, top, side = terrain(x, y)
            HEIGHTS[(i, j)] = h
            v = len(verts)
            verts += [(x - hc, y - hc, base), (x + hc, y - hc, base), (x + hc, y + hc, base), (x - hc, y + hc, base),
                      (x - hc, y - hc, h), (x + hc, y - hc, h), (x + hc, y + hc, h), (x - hc, y + hc, h)]
            faces += [(v + 4, v + 5, v + 6, v + 7), (v, v + 1, v + 5, v + 4), (v + 1, v + 2, v + 6, v + 5), (v + 2, v + 3, v + 7, v + 6), (v + 3, v, v + 4, v + 7)]
            mats += [idx[top], idx[side], idx[side], idx[side], idx[side]]
    me = bpy.data.meshes.new("Continent")
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set("material_index", mats)
    me.update()
    for k in keys:
        me.materials.append(M[k])
    o = bpy.data.objects.new("Continent", me)
    link(o)
    # mar y ríos: una lámina de agua global; el lago helado lleva hielo encima
    sea = F.facade_box("Sea", (X1 - X0 + 400, Y1 - Y0 + 400, 0.2), [M["sea"]]); sea.modifiers.clear()
    sea.location = (0, 0, -0.6); link(sea)
    lx, ly, lr = LAKE
    bm = bmesh.new(); bmesh.ops.create_circle(bm, cap_ends=True, segments=48, radius=lr + 2)
    me = bpy.data.meshes.new("Ice"); bm.to_mesh(me); bm.free(); me.materials.append(M["ice"])
    ice = bpy.data.objects.new("Ice", me); ice.location = (lx, ly, -0.2); link(ice)
    log("Terreno: %d columnas" % (nx * ny))


HEIGHTS = {}


def ground(x, y):
    i, j = int((x - X0) / CELL), int((y - Y0) / CELL)
    return HEIGHTS.get((i, j), 0.0)


def link(o):
    bpy.context.scene.collection.objects.link(o)
    PLACED.append(o)
    return o


def place(mod, loc, rot=0.0, scale=1.0):
    e = bpy.data.objects.new(f"{mod}_{len(PLACED)}", None)
    e.instance_type = "COLLECTION"
    e.instance_collection = F.MODULES[mod]
    e.location = loc
    e.rotation_euler.z = math.radians(rot)
    e.scale = (scale,) * 3 if isinstance(scale, (int, float)) else scale
    return link(e)


def coll(name, objs):
    c = bpy.data.collections.new("MOD_" + name)
    for o in objs:
        c.objects.link(o)
    F.MODULES[name] = c
    return c


def cube(name, size, loc, mat, rot=0.0, bevel=0.15):
    o = F.facade_box(name, size, [mat])
    o.location = loc
    o.rotation_euler.z = math.radians(rot)
    if bevel and "Bevel" in o.modifiers:
        o.modifiers["Bevel"].width = bevel
    elif "Bevel" in o.modifiers:
        o.modifiers.remove(o.modifiers["Bevel"])
    return o


# ───────────────────────── módulos del mundo ─────────────────────────
def build_modules(M):
    # árbol cúbico (3 variantes de copa)
    for v, (lm, tall) in enumerate([(M["leaves"], 1.0), (M["leaves_dark"], 1.3), (M["leaves_autumn"], 0.9)]):
        r = random.Random(v)
        parts = [cube(f"tree{v}_trunk", (1.2, 1.2, 5 * tall), (0, 0, 0), M["bark"], bevel=0.1)]
        for k in range(4):
            s = r.uniform(3.2, 4.6)
            parts.append(cube(f"tree{v}_leaf{k}", (s, s, s * 0.85), (r.uniform(-1.2, 1.2), r.uniform(-1.2, 1.2), 4.2 * tall + k * 1.4 - (k > 1) * 1.6), lm, r.uniform(0, 40), 0.35))
        coll(f"tree{v}", parts)
    # pino cúbico nevado
    parts = [cube("pine_trunk", (0.9, 0.9, 3.0), (0, 0, 0), M["bark"], bevel=0.08)]
    for k in range(4):
        s = 4.4 - k * 1.0
        parts.append(cube(f"pine_l{k}", (s, s, 1.5), (0, 0, 2.2 + k * 1.5), M["pine_snow"] if k % 2 else M["leaves_dark"], k * 22, 0.2))
    coll("pine", parts)
    # palmera
    parts = [cube(f"palm_t{k}", (0.8, 0.8, 1.6), (k * 0.25, 0, k * 1.55), M["bark"], k * 9, 0.1) for k in range(6)]
    for k in range(5):
        a = k / 5 * math.tau
        p = cube(f"palm_leaf{k}", (4.5, 1.1, 0.35), (math.cos(a) * 2.0 + 1.4, math.sin(a) * 2.0, 9.2), M["leaves"], math.degrees(a), 0.08)
        p.rotation_euler.x = math.radians(18)
        parts.append(p)
    coll("palm", parts)
    # cristal arcano
    for name, mat in (("crystal_teal", M["crystal_teal"]), ("crystal_violet", M["crystal_violet"])):
        parts = []
        for k in range(4):
            c = cube(f"{name}{k}", (1.0, 1.0, 3.5 - k * 0.6), ((k % 2) * 1.2 - 0.6, (k // 2) * 1.2 - 0.6, 0), mat, k * 25, 0.1)
            c.rotation_euler.x = math.radians(rnd.uniform(-14, 14)); c.rotation_euler.y = math.radians(rnd.uniform(-14, 14))
            parts.append(c)
        coll(name, parts)
    # aguja de hielo
    coll("ice_spike", [F.pyramid("ice_spike", 2.6, 12, M["ice_glow"], 0.0)])
    # molino
    parts = [cube("mill_body", (6, 6, 9), (0, 0, 0), M["plaster"]), ]
    parts.append(F.pyramid("mill_roof", 6, 4.5, M["roof_red"])); parts[-1].location.z = 9
    for k in range(4):
        bl = cube(f"mill_blade{k}", (1.2, 0.3, 7.5), (0, -3.4, 7.5), M["wood"], 0, 0.05)
        bl.rotation_euler = (0, math.radians(k * 90 + 20), 0)
        bl.location = (math.sin(math.radians(k * 90 + 20)) * 3.75, -3.4, 7.5 + math.cos(math.radians(k * 90 + 20)) * 3.75)
        parts.append(bl)
    coll("windmill", parts)
    # pirámide escalonada
    parts = []
    for k in range(9):
        s = 44 - k * 4.6
        parts.append(cube(f"pyr{k}", (s, s, 3.4), (0, 0, k * 3.4), M["sandstone"], 0, 0.3))
    parts.append(cube("pyr_temple", (6, 6, 5), (0, 0, 9 * 3.4), M["sandstone"], 0, 0.2))
    parts.append(cube("pyr_gem", (2, 2, 2), (0, 0, 9 * 3.4 + 6), M["crystal_violet"], 45, 0.1))
    for k in range(9):
        parts.append(cube(f"pyr_stair{k}", (6, 3, 3.4), (0, -22 + k * 2.3 - 1.5, k * 3.4), M["sandstone"], 0, 0.15))
    coll("pyramid", parts)
    # boca de cueva con cristales
    parts = [cube("cave_frame_l", (5, 6, 16), (-8, 0, 0), M["rock_dark"], 0, 0.6), cube("cave_frame_r", (5, 6, 16), (8, 0, 0), M["rock_dark"], 0, 0.6),
             cube("cave_lintel", (21, 7, 6), (0, 0, 14), M["rock_dark"], 0, 0.8), cube("cave_void", (11.5, 4, 14), (0, 1.5, 0), M["void"], 0, 0)]
    for k in range(5):
        parts.append(cube(f"cave_cr{k}", (1.1, 1.1, rnd.uniform(2, 4)), (rnd.uniform(-5, 5), -1.5 + rnd.uniform(-1, 1), 0), M["crystal_teal"], rnd.uniform(0, 45), 0.1))
    coll("cave", parts)
    # isla flotante (cono escalonado invertido)
    parts = []
    for k in range(6):
        s = 30 - k * 4.6
        parts.append(cube(f"isle{k}", (s * 1.1, s, 4), (rnd.uniform(-1, 1), rnd.uniform(-1, 1), -k * 4), M["rock"] if k else M["isle_top"], rnd.uniform(-8, 8), 0.4))
    parts.append(cube("isle_falls", (4, 1.2, 30), (6, -15.5, -28), M["falls"], 0, 0))
    coll("isle", parts)
    # nube de cubos
    parts = []
    for k in range(9):
        s = rnd.uniform(6, 13)
        parts.append(cube(f"cloud{k}", (s * 1.4, s, s * 0.6), (rnd.uniform(-14, 14), rnd.uniform(-8, 8), rnd.uniform(0, 4)), M["cloud"], 0, 1.0))
    coll("cloud", parts)
    # faro
    parts = [F.facade_box("lighthouse", (5, 5, 22), [M["plaster"]]), F.pyramid("lighthouse_roof", 5, 4, M["roof_red"])]
    parts[1].location.z = 24
    parts.append(cube("lighthouse_lamp", (3.5, 3.5, 2.2), (0, 0, 22), M["lamp"], 0, 0.1))
    coll("lighthouse", parts)
    # barco
    parts = [cube("boat_hull", (10, 3.6, 2.2), (0, 0, 0), M["wood"], 0, 0.5), cube("boat_mast", (0.4, 0.4, 9), (0, 0, 2), M["wood"], 0, 0),
             cube("boat_sail", (0.2, 5.5, 5.5), (0.4, 0, 4.5), M["plaster"], 0, 0.05)]
    coll("boat", parts)
    # columnas en ruinas
    parts = [cube(f"ruin{k}", (2, 2, rnd.uniform(3, 9)), (math.cos(k) * 7, math.sin(k) * 7, 0), M["sandstone"], k * 15, 0.25) for k in range(7)]
    coll("ruins", parts)
    # Árbol del Mundo
    parts = []
    for k in range(10):
        s = 9 - k * 0.45
        parts.append(cube(f"wt_trunk{k}", (s, s, 5.5), (math.sin(k * 0.7) * 1.2, math.cos(k * 0.5), k * 5.3), M["bark"], k * 11, 0.5))
    for k in range(4):
        a = k / 4 * math.tau + 0.4
        parts.append(cube(f"wt_root{k}", (12, 3.5, 3), (math.cos(a) * 6, math.sin(a) * 6, 0), M["bark"], math.degrees(a), 0.4))
    r = random.Random(77)
    for k in range(26):
        s = r.uniform(9, 17)
        parts.append(cube(f"wt_leaf{k}", (s, s, s * 0.7), (r.uniform(-20, 20), r.uniform(-20, 20), 46 + r.uniform(-6, 16)), M["leaves_magic"] if k % 4 == 0 else M["leaves"], r.uniform(0, 45), 1.0))
    for k in range(40):
        parts.append(cube(f"wt_spark{k}", (0.6, 0.6, 0.6), (r.uniform(-24, 24), r.uniform(-24, 24), r.uniform(20, 66)), M["spark"], r.uniform(0, 45), 0))
    coll("world_tree", parts)


# ───────────────────────── poblar el mundo ─────────────────────────
def populate(M):
    gx = GORGE_X
    # FORTALEZA en la garganta del abismo
    pts = [(gx - 30, 98), (gx - 20, 95), (gx - 10, 93), (gx, 92), (gx + 10, 93), (gx + 20, 95), (gx + 30, 98)]
    for k in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[k], pts[k + 1]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        place("gatehouse" if k == 3 else "wall_segment", ((x0 + x1) / 2, (y0 + y1) / 2, 6), ang, (1.02, 1, 1))
    for k in (0, 2, 4, 6):
        place("wall_tower", (pts[k][0], pts[k][1], 6))
    place("keep", (gx + 4, 140, 6))
    for x, y, r in [(gx - 12, 108, 0), (gx - 2, 112, 6), (gx + 14, 110, -6), (gx - 10, 122, 3), (gx + 16, 124, -4)]:
        place("house", (x, y, 6), r)
    place("waterfall", (gx - 6, 176, 6), 0, 0.9)
    # CASTILLO REAL sobre la colina junto al mar
    cx, cy = CASTLE
    cz = ground(cx, cy)
    ring = [(cx + math.cos(a) * 30, cy + math.sin(a) * 30) for a in [k * math.tau / 6 + 0.3 for k in range(6)]]
    for k in range(6):
        (x0, y0), (x1, y1) = ring[k], ring[(k + 1) % 6]
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        place("castle_gate" if k == 4 else "castle_wall", ((x0 + x1) / 2, (y0 + y1) / 2, cz), ang, (2.9, 1, 1) if k != 4 else 1.0)
        place("castle_tower", (x0, y0, cz), rnd.uniform(0, 20), 1.15)
    place("castle_keep", (cx + 2, cy + 6, cz), 0, 1.1)
    for k in range(5):
        a = k * 1.2 + 0.5
        place("castle_house", (cx + math.cos(a) * 16, cy + math.sin(a) * 16, cz), math.degrees(a))
    place("lighthouse", (-262, -120, ground(-262, -120)))
    for x, y, r in [(-282, -80, 30), (-290, -140, -20), (-240, -190, 70), (60, -205, 10)]:
        place("boat", (x, y, -0.7), r)
    # ALDEA de Valdeoro con molino
    vx, vy = VILLAGE
    for k in range(9):
        a = k / 9 * math.tau
        x, y = vx + math.cos(a) * 18, vy + math.sin(a) * 14
        place("castle_house" if k % 3 == 0 else "house", (x, y, ground(x, y)), math.degrees(a) + 90)
    for x, y in ((vx + 36, vy - 22), (vx - 30, vy + 26)):
        place("windmill", (x, y, ground(x, y)), rnd.uniform(-20, 20))
    # BOSQUE DE ANTAÑO y Árbol del Mundo
    wx, wy = WORLD_TREE
    place("world_tree", (wx, wy, ground(wx, wy)))
    for k in range(260):
        x, y = rnd.uniform(-168, -42), rnd.uniform(-8, 72)
        if math.hypot(x - wx, y - wy) < 26 or on_road(x, y, 6):
            continue
        place(f"tree{rnd.randint(0, 2)}", (x, y, ground(x, y)), rnd.uniform(0, 90), rnd.uniform(0.8, 1.4))
    for k in range(70):  # árboles sueltos en llanuras
        x, y = rnd.uniform(-240, 120), rnd.uniform(-160, 90)
        b, _ = biome(x, y)
        if b == "plains" and not on_road(x, y, 6) and math.hypot(x - CASTLE[0], y - CASTLE[1]) > 40:
            place(f"tree{rnd.randint(0, 2)}", (x, y, ground(x, y)), rnd.uniform(0, 90), rnd.uniform(0.8, 1.2))
    # NOROESTE HELADO
    lx, ly, lr = LAKE
    for k in range(120):
        a, r = rnd.uniform(0, math.tau), rnd.uniform(lr + 6, lr + 70)
        x, y = lx + math.cos(a) * r, ly + math.sin(a) * r
        if biome(x, y)[0] == "snow" and not on_road(x, y, 5):
            place("pine", (x, y, ground(x, y)), rnd.uniform(0, 90), rnd.uniform(0.9, 1.6))
    for k in range(9):
        a = rnd.uniform(0, math.tau)
        x, y = lx + math.cos(a) * rnd.uniform(5, lr - 8), ly + math.sin(a) * rnd.uniform(5, lr - 8)
        place("ice_spike", (x, y, -0.4), rnd.uniform(0, 90), rnd.uniform(0.6, 1.5))
    # CUEVAS
    place("cave", (-40, 112, 6), 0, 1.0)
    place("cave", (170, 115, 6), 0, 1.2)
    # DESIERTO
    place("pyramid", (PYRAMID[0], PYRAMID[1], ground(*PYRAMID)), 0)
    ox, oy = OASIS
    for k in range(10):
        a = k / 10 * math.tau + 0.2
        x, y = ox + math.cos(a) * 16, oy + math.sin(a) * 16
        place("palm", (x, y, 2.0), math.degrees(a), rnd.uniform(0.9, 1.3))
    place("ruins", (235, 30, ground(235, 30)), 0)
    place("ruins", (160, -40, ground(160, -40)), 40, 0.8)
    # MAGIA: islas flotantes, cristales y nubes
    for x, y, z, s in [(-30, -40, 95, 1.0), (95, 10, 110, 0.8), (-150, -120, 100, 0.7), (150, -120, 120, 0.6)]:
        place("isle", (x, y, z), rnd.uniform(0, 90), s)
        place("tree1", (x + 3, y + 2, z + 4), 0, 1.0 * s + 0.3)
        place("crystal_violet", (x - 5, y - 4, z + 4), 0, 1.3)
    for x, y in [(-60, -85), (VILLAGE[0] + 2, VILLAGE[1]), (GORGE_X + 6, 70), (OASIS[0] - 8, OASIS[1] - 18), (WORLD_TREE[0] + 14, WORLD_TREE[1] - 16), (-150, 90), (130, -60)]:
        place("crystal_teal" if rnd.random() < 0.5 else "crystal_violet", (x, y, ground(x, y)), rnd.uniform(0, 90), 1.4)
    for k in range(14):
        place("cloud", (rnd.uniform(-300, 300), rnd.uniform(-220, 200), rnd.uniform(130, 160)), rnd.uniform(0, 90), rnd.uniform(0.8, 1.6))
    # luces mágicas y cálidas
    for (x, y, z), col, p in [((WORLD_TREE[0], WORLD_TREE[1], 50), (0.4, 1.0, 0.8), 2.0e5), ((-40, 106, 12), (0.3, 1.0, 0.9), 6e4), ((170, 109, 12), (0.3, 1.0, 0.9), 6e4),
                              ((-262, -120, 25), (1.0, 0.75, 0.4), 6e4), ((PYRAMID[0], PYRAMID[1], 40), (0.8, 0.3, 1.0), 6e4), ((GORGE_X + 4, 128, 20), (1.0, 0.6, 0.3), 5e4)]:
        d = bpy.data.lights.new("magic", "POINT"); d.color = col; d.energy = p * S * S; d.shadow_soft_size = 2 * S
        o = bpy.data.objects.new("magic", d); o.location = (x, y, z); link(o)


# ───────────────────────── materiales ─────────────────────────
def materials():
    D = F.detail_mat
    M = {
        "meadow": D("Meadow", "meadow", "box", repeat=0.09, grime=0, edge=0.15, ao=0.6, tint=(0.8, 0.95, 0.7)),
        "forest": D("ForestFloor", "meadow", "box", repeat=0.09, grime=0, edge=0.15, ao=0.6, tint=(0.55, 0.7, 0.5)),
        "crop": D("Crop", "crop", "box", repeat=0.12, grime=0, edge=0.1, ao=0.5),
        "beach": D("Beach", "beach", "box", repeat=0.1, grime=0, edge=0.1, ao=0.5),
        "sand": D("Sand", "sand", "box", repeat=0.08, grime=0, edge=0.12, ao=0.5),
        "sand_side": D("SandSide", "sand", "box", repeat=0.12, grime=0, edge=0.2, ao=0.6, tint=(0.85, 0.75, 0.62)),
        "red_rock": D("RedRock", "red_rock", "box", repeat=0.08, grime=0, edge=0.25, ao=0.7),
        "snow": D("Snow", "snow", "box", repeat=0.08, grime=0, edge=0.1, ao=0.45),
        "snow_side": D("SnowSide", "moss_rock", "box", repeat=0.12, grime=0, edge=0.25, ao=0.6, tint=(0.75, 0.8, 0.92)),
        "rock": D("Rock", "moss_rock", "box", repeat=0.1, grime=0, edge=0.3, ao=0.75, tint=(0.66, 0.65, 0.7)),
        "rock_dark": D("RockDark", "moss_rock", "box", repeat=0.12, grime=0, edge=0.3, ao=0.8, tint=(0.4, 0.4, 0.45)),
        "grass": D("MountGrass", "grass", "box", repeat=0.1, grime=0, edge=0.12, ao=0.6),
        "dirt": D("Dirt", "dirt", "box", repeat=0.12, grime=0, edge=0.05, ao=0.5),
        "dirt_side": D("DirtSide", "dirt", "box", repeat=0.12, grime=0, edge=0.25, ao=0.65, tint=(0.75, 0.66, 0.56)),
        "paving": D("Paving", "paving", "box", repeat=0.18, grime=0, edge=0.05),
        "bark": D("Bark", "wood", "box", repeat=0.4, grime=0, edge=0.2, tint=(0.6, 0.45, 0.35)),
        "leaves": D("Leaves", "leaves_cube", "box", repeat=0.25, grime=0, edge=0.05, ao=0.75, tint=(0.55, 0.85, 0.42)),
        "leaves_dark": D("LeavesDark", "leaves_cube", "box", repeat=0.25, grime=0, edge=0.05, ao=0.7, tint=(0.45, 0.65, 0.55)),
        "leaves_autumn": D("LeavesAutumn", "leaves_cube", "box", repeat=0.25, grime=0, edge=0.05, ao=0.7, tint=(1.4, 0.8, 0.35)),
        "leaves_magic": D("LeavesMagic", "leaves_cube", "box", repeat=0.25, grime=0, edge=0.4, ao=0.6, tint=(0.6, 1.1, 1.2)),
        "pine_snow": D("PineSnow", "snow", "box", repeat=0.25, grime=0, edge=0.3, ao=0.6),
        "sandstone": D("Sandstone", "sand", "box", repeat=0.15, grime=0, edge=0.35, ao=0.75, tint=(1.0, 0.82, 0.6)),
        "plaster": D("Plaster", "wall", "box", repeat=0.25, grime=1.5, edge=0.2),
        "wood": D("Wood", "wood", "box", repeat=0.35, grime=0, edge=0.2),
        "roof_red": D("RoofRed", "roof_red", "box", repeat=0.3, grime=0, edge=0.15, rough=0.5),
        "isle_top": D("IsleTop", "meadow", "box", repeat=0.12, grime=0, edge=0.2, ao=0.6),
        "sea": F.water_mat("Sea", (0.04, 0.22, 0.32), 0.03),
        "falls": F.water_mat("Falls2", (0.55, 0.72, 0.82), 0.15, foam=1.0),
        "cloud": F.flat("Cloud", (0.95, 0.96, 1.0), 1.0),
        "void": F.flat("Void", (0.01, 0.01, 0.015), 1.0),
        "lamp": F.flat("Lamp", (1.0, 0.8, 0.45), 0.3, emission=(1.0, 0.75, 0.4), strength=20.0),
        "spark": F.flat("Spark", (0.6, 1.0, 0.8), 0.3, emission=(0.5, 1.0, 0.8), strength=25.0),
        "crystal_teal": F.flat("CrystalTeal", (0.2, 0.9, 0.85), 0.1, emission=(0.2, 1.0, 0.9), strength=9.0),
        "crystal_violet": F.flat("CrystalViolet", (0.6, 0.3, 1.0), 0.1, emission=(0.65, 0.3, 1.0), strength=9.0),
        "ice_glow": F.flat("IceGlow", (0.7, 0.92, 1.0), 0.08, emission=(0.4, 0.8, 1.0), strength=1.2),
    }
    ice = F.water_mat("Ice", (0.62, 0.86, 0.95), 0.12)
    M["ice"] = D("IceTex", "ice", "box", repeat=0.04, grime=0, edge=0, ao=0.3, rough=0.08)
    return M


# ───────────────────────── luz, cámara ─────────────────────────
SHOTS = {  # objetivo, elevación, azimut, anchura visible (m), f-stop
    "world": ((-10, -10, 10), 52, -18, 720, 5.6),
    "desert": ((225, -20, 10), 34, -30, 190, 2.8),
    "frost": ((-170, 125, 6), 36, 20, 170, 2.8),
    "castle": ((-215, -70, 18), 32, 35, 150, 2.8),
    "fortress": ((20, 115, 16), 30, -10, 150, 2.8),
    "isles": ((-40, -60, 60), 22, -25, 260, 4.0),
    "plains": ((0, -70, 10), 30, -20, 260, 4.0),
}


def light_and_camera():
    sc = bpy.context.scene
    w = bpy.data.worlds.new("Sky"); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    try:
        sky = w.node_tree.nodes.new("ShaderNodeTexSky")
        for t in ("NISHITA", "MULTIPLE_SCATTERING", "PREETHAM"):
            try: sky.sky_type = t; break
            except Exception: pass
        try: sky.sun_elevation = math.radians(28)
        except Exception: pass
        w.node_tree.links.new(sky.outputs[0], bg.inputs[0]); bg.inputs[1].default_value = 0.18
    except Exception:
        bg.inputs[0].default_value = (0.45, 0.6, 0.85, 1)
    sun = bpy.data.lights.new("Sun", "SUN"); sun.energy = 4.5; sun.color = (1.0, 0.86, 0.68); sun.angle = math.radians(3)
    so = bpy.data.objects.new("Sun", sun); sc.collection.objects.link(so); so.rotation_euler = (math.radians(58), 0, math.radians(-40))
    fill = bpy.data.lights.new("Fill", "SUN"); fill.energy = 0.7; fill.color = (0.55, 0.68, 1.0); fill.angle = math.radians(25)
    fo = bpy.data.objects.new("Fill", fill); sc.collection.objects.link(fo); fo.rotation_euler = (math.radians(50), 0, math.radians(150))
    # bruma atmosférica
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    me = bpy.data.meshes.new("Haze"); bm.to_mesh(me); bm.free()
    hm = bpy.data.materials.new("Haze"); hm.use_nodes = True; nt = hm.node_tree; nt.nodes.remove(nt.nodes["Principled BSDF"])
    v = nt.nodes.new("ShaderNodeVolumePrincipled"); v.inputs["Density"].default_value = 0.00009 / S; v.inputs["Color"].default_value = (0.8, 0.86, 1.0, 1)
    nt.links.new(v.outputs[0], nt.nodes["Material Output"].inputs["Volume"]); me.materials.append(hm)
    ho = bpy.data.objects.new("Haze", me); sc.collection.objects.link(ho); ho.scale = (900 * S, 800 * S, 260 * S); ho.location = (0, 0, 90 * S)
    # raíz a escala de maqueta
    root = bpy.data.objects.new("World_Root", None); sc.collection.objects.link(root)
    for o in PLACED:
        o.parent = root
    root.scale = (S, S, S)
    bpy.context.view_layer.update()
    (tx, ty, tz), elev, az, width, fstop = SHOTS.get(W["shot"], SHOTS["world"])
    cd = bpy.data.cameras.new("Cam"); cd.lens = 65; cd.sensor_width = 36
    dist = (width * S / 2) / math.tan(math.atan(18 / 65))
    e, a = math.radians(elev), math.radians(az)
    c = bpy.data.objects.new("Cam", cd); sc.collection.objects.link(c)
    target = Vector((tx, ty, tz)) * S
    c.location = target + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
    f = bpy.data.objects.new("Focus", None); sc.collection.objects.link(f); f.location = target
    tr = c.constraints.new("TRACK_TO"); tr.target = f; tr.track_axis = "TRACK_NEGATIVE_Z"; tr.up_axis = "UP_Y"
    cd.clip_start = 0.005; cd.clip_end = 100
    cd.dof.use_dof = True; cd.dof.focus_object = f; cd.dof.aperture_fstop = fstop
    sc.camera = c


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    F.prepare_facades(); F.make_snow()
    FM = F.materials()
    M = materials()
    # variantes del castillo real con tejados rojos (se renombran tras construirlas)
    CM = dict(FM, roof=M["roof_red"])
    for fn, new in ((F.wall_tower, "castle_tower"), (F.keep, "castle_keep"), (F.house, "castle_house"), (F.wall_segment, "castle_wall"), (F.gatehouse, "castle_gate")):
        fn(CM)
        F.MODULES[new] = F.MODULES.pop(fn.__name__)
    for fn in (F.wall_segment, F.wall_tower, F.gatehouse, F.keep, F.house, F.waterfall):
        fn(FM)
    M.update({k: v for k, v in FM.items() if k not in M})
    build_modules(M)
    build_terrain(M)
    populate(M)
    light_and_camera()
    F.CFG["res"], F.CFG["samples"], F.CFG["out"] = W["res"], W["samples"], W["out"]
    F.render_settings()
    vs = bpy.context.scene.view_settings
    vs.exposure = -0.85
    for lk in ("AgX - Punchy", "Punchy", "AgX - High Contrast", "High Contrast"):
        try:
            vs.look = lk
            break
        except Exception:
            pass
    log("Mundo listo: %d objetos colocados, %d módulos" % (len(PLACED), len(F.MODULES)))
    if W["render"] and bpy.app.background:
        bpy.ops.render.render(write_still=True)
        log("Render → " + W["out"])


main()
