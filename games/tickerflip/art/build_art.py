"""Pre-rendered art for Tickerflip, built in Blender 5.2 (Cycles, CPU).
Run: /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup -P art/build_art.py -- [tile|flap|frame|lamp|hall|all]
Outputs go to assets/art/. Depth objects (the flap cell, the brass frame, the lamps, the lacquered hall) are
rendered here and used as sprites; the page draws only flat colour and text on top of them."""
import bpy, bmesh, math, sys, os
import numpy as np
from mathutils import Vector

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "art")
os.makedirs(OUT, exist_ok=True)
what = (sys.argv[sys.argv.index("--") + 1:] or ["all"])[0] if "--" in sys.argv else "all"
sub = (sys.argv[sys.argv.index("--") + 2:] or ["all"])[0] if "--" in sys.argv else "all"


def reset(res, ortho=None, transparent=True, samples=48):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = transparent
    sc.view_settings.view_transform = "Standard"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA"
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam); sc.camera = cam
    if ortho:
        cam.data.type = "ORTHO"; cam.data.ortho_scale = ortho * max(1.0, res[0] / res[1])  # ortho_scale is the longer side
    return sc, cam


def world(sc, color=(0.2, 0.2, 0.2), strength=1.0):
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    bg = w.node_tree.nodes["Background"]; bg.inputs[0].default_value = (*color, 1); bg.inputs[1].default_value = strength


def mat(name, color, rough=0.5, metal=0.0, emit=None, emit_strength=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1); b.inputs["Emission Strength"].default_value = emit_strength
    return m


def box(name, size, loc, m, bevel=0.0, seg=3, rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name); ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts: v.co.x *= size[0]; v.co.y *= size[1]; v.co.z *= size[2]
    bm.to_mesh(me); bm.free()
    ob.location = loc; ob.rotation_euler = rot
    ob.data.materials.append(m)
    if bevel:
        bv = ob.modifiers.new("bv", "BEVEL"); bv.width = bevel; bv.segments = seg; bv.limit_method = "NONE"
        # scale is baked so the bevel is in world units
    for p in ob.data.polygons: p.use_smooth = True
    return ob


def bake_scale(ob):
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects: o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)


def light(kind, loc, energy, size=1.0, target=None, spot=None, color=(1, 1, 1)):
    ld = bpy.data.lights.new("l", kind); ld.energy = energy; ld.color = color
    if kind == "AREA": ld.size = size
    if kind == "SPOT": ld.spot_size = spot or math.radians(60); ld.spot_blend = 0.8; ld.shadow_soft_size = size
    ob = bpy.data.objects.new("l", ld); bpy.context.scene.collection.objects.link(ob); ob.location = loc
    if target is not None:
        d = Vector(target) - Vector(loc); ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def render(path):
    sc = bpy.context.scene; sc.render.filepath = path; bpy.ops.render.render(write_still=True); print("wrote", path)


def normalise(path, target=0.96, pct=88):
    """Rescale a grey shading sprite so its lit areas sit at `target`; the browser multiplies it over flat colour."""
    img = bpy.data.images.load(path); w, h = img.size
    a = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)
    cov = a[..., 3] > 0.5
    k = target / max(1e-4, np.percentile(a[..., :3].mean(-1)[cov], pct))
    a[..., :3] = np.clip(a[..., :3] * k, 0, 1)
    img.pixels = a.ravel().tolist(); img.filepath_raw = path; img.file_format = "PNG"; img.save(); bpy.data.images.remove(img)


# ---------------------------------------------------------------- the flap cell (two cards, slot, pins)
def tile_scene(top_angle=0.0, only_bottom=False, W=0.8):
    white = mat("card", (0.9, 0.9, 0.9), rough=0.55)
    dark = mat("slot", (0.005, 0.005, 0.005), rough=0.8)
    pin = mat("pin", (0.8, 0.8, 0.8), rough=0.3, metal=1.0)
    t = 0.05
    top = box("top", (W - 0.06, t, 0.47), (0, 0, 0.0), white, bevel=0.03)
    for v in top.data.vertices: v.co.z += 0.02 + 0.235
    bot = box("bot", (W - 0.06, t, 0.47), (0, 0, -0.255), white, bevel=0.03)
    slot = box("slotbar", (W, 0.02, 0.05), (0, 0.04, 0), dark)
    back = box("back", (W + 0.1, 0.01, 1.1), (0, 0.06, 0), dark)
    for sgn in (-1, 1):
        p = bpy.data.objects.new("pin", bpy.data.meshes.new("pin")); bpy.context.scene.collection.objects.link(p)
        bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.028, radius2=0.028, depth=0.07); bm.to_mesh(p.data); bm.free()
        p.rotation_euler = (math.radians(90), 0, 0); p.location = (sgn * (W / 2 - 0.035), -0.005, 0); p.data.materials.append(pin)
    top.rotation_euler = (math.radians(top_angle), 0, 0)
    return top, bot


def do_tile():
    sc, cam = reset((320, 400), ortho=1.08)
    world(sc, (0.55, 0.55, 0.55), 0.9)
    tile_scene()
    cam.location = (0, -5, 0); cam.rotation_euler = (math.radians(90), 0, 0)
    light("AREA", (-1.2, -3, 2.4), 260, size=3, target=(0, 0, 0))
    render(os.path.join(OUT, "tile-shade.png")); normalise(os.path.join(OUT, "tile-shade.png"))


def do_flap():
    """Face-on shading of one flap card at six fall angles (0, 16, 30, 50, 72, 86 degrees).
    The page squashes the flap on held frames; this sheet is the light on the card at each angle
    (brighter when it faces the lamp, darker as it turns away), multiplied over the flat face."""
    angles = [0, 16, 30, 50, 72, 86]
    frames = []
    for i, ang in enumerate(angles):
        sc, cam = reset((320, 200), ortho=0.5, samples=48)
        world(sc, (0.05, 0.05, 0.05), 0.5)
        white = mat("card", (0.9, 0.9, 0.9), rough=0.5)
        box("card", (0.8, 0.05, 0.5), (0, 0, 0), white, bevel=0.035)
        cam.location = (0, -5, 0); cam.rotation_euler = (math.radians(90), 0, 0)
        # the lamp stays put; the card turns away from it, so the light sweeps down the face
        el = math.radians(8 + ang * 0.75)
        light("AREA", (0, -3 * math.cos(el), 3 * math.sin(el)), 190, size=2.5, target=(0, 0, 0))
        p = os.path.join("/tmp", f"flapf_{i}.png"); render(p); frames.append(p)
    imgs = [bpy.data.images.load(p) for p in frames]
    w, h = imgs[0].size
    sheet = np.zeros((h, w * len(imgs), 4), dtype=np.float32)
    arrs = [np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4) for im in imgs]
    ref = np.percentile(arrs[0][..., :3].mean(-1)[arrs[0][..., 3] > 0.5], 80)
    for i, a in enumerate(arrs):
        a[..., :3] = np.clip(a[..., :3] / ref * 0.97, 0, 1)
        sheet[:, i * w:(i + 1) * w] = a
    out = bpy.data.images.new("sheet", w * len(imgs), h, alpha=True); out.pixels = sheet.ravel().tolist()
    out.filepath_raw = os.path.join(OUT, "flap-shadow.png"); out.file_format = "PNG"; out.save()


# ---------------------------------------------------------------- brass frame, 9-slice
def brass_world(sc):
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    nt = w.node_tree; n = nt.nodes
    for x in list(n): n.remove(x)
    tc = n.new("ShaderNodeTexCoord"); sep = n.new("ShaderNodeSeparateXYZ"); ramp = n.new("ShaderNodeValToRGB"); bg = n.new("ShaderNodeBackground"); out = n.new("ShaderNodeOutputWorld")
    nt.links.new(tc.outputs["Window" if False else "Generated"], sep.inputs[0]) if False else None
    mp = n.new("ShaderNodeMapping")
    nt.links.new(tc.outputs["Normal" if False else "Window"], sep.inputs[0])
    # reflection-vector driven studio gradient: warm light above, dark floor
    geo = n.new("ShaderNodeNewGeometry")
    nt.links.new(geo.outputs["Incoming"], sep.inputs[0])
    ramp.color_ramp.elements[0].position = 0.2; ramp.color_ramp.elements[0].color = (0.02, 0.012, 0.008, 1)
    ramp.color_ramp.elements[1].position = 0.85; ramp.color_ramp.elements[1].color = (1.0, 0.82, 0.55, 1)
    nt.links.new(sep.outputs["Z"], ramp.inputs[0]); nt.links.new(ramp.outputs[0], bg.inputs[0]); bg.inputs[1].default_value = 3.0
    nt.links.new(bg.outputs[0], out.inputs[0])


def do_frame():
    S = 384
    sc, cam = reset((S, S), ortho=2.0, samples=64)
    brass_world(sc)
    brass = mat("brass", (0.62, 0.44, 0.20), rough=0.42, metal=1.0)
    brass_lo = mat("brass2", (0.45, 0.30, 0.10), rough=0.4, metal=1.0)
    R = 1.0; bar = 0.22
    # outer bars with a rounded bevel, plus an inner lip, so the ring reads as a cast moulding
    for nm, size, loc in (("t", (2 * R, bar, 0.22), (0, 0, R - bar / 2)), ("b", (2 * R, bar, 0.22), (0, 0, -R + bar / 2)),
                          ("l", (bar, 0.0 + 0.22, 2 * R - 2 * bar), (-R + bar / 2, 0, 0)), ("r", (bar, 0.22, 2 * R - 2 * bar), (R - bar / 2, 0, 0))):
        if nm in "tb": ob = box(nm, (2 * R, 0.22, bar), (0, 0, loc[2]), brass, bevel=0.07, seg=4)
        else: ob = box(nm, (bar, 0.22, 2 * R - 2 * bar), (loc[0], 0, 0), brass, bevel=0.07, seg=4)
    inner = 0.07
    for nm, size, loc in (("it", (2 * (R - bar) + 0.02, 0.1, inner), (0, -0.07, R - bar - inner / 2)), ("ib", (2 * (R - bar) + 0.02, 0.1, inner), (0, -0.07, -(R - bar) + inner / 2))):
        box(nm, size, loc, brass_lo, bevel=0.02)
    for nm, x in (("il", -(R - bar) + inner / 2), ("ir", (R - bar) - inner / 2)):
        box(nm, (inner, 0.1, 2 * (R - bar) - 2 * inner), (x, -0.07, 0), brass_lo, bevel=0.02)
    for sx in (-1, 1):
        for sz in (-1, 1):
            bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=14, radius=0.07)
            me = bpy.data.meshes.new("riv"); bm.to_mesh(me); bm.free(); o = bpy.data.objects.new("riv", me)
            bpy.context.scene.collection.objects.link(o); o.location = (sx * (R - bar / 2), -0.14, sz * (R - bar / 2)); o.data.materials.append(brass)
            for p in me.polygons: p.use_smooth = True
    cam.location = (0, -6, 0); cam.rotation_euler = (math.radians(90), 0, 0)
    light("AREA", (-2, -4, 3), 400, size=3, target=(0, 0, 0))
    render(os.path.join(OUT, "frame.png"))


# ---------------------------------------------------------------- lamp and hall
def lamp(x, z, brass, glass, spot_target=None, spot_energy=2500):
    rod = box("rod", (0.02, 0.02, 0.5), (x, 0, z + 0.55), brass, bevel=0.004)
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=False, segments=40, radius1=0.2, radius2=0.04, depth=0.18)
    me = bpy.data.meshes.new("shade"); bm.to_mesh(me); bm.free()
    sh = bpy.data.objects.new("shade", me); bpy.context.scene.collection.objects.link(sh)
    sh.location = (x, 0, z + 0.2); sh.data.materials.append(brass)
    sol = sh.modifiers.new("s", "SOLIDIFY"); sol.thickness = 0.012
    for p in me.polygons: p.use_smooth = True
    bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=16, radius=0.085)
    me2 = bpy.data.meshes.new("bulb"); bm.to_mesh(me2); bm.free(); b = bpy.data.objects.new("bulb", me2)
    bpy.context.scene.collection.objects.link(b); b.location = (x, 0, z + 0.07); b.scale = (1, 1, 0.9); b.data.materials.append(glass)
    if spot_target:
        light("SPOT", (x, -0.05, z + 0.08), spot_energy, size=0.06, target=spot_target, spot=math.radians(95), color=(1.0, 0.72, 0.38))


def do_lamp():
    sc, cam = reset((360, 420), ortho=1.35, samples=64)
    brass_world(sc)
    brass = mat("brass", (0.80, 0.56, 0.22), rough=0.3, metal=1.0)
    glass = mat("bulb", (1, 0.8, 0.45), emit=(1.0, 0.72, 0.32), emit_strength=18)
    lamp(0, 0, brass, glass)
    cam.location = (0, -6, 0.32); cam.rotation_euler = (math.radians(90), 0, 0)
    light("AREA", (-2, -4, 2), 300, size=3, target=(0, 0, 0.2))
    render(os.path.join(OUT, "lamp.png"))


def hall(path, res, xs, ortho, cam_z, rail_z):
    sc, cam = reset(res, ortho=ortho, transparent=False, samples=96)
    world(sc, (0.01, 0.006, 0.004), 1.0)
    lac = mat("lacquer", (0.075, 0.032, 0.022), rough=0.22)
    lac2 = mat("lacquer2", (0.05, 0.022, 0.015), rough=0.3)
    brass = mat("brass", (0.80, 0.56, 0.22), rough=0.32, metal=1.0)
    glass = mat("bulb", (1, 0.8, 0.45), emit=(1.0, 0.72, 0.32), emit_strength=18)
    W = ortho * res[0] / res[1]
    top = cam_z + ortho / 2
    box("wall", (W + 1, 0.1, ortho + 1), (0, 0.3, cam_z), lac)
    # raised panel mouldings: vertical stiles
    step = 0.9
    n = int(W / step) + 2
    for i in range(-n, n + 1):
        box(f"stile{i}", (0.045, 0.05, ortho + 1), (i * step, 0.22, cam_z), lac2, bevel=0.012)
    # wainscot below the brass rail
    box("rail", (W + 1, 0.12, 0.07), (0, 0.15, rail_z), brass, bevel=0.02)
    box("dado", (W + 1, 0.12, ortho), (0, 0.2, rail_z - 0.04 - ortho / 2), lac2)
    for i in range(-n, n + 1):
        box(f"dp{i}", (step - 0.12, 0.05, 0.9), (i * step + step / 2, 0.12, rail_z - 0.5), lac, bevel=0.015)
    for x in xs:
        lamp(x, top - 0.78, brass, glass, spot_target=(x, 0.3, top - 2.6))
    box("topbar", (W + 1, 0.14, 0.1), (0, 0.1, top - 0.05), brass, bevel=0.02)
    cam.location = (0, -6, cam_z); cam.rotation_euler = (math.radians(90), 0, 0)
    light("AREA", (0, -4, top - 1), 60, size=4, target=(0, 0.3, cam_z), color=(1, 0.8, 0.55))
    render(path)


def do_hall(which="all"):
    if which in ("all", "portrait"): hall(os.path.join(OUT, "hall-portrait.png"), (780, 1688), [0.0], 8.4, 0, -3.1)
    if which in ("all", "wide"): hall(os.path.join(OUT, "hall-wide.png"), (1920, 1080), [-4.4, 0.0, 4.4], 6.0, 0, -2.1)


STEPS = {"tile": do_tile, "flap": do_flap, "frame": do_frame, "lamp": do_lamp, "hall": lambda: do_hall(sub)}
for name in (STEPS if what == "all" else [what]):
    STEPS[name]()
