"""Topfloor: the three brass objects of the game, rendered from Blender.

Run: Blender -b --factory-startup -P build_art.py -- <out_dir> [samples] [only]

  dial-base.png    the floor indicator: stepped brass bezel, enamel face, the odometer window (720 x 720)
  dial-needle.png  the needle with its shadow on the face, pointing straight up, same canvas (rotated by the page)
  dial-cap.png     the hub cap that sits over the needle, same canvas
  car-<n>.png      the lift car, thirteen door positions from shut (0) to open (12), 448 x 624 each
  call.png         the call button, up and pressed (2 x 240 x 240)

Everything printed on the dial (ticks, numerals, the tier bands) stays in the page as flat SVG: print is flat.
"""
import bpy, bmesh, math, sys, os
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/topfloor-art"
SAMPLES = int(argv[1]) if len(argv) > 1 else 96
ONLY = argv[2] if len(argv) > 2 else ""
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
try:
    pr = bpy.context.preferences.addons["cycles"].preferences
    pr.compute_device_type = "METAL"; pr.get_devices()
    for d in pr.devices: d.use = True
    sc.cycles.device = "GPU"
except Exception as e:
    print("gpu off", e); sc.cycles.device = "CPU"
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"


def mat(name, base, metal=0.0, rough=0.4, coat=0.0, emit=None, strength=0.0, alpha=1.0, trans=0.0):
    m = bpy.data.materials.new(name)
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if coat:
        b.inputs["Coat Weight"].default_value = coat; b.inputs["Coat Roughness"].default_value = 0.06
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1); b.inputs["Emission Strength"].default_value = strength
    if trans:
        b.inputs["Transmission Weight"].default_value = trans; b.inputs["IOR"].default_value = 1.45
    return m


BRASS = mat("brass", (0.78, 0.55, 0.22), 1.0, 0.24)
BRASS_SATIN = mat("brass_satin", (0.70, 0.49, 0.20), 1.0, 0.42)
BRASS_DK = mat("brass_dark", (0.36, 0.24, 0.09), 1.0, 0.45)
ENAMEL = mat("face_enamel", (0.012, 0.035, 0.042), 0.0, 0.62)
PIT = mat("pit", (0.004, 0.004, 0.004), 0.0, 0.8)
WALNUT = mat("walnut", (0.20, 0.085, 0.03), 0.0, 0.45, 0.3)
CREAM = mat("cream", (0.90, 0.78, 0.55), 0.0, 0.6)
LAMP = mat("lamp", (1, 0.9, 0.7), 0.0, 0.5, emit=(1.0, 0.82, 0.52), strength=14.0)
GLASS = mat("glass", (0.80, 0.93, 0.95), 0.0, 0.03, trans=1.0)
CARPET = mat("carpet", (0.33, 0.045, 0.04), 0.0, 0.9)
RED = mat("lens", (0.45, 0.05, 0.02), 0.0, 0.2, 0.8)
IVORY = mat("ivory", (0.92, 0.86, 0.70), 0.0, 0.4, 0.5)


def to_obj(name, bm, material, smooth=True, bevel=0.0, seg=2):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    ob.data.materials.append(material)
    if smooth:
        for p in me.polygons: p.use_smooth = True
    if bevel:
        m = ob.modifiers.new("bev", "BEVEL"); m.width = bevel; m.segments = seg; m.angle_limit = math.radians(35)
    return ob


def lathe(name, profile, material, steps=96, axis="Y"):
    """Spin a closed (r, h) profile. axis Y: the disc faces the camera (-Y is the front)."""
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0, z)) for r, z in profile]
    es = [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
    bmesh.ops.spin(bm, geom=vs + es, angle=2 * math.pi, steps=steps, axis=(0, 0, 1), cent=(0, 0, 0))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = to_obj(name, bm, material, True)
    if axis == "Y": ob.rotation_euler = (math.pi / 2, 0, 0)     # +Z of the profile now points at the camera (-Y)
    return ob


def box(name, size, loc, material, bevel=0.0, seg=2):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    ob = to_obj(name, bm, material, False, bevel, seg); ob.location = loc; return ob


def prism(name, pts, depth, loc, material, bevel=0.0):
    """Extrude an (x, z) outline along Y, centred on loc.y."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, -depth / 2, z)) for x, z in pts]
    f = bm.faces.new(vs)
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    bmesh.ops.translate(bm, vec=(0, depth, 0), verts=[v for v in r["geom"] if isinstance(v, bmesh.types.BMVert)])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = to_obj(name, bm, material, False, bevel); ob.location = loc; return ob


def area(name, loc, size, energy, color=(1, 1, 1), aim=(0, 0, 0)):
    ld = bpy.data.lights.new(name, "AREA"); ld.energy = energy; ld.size = size; ld.color = color
    o = bpy.data.objects.new(name, ld); sc.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


def camera(scale, w, h, z=0.0):
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = "ORTHO"; cam.data.ortho_scale = scale; cam.data.sensor_fit = "HORIZONTAL"
    cam.location = (0, -6, z); cam.rotation_euler = (math.pi / 2, 0, 0)
    sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = w, h, 100
    return cam


def world(strength=0.5):
    w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
    nt = w.node_tree; nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord"); sep = nt.nodes.new("ShaderNodeSeparateXYZ"); ramp = nt.nodes.new("ShaderNodeValToRGB")
    bg = nt.nodes.new("ShaderNodeBackground"); out = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0]); nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    cr = ramp.color_ramp      # a dusk sky for the brass to reflect: warm low, blue high
    cr.elements[0].position = 0.30; cr.elements[0].color = (0.10, 0.07, 0.08, 1)
    cr.elements[1].position = 0.75; cr.elements[1].color = (0.30, 0.38, 0.55, 1)
    mid = cr.elements.new(0.52); mid.color = (0.95, 0.55, 0.30, 1)
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"]); bg.inputs["Strength"].default_value = strength
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def render(name, only=None):
    """Render with only the given objects visible (None = all)."""
    for o in sc.objects:
        if o.type == "MESH": o.hide_render = only is not None and o not in only
    sc.render.filepath = f"{OUT}/{name}.png"
    bpy.ops.render.render(write_still=True)
    print("wrote", name, flush=True)


def clear():
    for o in list(sc.objects): bpy.data.objects.remove(o, do_unlink=True)


# ------------------------------------------------------------------ the dial
def dial():
    clear(); world(0.55)
    camera(2.2, 720, 720)
    # units: the bezel is 1.0 in radius; depth along -Y toward the camera. profile is (radius, height toward camera)
    bezel = lathe("bezel", [(0.865, 0.0), (1.0, 0.0), (1.0, 0.07), (0.985, 0.10), (0.955, 0.10), (0.945, 0.135), (0.915, 0.15), (0.895, 0.135), (0.885, 0.085), (0.865, 0.07)], BRASS)
    step = lathe("bezel_step", [(0.84, 0.0), (0.87, 0.0), (0.87, 0.06), (0.84, 0.045)], BRASS_DK)
    face = lathe("face", [(0.0, 0.0), (0.85, 0.0), (0.85, 0.02), (0.0, 0.02)], ENAMEL)
    for k in range(8):
        a = math.radians(22.5 + k * 45)
        s = lathe(f"screw{k}", [(0.0, 0.10), (0.022, 0.10), (0.022, 0.112), (0.014, 0.118), (0.0, 0.118)], BRASS_DK, steps=20)
        s.location = (0.97 * math.cos(a), 0, 0.97 * math.sin(a))
    # the odometer window: a brass frame around a dark pit, low on the face
    wy, ww, wh = -0.46, 0.56, 0.235
    box("win_frame", (ww + 0.07, 0.05, wh + 0.07), (0, -0.04, wy), BRASS, 0.012, 3)
    box("win_pit", (ww, 0.06, wh), (0, -0.045, wy), PIT)
    for dx in (-ww / 6, ww / 6):
        box(f"win_bar{dx}", (0.012, 0.06, wh), (dx, -0.05, wy), BRASS_DK)
    base = [o for o in sc.objects if o.type == "MESH"]
    # needle: a tapered brass blade from the hub to the scale, a short tail with a counterweight
    needle = prism("needle", [(-0.046, 0.0), (-0.010, 0.69), (0.0, 0.745), (0.010, 0.69), (0.046, 0.0), (0.030, -0.17), (-0.030, -0.17)], 0.012, (0, -0.075, 0), BRASS, 0.003)
    weight = lathe("needle_weight", [(0.0, 0.0), (0.062, 0.0), (0.062, 0.016), (0.0, 0.016)], BRASS_SATIN, steps=40); weight.location = (0, -0.07, -0.20)
    cap = lathe("cap", [(0.0, 0.0), (0.085, 0.0), (0.085, 0.03), (0.06, 0.055), (0.0, 0.062)], BRASS, steps=64); cap.location = (0, -0.085, 0)
    slot = box("cap_slot", (0.09, 0.01, 0.014), (0, -0.147, 0), BRASS_DK)
    catcher = lathe("catch", [(0.0, 0.0), (0.85, 0.0), (0.85, 0.001), (0.0, 0.001)], mat("catch", (0.02, 0.04, 0.05), 0, 1.0)); catcher.location = (0, -0.0205, 0)
    catcher.is_shadow_catcher = True
    area("key", (-2.6, -3.2, 3.0), 2.2, 520, (1.0, 0.86, 0.66))
    area("fill", (3.0, -2.6, -1.0), 3.0, 120, (0.62, 0.74, 1.0))
    area("kick", (0.5, -1.5, -3.2), 2.0, 60, (1.0, 0.6, 0.4))
    render("dial-base", base)
    render("dial-needle", [needle, weight, catcher])
    render("dial-cap", [cap, slot])


# ------------------------------------------------------------------ the lift car
def car():
    clear(); world(0.45)
    W, H = 448, 624
    camera(1.12, W, H, z=0.78)          # 1 unit = 400 px; the car is 1.04 wide and 1.48 tall, standing on z = 0
    D = 0.5                             # depth of the cab
    # platform and sill
    box("platform", (1.04, D + 0.06, 0.10), (0, 0, 0.05), BRASS, 0.012, 3)
    box("plat_lip", (1.08, D + 0.10, 0.025), (0, 0, 0.1125), BRASS_DK, 0.006)
    # corner posts and header
    for sx in (-1, 1):
        box(f"post{sx}", (0.075, 0.075, 1.02), (sx * 0.4825, -D / 2 + 0.04, 0.635), BRASS, 0.01, 3)
        box(f"post_b{sx}", (0.06, 0.06, 1.02), (sx * 0.49, D / 2 - 0.03, 0.635), BRASS_DK, 0.008)
        for z in (0.24, 1.05):
            s = lathe(f"rivet{sx}{z}", [(0.0, 0.0), (0.012, 0.0), (0.012, 0.006), (0.0, 0.011)], BRASS_DK, steps=16); s.location = (sx * 0.4825, -D / 2 + 0.0025, z)
    box("header", (1.04, 0.09, 0.09), (0, -D / 2 + 0.04, 1.19), BRASS, 0.01, 3)
    # stepped Deco roof
    for i, (w, h, z) in enumerate([(1.10, 0.09, 1.28), (0.72, 0.075, 1.3625), (0.30, 0.06, 1.43)]):
        box(f"roof{i}", (w, D + 0.08 - i * 0.12, h), (0, 0, z), BRASS, 0.012, 3)
    box("roof_shadow", (1.06, D + 0.04, 0.012), (0, 0, 1.231), BRASS_DK)
    lens = lathe("alarm_lens", [(0.0, 0.0), (0.034, 0.0), (0.034, 0.012), (0.022, 0.028), (0.0, 0.034)], RED, steps=32); lens.location = (0, -(D + 0.08) / 2, 1.28)
    ring = lathe("alarm_ring", [(0.034, 0.0), (0.046, 0.0), (0.046, 0.012), (0.034, 0.012)], BRASS_DK, steps=32); ring.location = (0, -(D + 0.08) / 2, 1.28)
    # cab interior: walnut back wall with cream panels, carpet, a ceiling lamp, a handrail
    box("back", (0.93, 0.02, 1.04), (0, D / 2 - 0.01, 0.64), WALNUT)
    for px in (-0.31, 0.0, 0.31):
        box(f"panel{px}", (0.25, 0.012, 0.50), (px, D / 2 - 0.024, 0.86), CREAM, 0.008)
        box(f"panel_lo{px}", (0.25, 0.012, 0.26), (px, D / 2 - 0.024, 0.30), mat(f"pl{px}", (0.26, 0.11, 0.04), 0, 0.45), 0.008)
    for sx in (-1, 1): box(f"side{sx}", (0.02, D - 0.05, 1.04), (sx * 0.46, 0, 0.64), WALNUT)
    box("floor", (0.93, D - 0.04, 0.01), (0, 0, 0.125), CARPET)
    box("ceiling", (0.93, D - 0.04, 0.02), (0, 0, 1.15), CREAM)
    box("ceil_lamp", (0.5, 0.2, 0.012), (0, -0.02, 1.136), LAMP)
    box("rail", (0.90, 0.018, 0.022), (0, D / 2 - 0.06, 0.56), BRASS, 0.006)
    # doors: two glass leaves with brass stiles, sliding outward behind the posts
    leaves = []
    for sx in (-1, 1):
        g = bpy.data.objects.new(f"leaf{sx}", None); sc.collection.objects.link(g)
        parts = [box(f"glass{sx}", (0.44, 0.008, 1.0), (0, 0, 0), GLASS),
                 box(f"stile_o{sx}", (0.03, 0.022, 1.02), (sx * 0.215, 0, 0), BRASS, 0.004),
                 box(f"stile_i{sx}", (0.03, 0.022, 1.02), (-sx * 0.215, 0, 0), BRASS, 0.004),
                 box(f"stile_m{sx}", (0.016, 0.018, 1.0), (0, 0, 0), BRASS_SATIN, 0.003),
                 box(f"rail_t{sx}", (0.44, 0.022, 0.03), (0, 0, 0.495), BRASS, 0.004),
                 box(f"rail_b{sx}", (0.44, 0.022, 0.05), (0, 0, -0.485), BRASS, 0.004),
                 box(f"rail_m{sx}", (0.44, 0.018, 0.016), (0, 0, -0.12), BRASS_SATIN, 0.003)]
        for p in parts: p.parent = g
        g.location = (sx * 0.2225, -D / 2 + 0.085 + (0.012 if sx > 0 else 0), 0.635)
        leaves.append((g, sx))
    area("key", (-2.2, -3.0, 2.6), 1.8, 300, (1.0, 0.82, 0.60), (0, 0, 0.7))
    area("fill", (2.4, -2.6, 0.6), 2.6, 70, (0.60, 0.72, 1.0), (0, 0, 0.7))
    area("top", (0.0, -1.2, 3.0), 1.6, 60, (1.0, 0.9, 0.8), (0, 0, 0.7))
    N = 13
    for i in range(N):
        u = i / (N - 1)
        for g, sx in leaves: g.location.x = sx * (0.2225 + 0.40 * u)
        # the leaves slide behind the posts; hide what would stick out past the car by clipping in the page
        render(f"car-{i:02d}")


# ------------------------------------------------------------------ the call button
def call():
    clear(); world(0.55)
    camera(2.4, 240, 240)
    plate = lathe("plate", [(0.0, 0.0), (1.0, 0.0), (1.0, 0.06), (0.95, 0.10), (0.80, 0.10), (0.76, 0.06), (0.0, 0.06)], BRASS)
    well = lathe("well", [(0.0, 0.05), (0.76, 0.05), (0.76, 0.062), (0.0, 0.062)], BRASS_DK)
    cap = lathe("button", [(0.0, 0.0), (0.66, 0.0), (0.66, 0.10), (0.60, 0.15), (0.0, 0.17)], IVORY, steps=96)
    tri = prism("arrow", [(-0.20, -0.13), (0.20, -0.13), (0.0, 0.19)], 0.02, (0, 0, 0), mat("arrow", (0.05, 0.03, 0.01), 0, 0.5), 0.004)
    area("key", (-2.6, -3.2, 3.0), 2.2, 520, (1.0, 0.86, 0.66))
    area("fill", (3.0, -2.6, -1.0), 3.0, 120, (0.62, 0.74, 1.0))
    for name, dy in (("call-up", 0.0), ("call-down", 0.085)):
        cap.location = (0, -0.06 + dy, 0); tri.location = (0, -0.235 + dy, 0)
        render(name)


for name, fn in (("dial", dial), ("car", car), ("call", call)):
    if not ONLY or ONLY == name: fn()
print("done")
