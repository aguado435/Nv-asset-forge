"""
worldgen.py · motor de mundos por receta (JSON) para NV Asset Forge
===================================================================
Construye en Blender un mundo cúbico 2D-HD a partir de una "receta" JSON: masas de
tierra, biomas, montañas, cordilleras, mesetas, volcanes, lagos, ríos, caminos,
gargantas, lugares emblemáticos compuestos (fortaleza, castillo, aldea, puerto,
oasis, campamento) y dispersión de módulos. Las recetas las puede escribir una
persona o el LLM diseñador de niveles de la app.

Uso:
  blender -b -P worldgen.py -- --spec worlds/aethermoor.json [--shot world|lm0|lm1...]
         [--res 1600x900] [--samples 40] [--out render.png] [--save-blend mundo.blend]
         [--export-glb mundo.glb]
"""
import json
import math
import os
import random
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_world as BW  # noqa: E402  (materiales, módulos, utilidades)

F = BW.F
G = {"spec": os.path.join(HERE, "worlds", "aethermoor.json"), "shot": "world", "res": (1600, 900), "samples": 40,
     "out": os.path.join(HERE, "render_world.png"), "blend": None, "glb": None, "render": True}
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
for i, a in enumerate(argv):
    if a == "--spec": G["spec"] = argv[i + 1]
    if a == "--shot": G["shot"] = argv[i + 1]
    if a == "--res": G["res"] = tuple(int(v) for v in argv[i + 1].split("x"))
    if a == "--samples": G["samples"] = int(argv[i + 1])
    if a == "--out": G["out"] = argv[i + 1]
    if a == "--save-blend": G["blend"] = argv[i + 1]
    if a == "--export-glb": G["glb"] = argv[i + 1]
    if a == "--no-render": G["render"] = False

with open(G["spec"], "r", encoding="utf-8") as fh:
    SPEC = json.load(fh)


def log(m):
    print("WORLD:", m, flush=True)


# ───────────────────────── catálogo (lo que el LLM puede usar) ─────────────────────────
BIOMES = ["plains", "forest", "farmland", "desert", "snow", "mountain", "swamp", "volcanic", "beach"]
COMPOSITES = {"fortress": 46, "castle": 40, "village": 32, "port": 26, "oasis": 24, "camp": 20, "pyramid": 28, "world_tree": 22}
MODULE_INFO = {
    "tree0": "árbol cúbico verde", "tree1": "árbol cúbico oscuro alto", "tree2": "árbol cúbico otoñal", "pine": "pino nevado",
    "palm": "palmera", "crystal_teal": "cristal arcano turquesa (brilla)", "crystal_violet": "cristal arcano violeta (brilla)",
    "ice_spike": "aguja de hielo", "windmill": "molino", "pyramid": "pirámide escalonada", "cave": "boca de cueva con cristales",
    "isle": "isla flotante (usar floating_isles)", "cloud": "nube de cubos (usar clouds)", "lighthouse": "faro", "boat": "barco de vela",
    "ruins": "columnas en ruinas", "world_tree": "Árbol del Mundo gigante", "house": "casa de piedra y madera", "castle_house": "casa de tejado rojo",
    "wall_tower": "torre de muralla", "castle_tower": "torre de tejado rojo", "keep": "torreón-ciudadela", "castle_keep": "torreón de tejados rojos",
    "waterfall": "cascada alta con poza (colocar al pie de una pared)", "tent": "tienda de campaña de pieles", "pier": "embarcadero de madera",
    "bridge": "puente de piedra (rotar para cruzar el río)", "monolith": "monolito rúnico antiguo",
}


# ───────────────────────── geografía genérica ─────────────────────────
n2 = BW.n2
q = BW.q
dist_seg = BW.dist_seg


def d_poly(x, y, pts):
    return min(dist_seg(x, y, pts[k], pts[k + 1]) for k in range(len(pts) - 1)) if len(pts) > 1 else 1e9


def poly_sd(x, y, poly):
    """Distancia con signo a un polígono (positiva dentro)."""
    inside, n = False, len(poly)
    for k in range(n):
        (x1, y1), (x2, y2) = poly[k], poly[(k + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-9) + x1:
            inside = not inside
    d = min(dist_seg(x, y, poly[k], poly[(k + 1) % n]) for k in range(n))
    return d if inside else -d


def landness(x, y):
    """>0 tierra, <0 mar. Círculos (land) + contornos de costa (land_polygons) − mares interiores (sea_polygons)."""
    land = SPEC.get("land") or ([] if SPEC.get("land_polygons") else [{"x": 0, "y": 0, "r": 260}])
    v = max([1 - math.hypot(x - l["x"], y - l["y"]) / max(1, l["r"]) for l in land] or [-1.0])
    for poly in SPEC.get("land_polygons", []):
        if len(poly) > 2:
            v = max(v, poly_sd(x, y, poly) / 70.0)
    for poly in SPEC.get("sea_polygons", []):
        if len(poly) > 2:
            sd = poly_sd(x, y, poly)
            if sd > 0:
                v = min(v, -sd / 70.0 - 0.02)
            else:
                v = min(v, -sd / 70.0)
    return v + 0.05 * n2(x * 1.9, y * 1.9)


def region_at(x, y):
    b = SPEC.get("default_biome", "plains")
    for r in SPEC.get("regions", []):
        rr = r.get("r", 60) * (1 + 0.14 * n2(x * 2.7 + r.get("x", 0), y * 2.7))
        if math.hypot(x - r.get("x", 0), y - r.get("y", 0)) < rr:
            b = r.get("biome", b)
    return b if b in BIOMES else "plains"


def terrain_raw(x, y):
    L = landness(x, y)
    if L < 0:
        return q(-3 - min(14, -L * 60)), "beach", "rock", "sea"
    b = region_at(x, y)
    nn = n2(x, y)
    top, side = {"plains": ("meadow", "dirt_side"), "forest": ("forest", "dirt_side"), "farmland": ("meadow", "dirt_side"),
                 "desert": ("sand", "sand_side"), "snow": ("snow", "snow_side"), "mountain": ("grass", "rock"),
                 "swamp": ("swamp", "dirt_side"), "volcanic": ("ash", "rock_dark"), "beach": ("beach", "beach")}[b]
    if b == "desert":
        h = 4 + 3 * math.sin(x * 0.06 + math.sin(y * 0.05) * 2) + 2 * nn
    elif b == "mountain":
        h = 12 + 10 * abs(n2(x * 1.7, y * 1.7))
    elif b == "swamp":
        h = 1.5 + 1.2 * nn
        if n2(x * 3.1, y * 3.1) > 0.45:
            return -2.0, "beach", "dirt_side", b
    elif b == "volcanic":
        h = 4 + 2.5 * nn
    else:
        h = 3 + 2.4 * nn
    if b == "farmland" and (int((x + 4000) / 16) + int((y + 4000) / 12)) % 3 != 0:
        top = "crop"
    if L < 0.05 and b not in ("mountain", "volcanic"):
        return 1.0, "beach", "beach", "beach"
    for hl in SPEC.get("hills", []):
        d = math.hypot(x - hl["x"], y - hl["y"])
        if d < hl["r"]:
            h += hl.get("h", 12) * (1 - d / hl["r"])
    peak = None
    for m in SPEC.get("mountains", []):
        d = math.hypot(x - m["x"], y - m["y"])
        if d < m["r"]:
            ph = 8 + m.get("h", 60) * (1 - d / m["r"]) ** 0.8 + 10 * abs(n2(x * 1.7, y * 1.7))
            peak = max(peak or 0, ph)
    for r in SPEC.get("ridges", []):
        d = dist_seg(x, y, r["from"], r["to"])
        w = r.get("w", 40)
        if d < w:
            ph = 8 + r.get("h", 60) * (1 - d / w) ** 0.7 + 12 * abs(n2(x * 1.7, y * 1.7))
            peak = max(peak or 0, ph)
    if peak is not None and peak > h:
        h = q(peak, 4)
        top, side = ("snow" if h > 62 else "rock" if h > 30 else "grass"), "rock"
    for m in SPEC.get("mesas", []):
        d = math.hypot(x - m["x"], y - m["y"])
        if d < m.get("r", 24):
            mh = m.get("h", 32) - max(0, d - m.get("r", 24) * 0.4) * 2.2
            if mh > h:
                h, top, side = mh, "red_rock", "red_rock"
    for v in SPEC.get("volcanoes", []):
        d = math.hypot(x - v["x"], y - v["y"])
        r = v.get("r", 50)
        if d < r:
            vh = v.get("h", 70) * (1 - d / r) ** 1.1 + 6 * abs(nn)
            if d < r * 0.16 and not v.get("dormant"):
                return q(v.get("h", 70) * 0.72, 4), "lava", "rock_dark", "volcanic"
            if vh > h:
                h, top, side = q(vh, 4), ("snow" if v.get("snowcap") and vh > v.get("h", 70) * 0.62 else "ash" if not v.get("green") else "grass"), "rock_dark"
    for g in SPEC.get("gorges", []):
        if dist_seg(x, y, g["from"], g["to"]) < g.get("w", 22):
            return float(g.get("floor", 6)), "paving", "rock", b
    for lk in SPEC.get("lakes", []):
        if math.hypot(x - lk["x"], y - lk["y"]) < lk.get("r", 30) * (1 + 0.1 * n2(x * 3, y * 3)):
            return -2.0, "snow" if lk.get("frozen") else "beach", "rock", "lake"
    for rv in SPEC.get("rivers", []):
        if d_poly(x, y, rv["points"]) < rv.get("w", 5):
            return -2.0, "beach", "rock", "river"
    for rd in SPEC.get("roads", []):
        if d_poly(x, y, rd["points"]) < rd.get("w", 3.2) and b not in ("mountain",):
            return max(2.0, q(3 + 2.4 * nn)), "dirt", "dirt_side", b
    return q(h), top, side, b


FLAT = []  # (x, y, r, altura) zonas niveladas bajo los lugares emblemáticos


def terrain(x, y):
    for fx, fy, fr, fh in FLAT:
        d = math.hypot(x - fx, y - fy)
        if d < fr:
            h, top, side, b = terrain_raw(x, y)
            if b in ("lake", "river", "sea"):
                return h, top, side, b
            if d < fr * 0.8:
                return fh, ("sand" if b == "desert" else "paving" if b == "mountain" else "snow" if b == "snow" else "meadow"), side, b
            t = (d - fr * 0.8) / (fr * 0.2)
            return q(fh * (1 - t) + h * t), top, side, b
    return terrain_raw(x, y)


# ───────────────────────── terreno ─────────────────────────
def build_terrain(M):
    x0, x1, y0, y1 = SPEC.get("bounds", [-320, 320, -240, 240])
    cell = float(SPEC.get("cell", 4))
    BW.X0, BW.X1, BW.Y0, BW.Y1, BW.CELL = x0, x1, y0, y1, cell
    keys = ["meadow", "forest", "crop", "beach", "sand", "red_rock", "snow", "rock", "grass", "dirt", "paving",
            "dirt_side", "sand_side", "snow_side", "swamp", "ash", "lava", "rock_dark"]
    idx = {k: i for i, k in enumerate(keys)}
    # nivelado de los emblemáticos (antes de construir)
    FLAT.clear()
    for lm in SPEC.get("landmarks", []):
        r = COMPOSITES.get(lm.get("type"))
        if r:
            h, _, _, b = terrain_raw(lm["x"], lm["y"])
            FLAT.append((lm["x"], lm["y"], r * lm.get("scale", 1.0), max(2.0, q(h)) if b != "mountain" else q(h)))
    nx, ny = int((x1 - x0) / cell), int((y1 - y0) / cell)
    base, hc = -20.0, cell / 2
    BW.HEIGHTS.clear()
    verts, faces, mats = [], [], []
    for i in range(nx):
        for j in range(ny):
            x, y = x0 + (i + 0.5) * cell, y0 + (j + 0.5) * cell
            h, top, side, _ = terrain(x, y)
            BW.HEIGHTS[(i, j)] = h
            v = len(verts)
            verts += [(x - hc, y - hc, base), (x + hc, y - hc, base), (x + hc, y + hc, base), (x - hc, y + hc, base),
                      (x - hc, y - hc, h), (x + hc, y - hc, h), (x + hc, y + hc, h), (x - hc, y + hc, h)]
            faces += [(v + 4, v + 5, v + 6, v + 7), (v, v + 1, v + 5, v + 4), (v + 1, v + 2, v + 6, v + 5), (v + 2, v + 3, v + 7, v + 6), (v + 3, v, v + 4, v + 7)]
            mats += [idx[top], idx[side], idx[side], idx[side], idx[side]]
    me = bpy.data.meshes.new("Terrain")
    me.from_pydata(verts, [], faces)
    me.polygons.foreach_set("material_index", mats)
    me.update()
    for k in keys:
        me.materials.append(M[k])
    BW.link(bpy.data.objects.new("Terrain", me))
    sea = F.facade_box("Sea", (x1 - x0 + 500, y1 - y0 + 500, 0.2), [M["sea"]]); sea.modifiers.clear()
    sea.location = (0, 0, -0.6); BW.link(sea)
    import bmesh
    for lk in SPEC.get("lakes", []):
        if lk.get("frozen"):
            bm = bmesh.new(); bmesh.ops.create_circle(bm, cap_ends=True, segments=40, radius=lk.get("r", 30) + 3)
            m2 = bpy.data.meshes.new("Ice"); bm.to_mesh(m2); bm.free(); m2.materials.append(M["ice"])
            o = bpy.data.objects.new("Ice", m2); o.location = (lk["x"], lk["y"], -0.2); BW.link(o)
    log("Terreno: %d columnas" % (nx * ny))


# ───────────────────────── módulos extra ─────────────────────────
def extra_modules(M):
    cube, coll = BW.cube, BW.coll
    parts = [F.pyramid("tent", 5, 4.5, M["leather"], 0.2)]
    parts.append(cube("tent_pole", (0.3, 0.3, 5.6), (0, 0, 0), M["wood"], 0, 0))
    coll("tent", parts)
    parts = [cube(f"pier_plank{k}", (4, 2.0, 0.4), (0, -k * 2.1, 0.6), M["wood"], 0, 0.06) for k in range(8)]
    parts += [cube(f"pier_post{k}", (0.5, 0.5, 3.5), (s * 1.8, -k * 4.2, -2.6), M["wood"], 0, 0.05) for k in range(4) for s in (-1, 1)]
    coll("pier", parts)
    parts = [cube("bridge_deck", (5, 16, 1.0), (0, 0, 1.6), M["paving"], 0, 0.2)]
    parts += [cube(f"bridge_rail{s}", (0.6, 16, 1.0), (s * 2.6, 0, 2.6), M["plaster"], 0, 0.1) for s in (-1, 1)]
    parts += [cube(f"bridge_pier{s}", (4, 2.5, 3.5), (0, s * 5.5, -1.8), M["plaster"], 0, 0.2) for s in (-1, 1)]
    coll("bridge", parts)
    parts = [cube("monolith", (2.4, 1.6, 9), (0, 0, 0), M["rock_dark"], 8, 0.25), cube("monolith_rune", (1.0, 0.2, 5), (0, -0.85, 2), M["crystal_teal"], 8, 0.05)]
    coll("monolith", parts)


# ───────────────────────── emblemáticos compuestos ─────────────────────────
def rot(cx, cy, dx, dy, deg):
    a = math.radians(deg)
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def P(mod, x, y, z=None, r=0.0, s=1.0):
    if mod not in F.MODULES:
        return
    BW.place(mod, (x, y, BW.ground(x, y) if z is None else z), r, s)


def landmark(lm):
    t, x, y = lm.get("type"), lm["x"], lm["y"]
    a, s = lm.get("rot", 0.0), lm.get("scale", 1.0)
    z = BW.ground(x, y)
    if t == "fortress":
        pts = [(-30, 6), (-20, 3), (-10, 1), (0, 0), (10, 1), (20, 3), (30, 6)]
        pw = [rot(x, y, px * s, py * s, a) for px, py in pts]
        for k in range(6):
            (x0, y0), (x1, y1) = pw[k], pw[k + 1]
            ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
            P("gatehouse" if k == 3 else "wall_segment", (x0 + x1) / 2, (y0 + y1) / 2, z, ang, (1.02 * s, s, s))
        for k in (0, 2, 4, 6):
            P("wall_tower", pw[k][0], pw[k][1], z, a, s)
        kx, ky = rot(x, y, 4 * s, 40 * s, a); P("keep", kx, ky, z, a, s)
        for dx, dy, rr in [(-12, 14, 0), (-2, 18, 6), (14, 16, -6), (-10, 28, 3), (16, 30, -4)]:
            hx, hy = rot(x, y, dx * s, dy * s, a); P("house", hx, hy, z, a + rr, s)
    elif t == "castle":
        ring = [rot(x, y, math.cos(q_) * 30 * s, math.sin(q_) * 30 * s, 0) for q_ in [k * math.tau / 6 + 0.3 + math.radians(a) for k in range(6)]]
        for k in range(6):
            (x0, y0), (x1, y1) = ring[k], ring[(k + 1) % 6]
            ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
            P("castle_gate" if k == 4 else "castle_wall", (x0 + x1) / 2, (y0 + y1) / 2, z, ang, (2.9 * s, s, s) if k != 4 else s)
            P("castle_tower", x0, y0, z, a, 1.15 * s)
        P("castle_keep", x + 2, y + 6, z, a, 1.1 * s)
        for k in range(5):
            hx, hy = rot(x, y, math.cos(k * 1.2 + 0.5) * 16 * s, math.sin(k * 1.2 + 0.5) * 16 * s, 0)
            P("castle_house", hx, hy, z, math.degrees(k * 1.2 + 0.5), s)
    elif t == "village":
        for k in range(9):
            q_ = k / 9 * math.tau
            hx, hy = x + math.cos(q_) * 18 * s, y + math.sin(q_) * 14 * s
            P("castle_house" if k % 3 == 0 else "house", hx, hy, z, math.degrees(q_) + 90, s)
        for dx, dy in ((34, -20), (-28, 24)):
            mx, my = rot(x, y, dx * s, dy * s, a); P("windmill", mx, my, None, rnd.uniform(-20, 20), s)
    elif t == "port":
        for k in range(3):
            px_, py_ = rot(x, y, (k - 1) * 12 * s, -6 * s, a); P("pier", px_, py_, 0.0, a, s)
        for k in range(3):
            bx, by = rot(x, y, (k - 1) * 12 * s + 3, -24 * s, a); P("boat", bx, by, -0.7, a + rnd.uniform(-20, 20), s)
        for k in range(5):
            hx, hy = rot(x, y, (k - 2) * 9 * s, 10 * s, a); P("house" if k % 2 else "castle_house", hx, hy, z, a, 0.85 * s)
        lx, ly = rot(x, y, 26 * s, -4 * s, a); P("lighthouse", lx, ly, None, 0, s)
    elif t == "oasis":
        for k in range(10):
            q_ = k / 10 * math.tau + 0.2
            P("palm", x + math.cos(q_) * 15 * s, y + math.sin(q_) * 15 * s, z, math.degrees(q_), rnd.uniform(0.9, 1.3) * s)
    elif t == "camp":
        for k in range(7):
            q_ = k / 7 * math.tau
            P("tent", x + math.cos(q_) * 11 * s, y + math.sin(q_) * 11 * s, z, math.degrees(q_), s)
        P("monolith", x, y, z, a, 0.6 * s)
        light((x, y, z + 4), (1.0, 0.5, 0.2), 4e4)
    elif t == "world_tree":
        P("world_tree", x, y, z, a, s)
        light((x, y, z + 50 * s), (0.4, 1.0, 0.8), 2e5)
    elif t in F.MODULES:
        P(t, x, y, lm.get("z"), a, s)
        if t == "cave":
            light((x, y - 6, z + 6), (0.3, 1.0, 0.9), 6e4)
        if t == "lighthouse":
            light((x, y, z + 25), (1.0, 0.75, 0.4), 6e4)
    if t in ("fortress", "castle", "village", "port"):
        for k in range(4):
            lx, ly = rot(x, y, (k - 1.5) * 14 * s, 4 * s, a)
            light((lx, ly, z + 6), (1.0, 0.6, 0.3), 1.5e4)


def light(loc, color, power):
    d = bpy.data.lights.new("lm_light", "POINT"); d.color = color; d.energy = power * BW.S * BW.S; d.shadow_soft_size = 2 * BW.S
    o = bpy.data.objects.new("lm_light", d); o.location = loc; BW.link(o)


rnd = random.Random(SPEC.get("seed", 7))


def populate():
    for lm in SPEC.get("landmarks", []):
        landmark(lm)
    budget = 900
    for sc in SPEC.get("scatter", []):
        mods = [m for m in sc.get("modules", []) if m in F.MODULES]
        if not mods:
            continue
        lo, hi = (sc.get("scale") or [0.8, 1.3])[:2]
        for k in range(min(int(sc.get("count", 30)), budget)):
            a_, r_ = rnd.uniform(0, math.tau), sc.get("r", 40) * math.sqrt(rnd.random())
            x, y = sc["x"] + math.cos(a_) * r_, sc["y"] + math.sin(a_) * r_
            h, _, _, b = terrain(x, y)
            if b in ("sea", "lake", "river") or h < 0:
                continue
            if any(math.hypot(x - fx, y - fy) < fr * 0.85 for fx, fy, fr, _ in FLAT):
                continue
            P(rnd.choice(mods), x, y, h, rnd.uniform(0, 90), rnd.uniform(lo, hi))
            budget -= 1
    for isle in SPEC.get("floating_isles", []):
        x, y, z, s = isle["x"], isle["y"], isle.get("z", 100), isle.get("scale", 1.0)
        P("isle", x, y, z, rnd.uniform(0, 90), s)
        P("tree1", x + 3, y + 2, z + 4, 0, s + 0.3)
        P("crystal_violet", x - 5, y - 4, z + 4, 0, 1.3)
    x0, x1, y0, y1 = SPEC.get("bounds", [-320, 320, -240, 240])
    for k in range(int(SPEC.get("clouds", 12))):
        P("cloud", rnd.uniform(x0, x1), rnd.uniform(y0, y1), rnd.uniform(130, 165), rnd.uniform(0, 90), rnd.uniform(0.8, 1.6))


def shots():
    x0, x1, y0, y1 = SPEC.get("bounds", [-320, 320, -240, 240])
    # encuadre automático a la tierra emergida (no al mapa entero)
    cell = BW.CELL
    land = [(x0 + (i + 0.5) * cell, y0 + (j + 0.5) * cell) for (i, j), h in BW.HEIGHTS.items() if h > 0.5]
    if land:
        lx0, lx1 = min(p[0] for p in land), max(p[0] for p in land)
        ly0, ly1 = min(p[1] for p in land), max(p[1] for p in land)
    else:
        lx0, lx1, ly0, ly1 = x0, x1, y0, y1
    w = max(lx1 - lx0, (ly1 - ly0) * 1.25) * 1.12 + 40
    out = {"world": (((lx0 + lx1) / 2, (ly0 + ly1) / 2 - (ly1 - ly0) * 0.04, 10), 52, -18, w, 5.6)}
    for k, lm in enumerate(SPEC.get("landmarks", [])):
        out[f"lm{k}"] = ((lm["x"], lm["y"], BW.ground(lm["x"], lm["y"]) + 8), 32, -18, 150 * lm.get("scale", 1.0), 2.8)
    for name, sh in (SPEC.get("shots") or {}).items():
        out[name] = (tuple(sh.get("target", [0, 0, 10])), sh.get("elev", 35), sh.get("az", -20), sh.get("width", 200), sh.get("fstop", 4.0))
    return out


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    F.prepare_facades(); F.make_snow()
    FM = F.materials()
    M = BW.materials()
    D = F.detail_mat
    M.update({
        "swamp": D("Swamp", "meadow", "box", repeat=0.09, grime=0, edge=0.1, ao=0.65, tint=(0.45, 0.55, 0.32)),
        "ash": D("Ash", "dark_stone", "box", repeat=0.12, grime=0, edge=0.2, ao=0.7, tint=(0.6, 0.55, 0.55)),
        "lava": F.flat("Lava", (1.0, 0.3, 0.05), 0.3, emission=(1.0, 0.3, 0.04), strength=12.0),
        "leather": D("Leather", "thatch", "box", repeat=0.3, grime=0, edge=0.2, tint=(0.7, 0.5, 0.35)),
    })
    CM = dict(FM, roof=M["roof_red"])
    for fn, new in ((F.wall_tower, "castle_tower"), (F.keep, "castle_keep"), (F.house, "castle_house"), (F.wall_segment, "castle_wall"), (F.gatehouse, "castle_gate")):
        fn(CM)
        F.MODULES[new] = F.MODULES.pop(fn.__name__)
    for fn in (F.wall_segment, F.wall_tower, F.gatehouse, F.keep, F.house, F.waterfall):
        fn(FM)
    M.update({k: v for k, v in FM.items() if k not in M})
    BW.build_modules(M)
    extra_modules(M)
    build_terrain(M)
    populate()
    BW.SHOTS = shots()
    BW.W["shot"] = G["shot"] if G["shot"] in BW.SHOTS else "world"
    sun = SPEC.get("sun") or {}
    BW.light_and_camera()
    so = bpy.data.objects.get("Sun")
    wnt = bpy.context.scene.world.node_tree
    sky = next((n for n in wnt.nodes if n.type == "TEX_SKY"), None)
    if sky is not None:  # el cielo sigue al sol: atardeceres y noches coherentes
        el = math.radians(sun.get("elev", 32))
        try: sky.sun_elevation = el
        except Exception: pass
        try: sky.sun_rotation = math.radians(sun.get("az", -40) + 180)
        except Exception: pass
        bgn = next((n for n in wnt.nodes if n.type == "BACKGROUND"), None)
        if bgn is not None and sun.get("elev", 32) < 12:
            bgn.inputs[1].default_value = 0.35
    if so and sun:
        so.rotation_euler = (math.radians(90 - sun.get("elev", 32)), 0, math.radians(sun.get("az", -40)))
        so.data.energy = sun.get("energy", 4.5)
        if sun.get("color"):
            so.data.color = sun["color"]
    F.CFG["res"], F.CFG["samples"], F.CFG["out"] = G["res"], G["samples"], G["out"]
    F.render_settings()
    vs = bpy.context.scene.view_settings
    vs.exposure = SPEC.get("exposure", -0.85)
    for lk in ("AgX - Punchy", "Punchy"):
        try:
            vs.look = lk
            break
        except Exception:
            pass
    log("Mundo '%s' listo: %d objetos" % (SPEC.get("name", "?"), len(BW.PLACED)))
    if G["blend"]:
        bpy.ops.wm.save_as_mainfile(filepath=G["blend"], compress=True)
    if G["glb"]:
        bpy.ops.export_scene.gltf(filepath=G["glb"], export_format="GLB", export_apply=True)
    if G["render"] and bpy.app.background:
        bpy.ops.render.render(write_still=True)
        log("Render → " + G["out"])


if __name__ == "__main__":
    main()
