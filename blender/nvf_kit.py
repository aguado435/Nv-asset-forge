"""
NV Asset Forge · kit de modelado procedural para Blender.

Lo usan los scripts que escribe el LLM: piezas de alto nivel (muros, tejados,
vigas, ventanas…) con biselado, ligera irregularidad "hecha a mano" y
materiales con texturas tileables (proyección en caja, sin UVs manuales).
Compatible con Blender 3.6, 4.x y 5.x.
"""
import math
import os
import random

import bpy
import bmesh
from mathutils import Vector, Matrix, Euler

TEXTURES = {}          # clave -> ruta de imagen tileable (la rellena el runner)
_MATS = {}
random.seed(7)


# ───────────────────────── escena ─────────────────────────
def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MATS.clear()


def _link(obj):
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _finish(obj, mat=None, bevel=0.0, smooth=False, wobble=0.0, segments=2):
    if mat is not None:
        obj.data.materials.append(mat if not isinstance(mat, str) else material(mat))
    if wobble:
        jitter(obj, wobble)
    if bevel:
        m = obj.modifiers.new("Bevel", "BEVEL")
        m.width = bevel
        m.segments = segments
        m.limit_method = "ANGLE"
        m.angle_limit = math.radians(35)
    for p in obj.data.polygons:
        p.use_smooth = smooth
    return obj


def _mesh_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return _link(bpy.data.objects.new(name, me))


# ───────────────────────── materiales ─────────────────────────
def material(name, color=(0.8, 0.8, 0.8), rough=0.75, metal=0.0, tex=None, scale=1.0, emission=None, strength=3.0, tint=None, **_ignored):
    """Material PBR. tex = clave de TEXTURES (textura tileable) o ruta. scale = repeticiones por metro."""
    if isinstance(name, bpy.types.Material):
        return name
    key = (name, tex)
    if name in _MATS and tex is None:
        return _MATS[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    col = tuple(color) + (1.0,) if len(color) == 3 else tuple(color)
    bsdf.inputs["Base Color"].default_value = col
    path = TEXTURES.get(tex, tex) if tex else None
    if path and os.path.exists(str(path)):
        img = bpy.data.images.load(str(path), check_existing=True)
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = img
        t.projection = "BOX"
        t.projection_blend = 0.25
        coord = nt.nodes.new("ShaderNodeTexCoord")
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (scale, scale, scale)
        nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
        nt.links.new(mapping.outputs["Vector"], t.inputs["Vector"])
        if tint:
            mix = nt.nodes.new("ShaderNodeMix") if hasattr(bpy.types, "ShaderNodeMix") else None
            if mix is not None:
                mix.data_type = "RGBA"
                mix.blend_type = "MULTIPLY"
                mix.inputs[0].default_value = 1.0
                nt.links.new(t.outputs["Color"], mix.inputs[6])
                mix.inputs[7].default_value = tuple(tint) + (1.0,)
                nt.links.new(mix.outputs[2], bsdf.inputs["Base Color"])
            else:
                nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
        else:
            nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    if emission:
        key_e = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
        bsdf.inputs[key_e].default_value = tuple(emission) + (1.0,)
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = strength
    m.diffuse_color = col
    _MATS[name] = m
    return m


# ───────────────────────── primitivas ─────────────────────────
def box(name, size, loc=(0, 0, 0), mat=None, rot=(0, 0, 0), bevel=0.02, wobble=0.0, origin="center", **_ignored):
    """Caja de tamaño (x, y, z). origin='bottom' apoya la base en loc.z."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    if origin == "bottom":
        bmesh.ops.translate(bm, vec=Vector((0, 0, size[2] / 2)), verts=bm.verts)
    o = _mesh_obj(name, bm)
    o.location = loc
    o.rotation_euler = [math.radians(a) for a in rot]
    return _finish(o, mat, bevel, wobble=wobble)


def cylinder(name, radius, height, loc=(0, 0, 0), mat=None, rot=(0, 0, 0), verts=24, bevel=0.01, smooth=True, radius_top=None, origin="bottom", wobble=0.0, **_ignored):
    bm = bmesh.new()
    r2 = radius if radius_top is None else radius_top
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=verts, radius1=radius, radius2=r2, depth=height)
    if origin == "bottom":
        bmesh.ops.translate(bm, vec=Vector((0, 0, height / 2)), verts=bm.verts)
    o = _mesh_obj(name, bm)
    o.location = loc
    o.rotation_euler = [math.radians(a) for a in rot]
    return _finish(o, mat, bevel, smooth=smooth, wobble=wobble)


def cone(name, radius, height, loc=(0, 0, 0), mat=None, verts=24, rot=(0, 0, 0), smooth=False, **_ignored):
    return cylinder(name, radius, height, loc, mat, rot, verts, bevel=0.0, smooth=smooth, radius_top=0.0)


def sphere(name, radius, loc=(0, 0, 0), mat=None, segments=24, scale=(1, 1, 1), **_ignored):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=max(8, segments // 2), radius=radius)
    o = _mesh_obj(name, bm)
    o.location = loc
    o.scale = scale
    return _finish(o, mat, 0, smooth=True)


def gable_roof(name, width, depth, height, loc=(0, 0, 0), mat=None, overhang=0.25, thickness=0.12, rot=0, wobble=0.0, **_ignored):
    """Tejado a dos aguas. width = eje X (caída), depth = eje Y (cumbrera). loc = centro de la base del tejado."""
    w, d = width / 2 + overhang, depth / 2 + overhang
    bm = bmesh.new()
    v = [bm.verts.new(p) for p in [(-w, -d, 0), (w, -d, 0), (0, -d, height), (-w, d, 0), (w, d, 0), (0, d, height)]]
    for f in [(v[0], v[1], v[2]), (v[5], v[4], v[3]), (v[0], v[2], v[5], v[3]), (v[1], v[4], v[5], v[2]), (v[0], v[3], v[4], v[1])]:
        bm.faces.new(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _mesh_obj(name, bm)
    o.location = loc
    o.rotation_euler = (0, 0, math.radians(rot))
    if thickness:
        s = o.modifiers.new("Solid", "SOLIDIFY")
        s.thickness = thickness
        s.offset = 1
    return _finish(o, mat, 0.015, wobble=wobble)


def tiled_roof(name, width, depth, height, loc=(0, 0, 0), mat=None, overhang=0.3, rows=None, rot=0, wobble=0.012, **_ignored):
    """Tejado a dos aguas con hileras de tejas reales (geometría escalonada). Más detalle que gable_roof."""
    import math as _m
    half = width / 2 + overhang
    slope_len = _m.hypot(half, height)
    ang = _m.degrees(_m.atan2(height, half))
    rows = rows or max(4, int(slope_len / 0.32))
    step = slope_len / rows
    parts = []
    for side in (-1, 1):
        for r in range(rows):
            t = (r + 0.5) / rows
            x = side * half * (1 - t)
            z = height * t
            tile = box(f"{name}_s{side}_r{r}", (step * 1.25, depth + overhang * 2, 0.07), (x, 0, z), mat, rot=(0, side * ang, 0), bevel=0.02, wobble=wobble)
            parts.append(tile)
    parts.append(box(name + "_ridge", (0.22, depth + overhang * 2 + 0.05, 0.16), (0, 0, height + 0.02), mat, bevel=0.03))
    o = join(parts, name)
    o.location = loc
    o.rotation_euler = (0, 0, math.radians(rot))
    return o


def hip_roof(name, width, depth, height, loc=(0, 0, 0), mat=None, overhang=0.25, ridge=0.4, rot=0, **_ignored):
    """Tejado a cuatro aguas (ridge = fracción de la cumbrera respecto a depth)."""
    w, d = width / 2 + overhang, depth / 2 + overhang
    r = d * ridge
    bm = bmesh.new()
    v = [bm.verts.new(p) for p in [(-w, -d, 0), (w, -d, 0), (w, d, 0), (-w, d, 0), (0, -r, height), (0, r, height)]]
    for f in [(v[0], v[1], v[4]), (v[2], v[3], v[5]), (v[1], v[2], v[5], v[4]), (v[3], v[0], v[4], v[5]), (v[3], v[2], v[1], v[0])]:
        bm.faces.new(f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    o = _mesh_obj(name, bm)
    o.location = loc
    o.rotation_euler = (0, 0, math.radians(rot))
    return _finish(o, mat, 0.015)


def pyramid_roof(name, size, height, loc=(0, 0, 0), mat=None, overhang=0.2, **_ignored):
    return cone(name, (size / 2 + overhang) * math.sqrt(2), height, loc, mat, verts=4, rot=(0, 0, 45))


def beam(name, start, end, thickness=0.12, mat=None, wobble=0.0, **_ignored):
    """Viga recta entre dos puntos 3D."""
    a, b = Vector(start), Vector(end)
    vec = b - a
    o = box(name, (thickness, thickness, vec.length), (a + b) / 2, mat, bevel=0.01, wobble=wobble)
    o.rotation_mode = "QUATERNION"
    o.rotation_quaternion = vec.to_track_quat("Z", "Y")
    return o


def window(name, loc, width=0.6, height=0.8, facing="-Y", frame_mat=None, glass_mat=None, depth=0.08, mullions=True, **_ignored):
    """Ventana con marco y cristal sobre una fachada. facing = dirección hacia la que mira (+X,-X,+Y,-Y)."""
    rotz = {"-Y": 0, "+Y": 180, "+X": 90, "-X": -90}[facing]
    parts = []
    glass_mat = glass_mat or material("glass_warm", (1.0, 0.75, 0.35), rough=0.3, emission=(1.0, 0.6, 0.25), strength=2.5)
    frame_mat = frame_mat or material("dark_wood", (0.22, 0.13, 0.07), rough=0.8)
    g = box(name + "_glass", (width, depth * 0.5, height), (0, 0, 0), glass_mat, bevel=0)
    parts.append(g)
    t = 0.07
    for i, (sx, sz, px, pz) in enumerate([(width + t * 2, t, 0, height / 2 + t / 2), (width + t * 2, t, 0, -height / 2 - t / 2), (t, height, -width / 2 - t / 2, 0), (t, height, width / 2 + t / 2, 0)]):
        parts.append(box(f"{name}_f{i}", (sx, depth, sz), (px, -depth * 0.3, pz), frame_mat, bevel=0.01))
    if mullions:
        parts.append(box(name + "_mv", (t * 0.6, depth, height), (0, -depth * 0.3, 0), frame_mat, bevel=0))
        parts.append(box(name + "_mh", (width, depth, t * 0.6), (0, -depth * 0.3, 0), frame_mat, bevel=0))
    o = join(parts, name)
    o.location = loc
    o.rotation_euler = (0, 0, math.radians(rotz))
    return o


def door(name, loc, width=1.0, height=1.9, facing="-Y", mat=None, frame_mat=None, arch=True, **_ignored):
    rotz = {"-Y": 0, "+Y": 180, "+X": 90, "-X": -90}[facing]
    mat = mat or material("door_wood", (0.35, 0.2, 0.1), rough=0.8)
    frame_mat = frame_mat or material("dark_wood", (0.22, 0.13, 0.07), rough=0.8)
    parts = [box(name + "_panel", (width, 0.08, height), (0, 0, height / 2), mat, bevel=0.01)]
    for i in range(1, 4):
        parts.append(box(f"{name}_plank{i}", (0.015, 0.1, height * 0.95), (-width / 2 + i * width / 4, -0.01, height / 2), frame_mat, bevel=0))
    parts.append(box(name + "_fl", (0.1, 0.14, height), (-width / 2 - 0.05, 0, height / 2), frame_mat))
    parts.append(box(name + "_fr", (0.1, 0.14, height), (width / 2 + 0.05, 0, height / 2), frame_mat))
    parts.append(box(name + "_ft", (width + 0.3, 0.14, 0.12), (0, 0, height + 0.06), frame_mat))
    if arch:
        a = cylinder(name + "_arch", width / 2, 0.08, (0, 0, height), mat, rot=(90, 0, 0), verts=16, origin="center", smooth=False)
        parts.append(a)
    o = join(parts, name)
    o.location = loc
    o.rotation_euler = (0, 0, math.radians(rotz))
    return o


def stone_ring(name, radius, height, loc=(0, 0, 0), mat=None, stones=14, stone_size=0.35, **_ignored):
    """Anillo de piedras irregulares (pozos, fuentes, torres)."""
    parts = []
    for i in range(stones):
        a = 2 * math.pi * i / stones
        s = stone_size * random.uniform(0.85, 1.15)
        st = box(f"{name}_{i}", (s * 1.4, s, height * random.uniform(0.9, 1.05)), (math.cos(a) * radius, math.sin(a) * radius, 0), mat, rot=(0, 0, math.degrees(a) + 90), bevel=0.04, wobble=0.02, origin="bottom")
        parts.append(st)
    o = join(parts, name)
    o.location = loc
    return o


def tree(name, loc=(0, 0, 0), height=3.0, trunk_mat=None, leaf_mat=None, style="round", **_ignored):
    trunk_mat = trunk_mat or material("bark", (0.3, 0.18, 0.1))
    leaf_mat = leaf_mat or material("leaves", (0.25, 0.55, 0.2), rough=0.9)
    parts = [cylinder(name + "_trunk", height * 0.06, height * 0.5, (0, 0, 0), trunk_mat, verts=8, radius_top=height * 0.04, smooth=False)]
    if style == "pine":
        for i in range(3):
            parts.append(cone(f"{name}_c{i}", height * (0.32 - i * 0.07), height * 0.4, (0, 0, height * (0.3 + i * 0.2)), leaf_mat, verts=10))
    else:
        for i in range(4):
            r = height * random.uniform(0.18, 0.26)
            parts.append(sphere(f"{name}_b{i}", r, (random.uniform(-0.3, 0.3) * height * 0.3, random.uniform(-0.3, 0.3) * height * 0.3, height * random.uniform(0.6, 0.8)), leaf_mat, segments=12))
    o = join(parts, name)
    o.location = loc
    return o


# ───────────────────────── utilidades ─────────────────────────
def jitter(obj, amount=0.02, **_ignored):
    """Desplaza ligeramente los vértices para un aspecto artesanal (estilo stylized)."""
    for v in obj.data.vertices:
        v.co += Vector((random.uniform(-amount, amount), random.uniform(-amount, amount), random.uniform(-amount, amount)))


def array(fn, count, step, *args, **kw):
    """Llama fn(i, pos) count veces desplazando pos según step (x,y,z). Devuelve la lista."""
    out = []
    for i in range(count):
        out.append(fn(i, Vector(step) * i))
    return out


def apply_mods(obj):
    bpy.context.view_layer.objects.active = obj
    for m in list(obj.modifiers):
        try:
            with bpy.context.temp_override(object=obj, active_object=obj):
                bpy.ops.object.modifier_apply(modifier=m.name)
        except Exception:
            try:
                bpy.ops.object.modifier_apply(modifier=m.name)
            except Exception:
                obj.modifiers.remove(m)


def join(objs, name):
    objs = [o for o in objs if o is not None]
    for o in objs:
        apply_mods(o)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name
    # el origen en (0,0,0) local para poder recolocar el conjunto
    return o


def group(name, objs):
    """Agrupa objetos bajo un vacío (para escenas como ciudades)."""
    e = bpy.data.objects.new(name, None)
    _link(e)
    for o in objs:
        o.parent = e
    return e


def ground(size=20, mat=None, loc=(0, 0, 0), **_ignored):
    mat = mat or material("grass", (0.3, 0.5, 0.2), rough=0.95)
    return box("ground", (size, size, 0.2), (loc[0], loc[1], loc[2] - 0.1), mat, bevel=0.05)
