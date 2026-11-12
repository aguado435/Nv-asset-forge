"""
NV Asset Forge - puente con Blender (se ejecuta en local, en segundo plano).

    blender -b --factory-startup -P nvf_blender.py -- trabajo.json

Operaciones:
  process -> limpia el modelo, lo pone a escala real con el pivote en la base,
             genera LODs y exporta FBX (Unity/Unreal) + GLB (Godot/web) + OBJ.
  render  -> render de calidad: sprite sheet de N direcciones con fondo
             transparente y una imagen "hero" en alta resolución.
Compatible con Blender 3.6, 4.x y 5.x.
"""
import json
import math
import os
import sys
import time

import bpy
import bmesh
from mathutils import Matrix, Vector

try:
    import numpy as np
except Exception:  # Blender siempre trae numpy, pero por si acaso
    np = None


def log(msg):
    print("NVF:" + str(msg), flush=True)


def read_args():
    argv = sys.argv
    path = argv[argv.index("--") + 1] if "--" in argv else argv[-1]
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ───────────────────────── escena ─────────────────────────
def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def set_active(obj):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def import_model(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif ext == ".obj":
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=path)
        else:
            bpy.ops.import_scene.obj(filepath=path)
    else:
        raise RuntimeError("Formato no soportado: " + ext)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("El archivo no contiene mallas")
    return meshes


def join_meshes(meshes, name):
    # 1) hornear la transformación de mundo en cada malla y quitar jerarquías
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        if o.data.users > 1:  # mallas instanciadas: hacerlas únicas antes de transformar
            o.data = o.data.copy()
        o.data.transform(mw)
        o.matrix_world = Matrix.Identity(4)
    for o in list(bpy.data.objects):
        if o.type != "MESH":
            bpy.data.objects.remove(o, do_unlink=True)
    bpy.context.view_layer.update()
    # 2) unir en un solo objeto (conserva materiales y UVs)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in bpy.context.scene.objects:
        o.select_set(o.type == "MESH")
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    obj.data.name = name + "_mesh"
    return obj


def tri_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def clean_mesh(obj, merge_dist):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge_dist)
    loose = [v for v in bm.verts if not v.link_edges]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return before - len(obj.data.vertices)


def shade_smooth(obj, angle_deg=40):
    set_active(obj)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle_deg))
        return
    except Exception:
        pass
    bpy.ops.object.shade_smooth()
    if hasattr(obj.data, "use_auto_smooth"):
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(angle_deg)


def bounds(obj):
    """Caja envolvente leída de los vértices (bound_box puede estar desactualizada)."""
    me = obj.data
    n = len(me.vertices)
    if np is not None:
        co = np.empty(n * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        co = co.reshape(n, 3)
        lo, hi = co.min(axis=0), co.max(axis=0)
        mn, mx = Vector(lo.tolist()), Vector(hi.tolist())
    else:
        xs = [v.co for v in me.vertices]
        mn = Vector((min(v.x for v in xs), min(v.y for v in xs), min(v.z for v in xs)))
        mx = Vector((max(v.x for v in xs), max(v.y for v in xs), max(v.z for v in xs)))
    mw = obj.matrix_world
    return mw @ mn, mw @ mx


def normalize(obj, height=None, pivot="base"):
    """Escala a 'height' metros (si se indica) y pone el pivote en la base o centro."""
    mn, mx = bounds(obj)
    size = mx - mn
    if height and size.z > 1e-6:
        s = float(height) / size.z
        obj.data.transform(Matrix.Scale(s, 4))
        obj.data.update()
    mn, mx = bounds(obj)
    c = (mn + mx) / 2
    off = Vector((c.x, c.y, mn.z if pivot == "base" else c.z))
    obj.data.transform(Matrix.Translation(-off))
    obj.data.update()
    obj.location = (0, 0, 0)
    mn, mx = bounds(obj)
    return mx - mn


def decimate(obj, target_tris):
    tris = tri_count(obj)
    if not target_tris or tris <= target_tris:
        return tris
    set_active(obj)
    mod = obj.modifiers.new("Decimate", "DECIMATE")
    mod.ratio = max(0.01, min(1.0, target_tris / float(tris)))
    mod.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=mod.name)
    return tri_count(obj)


def duplicate(obj, name):
    new = obj.copy()
    new.data = obj.data.copy()
    new.name = name
    new.data.name = name + "_mesh"
    bpy.context.scene.collection.objects.link(new)
    return new


# ───────────────────────── process ─────────────────────────
def op_process(a):
    out = a["outDir"]
    name = a.get("name", "asset")
    reset_scene()
    log("Importando " + os.path.basename(a["input"]))
    meshes = import_model(a["input"])
    obj = join_meshes(meshes, name)
    t0 = tri_count(obj)
    removed = clean_mesh(obj, float(a.get("mergeDistance", 0.0001)))
    log("Malla limpia: %d triángulos, %d vértices duplicados eliminados" % (t0, removed))
    size = normalize(obj, a.get("height") or None, a.get("pivot", "base"))
    log("Tamaño final: %.2f × %.2f × %.2f m" % (size.x, size.y, size.z))
    if a.get("smooth", True):
        shade_smooth(obj)
    tris = decimate(obj, int(a.get("maxTris") or 0))
    log("LOD0: %d triángulos" % tris)

    lods = [obj]
    ratios = [r for r in a.get("lods", [0.5, 0.25]) if 0 < r < 1]
    obj.name = name + "_LOD0"
    for i, r in enumerate(ratios, start=1):
        lod = duplicate(obj, "%s_LOD%d" % (name, i))
        decimate(lod, max(50, int(tris * r)))
        lods.append(lod)
        log("LOD%d: %d triángulos" % (i, tri_count(lod)))

    # grupo raíz para que Unity cree el LODGroup automáticamente
    root = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(root)
    for l in lods:
        l.parent = root

    report = {"triangles": [tri_count(l) for l in lods], "size_m": [round(size.x, 4), round(size.y, 4), round(size.z, 4)], "files": []}
    formats = a.get("formats", ["fbx", "glb", "obj"])

    if "fbx" in formats:
        p = os.path.join(out, name + ".fbx")
        bpy.ops.export_scene.fbx(filepath=p, use_selection=False, apply_scale_options="FBX_SCALE_ALL",
                                 axis_forward="-Z", axis_up="Y", path_mode="COPY", embed_textures=True,
                                 mesh_smooth_type="FACE", add_leaf_bones=False, bake_anim=False)
        report["files"].append(os.path.basename(p)); log("Exportado FBX con %d LODs" % len(lods))

    # GLB y OBJ: solo LOD0 (lo normal en Godot/web)
    for o in bpy.context.view_layer.objects:
        o.select_set(o == lods[0])
    bpy.context.view_layer.objects.active = lods[0]
    if "glb" in formats:
        p = os.path.join(out, name + "_optimized.glb")
        bpy.ops.export_scene.gltf(filepath=p, export_format="GLB", use_selection=True)
        report["files"].append(os.path.basename(p)); log("Exportado GLB optimizado")
    if "obj" in formats:
        p = os.path.join(out, name + ".obj")
        try:
            if hasattr(bpy.ops.wm, "obj_export"):
                bpy.ops.wm.obj_export(filepath=p, export_selected_objects=True, path_mode="COPY")
            else:
                bpy.ops.export_scene.obj(filepath=p, use_selection=True, path_mode="COPY")
            report["files"].append(os.path.basename(p)); log("Exportado OBJ")
        except Exception as e:
            log("Aviso: OBJ no exportado (%s)" % e)
    if a.get("saveBlend", True):
        p = os.path.join(out, name + ".blend")
        bpy.ops.wm.save_as_mainfile(filepath=p, compress=True)
        report["files"].append(os.path.basename(p)); log("Guardado .blend editable")
    return report


# ───────────────────────── render ─────────────────────────
def setup_render(scene, a, size):
    engine = a.get("engine", "eevee")
    q = a.get("quality", "normal")
    samples = {"draft": 16, "normal": 64, "high": 256}.get(q, 64)
    if engine == "cycles":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        if a.get("gpu", True):
            try:
                prefs = bpy.context.preferences.addons["cycles"].preferences
                for dev in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
                    try:
                        prefs.compute_device_type = dev
                        prefs.get_devices()
                        if any(d.type == dev for d in prefs.devices):
                            for d in prefs.devices:
                                d.use = True
                            scene.cycles.device = "GPU"
                            log("Cycles en GPU (%s)" % dev)
                            break
                    except Exception:
                        continue
            except Exception:
                pass
    else:
        ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in ids else "BLENDER_EEVEE"
        try:
            scene.eevee.taa_render_samples = samples
        except Exception:
            pass
    scene.render.film_transparent = True
    scene.render.resolution_x = size
    scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    try:
        scene.view_settings.view_transform = "Standard"  # colores fieles, sin el lavado de AgX/Filmic
    except Exception:
        pass
    if a.get("pixel"):
        scene.render.filter_size = 0.0


def add_light(name, kind, energy, rot_deg, color=(1, 1, 1)):
    data = bpy.data.lights.new(name, kind)
    data.energy = energy
    data.color = color
    if kind == "SUN":
        data.angle = math.radians(8)
    o = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(o)
    o.rotation_euler = [math.radians(r) for r in rot_deg]
    return o


def setup_world(scene, strength):
    w = bpy.data.worlds.new("NVF_World")
    scene.world = w
    w.use_nodes = True
    bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is None:
        bg = w.node_tree.nodes.new("ShaderNodeBackground")
        outn = next((n for n in w.node_tree.nodes if n.type == "OUTPUT_WORLD"), None) or w.node_tree.nodes.new("ShaderNodeOutputWorld")
        w.node_tree.links.new(bg.outputs[0], outn.inputs[0])
    bg.inputs[0].default_value = (0.55, 0.57, 0.62, 1)
    bg.inputs[1].default_value = strength


def image_pixels(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    arr = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(arr)
    bpy.data.images.remove(img)
    return arr.reshape(h, w, 4)


def save_pixels(arr, path):
    h, w = arr.shape[:2]
    img = bpy.data.images.new("nvf_sheet", w, h, alpha=True)
    img.pixels.foreach_set(arr.ravel())
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


def op_render(a):
    out = a["outDir"]
    name = a.get("name", "asset")
    dirs = int(a.get("directions", 8))
    size = int(a.get("size", 256))
    elev = math.radians(float(a.get("elevation", 30)))
    reset_scene()
    scene = bpy.context.scene
    log("Importando " + os.path.basename(a["input"]))
    obj = join_meshes(import_model(a["input"]), name)
    normalize(obj, None, "center")
    if a.get("smooth", True):
        shade_smooth(obj)
    pivot = bpy.data.objects.new("pivot", None)
    scene.collection.objects.link(pivot)
    obj.parent = pivot
    # radio de la esfera envolvente para encuadrar sin cortar en ninguna dirección
    radius = max((Vector(v.co)).length for v in obj.data.vertices) * 1.04

    cam_data = bpy.data.cameras.new("cam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = radius * 2
    cam_data.clip_end = radius * 20
    cam = bpy.data.objects.new("cam", cam_data)
    scene.collection.objects.link(cam)
    dist = radius * 6
    cam.location = (0, -math.cos(elev) * dist, math.sin(elev) * dist)
    track = cam.constraints.new("TRACK_TO")
    track.target = pivot
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    scene.camera = cam

    k = float(a.get("light", 1.0))
    add_light("key", "SUN", 3.2 * k, (50, 0, -35))
    add_light("fill", "SUN", 1.0 * k, (60, 0, 140), (0.85, 0.9, 1.0))
    add_light("rim", "SUN", 2.2 * k, (110, 0, 180), (1.0, 0.95, 0.9))
    setup_world(scene, 0.6 * k)
    setup_render(scene, a, size)

    tmp = os.path.join(out, "_frames")
    os.makedirs(tmp, exist_ok=True)
    cols = min(dirs, 8)
    rows = int(math.ceil(dirs / float(cols)))
    sheet = np.zeros((rows * size, cols * size, 4), dtype=np.float32) if np is not None else None
    frames = []
    t = time.time()
    for i in range(dirs):
        pivot.rotation_euler = (0, 0, -i * 2 * math.pi / dirs)
        fp = os.path.join(tmp, "%s_dir%02d.png" % (name, i))
        scene.render.filepath = fp
        bpy.ops.render.render(write_still=True)
        frames.append(fp)
        log("Render %d/%d" % (i + 1, dirs))
        if sheet is not None:
            px = image_pixels(fp)
            r, c = divmod(i, cols)
            y0 = (rows - 1 - r) * size  # las imágenes de Blender empiezan abajo
            sheet[y0:y0 + size, c * size:(c + 1) * size] = px
    files = []
    tag = "%s_blender_%ddir_%dpx_e%d" % (name, dirs, size, int(round(math.degrees(elev))))
    if sheet is not None:
        p = os.path.join(out, tag + ".png")
        save_pixels(sheet, p)
        files.append(os.path.basename(p))
        log("Sprite sheet %dx%d listo en %.1fs" % (cols * size, rows * size, time.time() - t))
    if a.get("hero", True):
        hs = int(a.get("heroSize", 1024))
        scene.render.resolution_x = scene.render.resolution_y = hs
        pivot.rotation_euler = (0, 0, math.radians(-35))
        p = os.path.join(out, name + "_blender_hero.png")
        scene.render.filepath = p
        bpy.ops.render.render(write_still=True)
        files.append(os.path.basename(p))
        log("Render hero %dpx listo" % hs)
    if a.get("keepFrames"):
        files += [os.path.join("_frames", os.path.basename(f)) for f in frames]
    else:
        for f in frames:
            try:
                os.remove(f)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass
    return {"files": files, "directions": dirs, "size": size}


# ───────────────────────── build (modelado procedural) ─────────────────────────
def frame_camera(scene, objs, size, elev_deg=28, azim_deg=-38, lens=50, pad=1.08):
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (mn + mx) / 2
    radius = max((p - center).length for p in pts)
    cam_data = bpy.data.cameras.new("hero_cam")
    cam_data.lens = lens
    cam_data.sensor_width = 36
    fov = 2 * math.atan(18.0 / lens)
    dist = radius / math.sin(fov / 2) * pad
    e, az = math.radians(elev_deg), math.radians(azim_deg)
    direction = Vector((math.sin(az) * math.cos(e), -math.cos(az) * math.cos(e), math.sin(e)))
    cam = bpy.data.objects.new("hero_cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = center + direction * dist
    cam_data.clip_end = dist * 4
    target = bpy.data.objects.new("hero_target", None)
    scene.collection.objects.link(target)
    target.location = center
    tr = cam.constraints.new("TRACK_TO")
    tr.target = target
    tr.track_axis = "TRACK_NEGATIVE_Z"
    tr.up_axis = "UP_Y"
    scene.camera = cam
    return center, radius


def studio_lights(scene, strength=1.0):
    add_light("key", "SUN", 3.5 * strength, (48, 0, -40), (1.0, 0.96, 0.9))
    add_light("fill", "SUN", 0.9 * strength, (65, 0, 130), (0.8, 0.88, 1.0))
    add_light("rim", "SUN", 2.0 * strength, (115, 0, 175), (1.0, 0.92, 0.85))
    w = bpy.data.worlds.new("NVF_Sky")
    scene.world = w
    w.use_nodes = True
    bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is None:
        bg = w.node_tree.nodes.new("ShaderNodeBackground")
        outn = next((n for n in w.node_tree.nodes if n.type == "OUTPUT_WORLD"), None) or w.node_tree.nodes.new("ShaderNodeOutputWorld")
        w.node_tree.links.new(bg.outputs[0], outn.inputs[0])
    bg.inputs[0].default_value = (0.62, 0.72, 0.85, 1)
    bg.inputs[1].default_value = 0.8 * strength


def op_build(a):
    out = a["outDir"]
    name = a.get("name", "asset")
    reset_scene()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import importlib
    import nvf_kit as kit
    importlib.reload(kit)
    kit._MATS.clear()
    kit.TEXTURES.clear()
    kit.TEXTURES.update(a.get("textures", {}))
    ns = {k: getattr(kit, k) for k in dir(kit) if not k.startswith("_")}
    ns.update({"math": math, "random": kit.random, "Vector": Vector, "bpy": bpy, "TEXTURES": kit.TEXTURES})
    with open(a["script"], "r", encoding="utf-8") as f:
        code = f.read()
    log("Ejecutando el script de modelado (%d líneas)" % code.count("\n"))
    exec(compile(code, "asset_script.py", "exec"), ns)
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("El script no creó ninguna malla")
    for o in meshes:
        kit.apply_mods(o)
    # evita caras coplanares superpuestas (sombras negras en Cycles/Eevee):
    # cada pieza grande se escala 1-4 mm alrededor de su centro
    rnd = kit.random.Random(3)
    for i, o in enumerate(meshes):
        dims = o.dimensions
        if max(dims) < 0.25:
            continue
        mw = o.matrix_world.copy()
        center = sum((Vector(c) for c in o.bound_box), Vector()) / 8
        k = 1.0 + (0.0005 + 0.0007 * (i % 7)) / max(0.5, max(dims))
        o.data.transform(Matrix.Translation(center) @ Matrix.Scale(k, 4) @ Matrix.Translation(-center))
    tris = sum(tri_count(o) for o in meshes)
    log("Modelo: %d objetos, %d triángulos" % (len(meshes), tris))
    files = []
    p = os.path.join(out, "model.glb")
    bpy.ops.export_scene.gltf(filepath=p, export_format="GLB", use_selection=False)
    files.append("model.glb")
    p = os.path.join(out, name + ".fbx")
    bpy.ops.export_scene.fbx(filepath=p, use_selection=False, apply_scale_options="FBX_SCALE_ALL", axis_forward="-Z", axis_up="Y",
                             path_mode="COPY", embed_textures=True, mesh_smooth_type="FACE", add_leaf_bones=False, bake_anim=False)
    files.append(name + ".fbx")
    scene = bpy.context.scene
    studio_lights(scene, float(a.get("light", 1.0)))
    frame_camera(scene, meshes, int(a.get("heroSize", 1024)), float(a.get("elevation", 28)), float(a.get("azimuth", -38)))
    setup_render(scene, a, int(a.get("heroSize", 1024)))
    scene.render.film_transparent = bool(a.get("transparent", True))
    p = os.path.join(out, "render_hero.png")
    scene.render.filepath = p
    log("Renderizando vista hero…")
    bpy.ops.render.render(write_still=True)
    files.append("render_hero.png")
    p = os.path.join(out, name + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=p, compress=True)
    files.append(name + ".blend")
    return {"files": files, "triangles": tris, "objects": len(meshes)}


def main():
    a = read_args()
    log("Blender %s" % bpy.app.version_string)
    try:
        op = a.get("op")
        res = op_process(a) if op == "process" else op_build(a) if op == "build" else op_render(a)
        print("NVF_RESULT:" + json.dumps(res), flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()
        import traceback as _tb
        tb = [l for l in _tb.format_exc().splitlines() if "asset_script.py" in l or "Error" in l][-4:]
        print("NVF_ERROR:" + str(e) + (" || " + " | ".join(x.strip() for x in tb) if tb else ""), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
