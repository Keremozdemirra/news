"""Face the Figure: the assay balance, rendered from Blender as stepped frames.

Run: Blender -b --factory-startup -P build_scale.py -- <out_dir> [step_deg] [samples] [only_frame|plate]

One object, hand-modelled from primitives and lathes: black enamel foot and column, a brass beam
with a needle on an ivory reading plate, two brass pans on three wires each. For every beam angle
from -12 to +12 degrees it writes two layers (1 degree steps by default):
  back_<n>.png   everything except the front half of each pan (shadow catcher on the bench included)
  front_<n>.png  only the front half of each pan, so a paper ticket can stand inside the pan
and scale.json with the projected pan positions per frame (normalised, origin top left).
Camera: orthographic, 7 degrees above level, 780 x 880 px (2x of a 390 pt design).
"""
import bpy, bmesh, math, json, sys
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
OUT = argv[0] if argv else "/tmp/scale"
STEP = float(argv[1]) if len(argv) > 1 else 1.0
SAMPLES = int(argv[2]) if len(argv) > 2 else 96
ONLY = argv[3] if len(argv) > 3 else ""
ANGLES = [round(-12 + i * STEP, 3) for i in range(int(24 / STEP) + 1)]
W, H = 900, 880
ZP, L, DROP, PAN_R, PAN_D = 0.44, 0.125, 0.29, 0.095, 0.034

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
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
sc.render.film_transparent = True
sc.render.image_settings.file_format = "PNG"
sc.render.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"


def mat(name, base, metal=0.0, rough=0.4, coat=0.0):
    m = bpy.data.materials.new(name)
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    if coat:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.08
    return m


BRASS = mat("brass", (0.74, 0.50, 0.19), 1.0, 0.27)
BRASS_DK = mat("brass_dark", (0.42, 0.28, 0.10), 1.0, 0.42)
ENAMEL = mat("black_enamel", (0.010, 0.011, 0.014), 0.0, 0.32, 0.6)
IVORY = mat("ivory", (0.93, 0.90, 0.80), 0.0, 0.55)
INK = mat("ink", (0.01, 0.01, 0.012), 0.0, 0.5)
LACQUER = mat("lacquer", (0.42, 0.018, 0.008), 0.0, 0.45)


def to_obj(name, bm, material, smooth=True, bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    ob.data.materials.append(material)
    if smooth:
        for p in me.polygons: p.use_smooth = True
    if bevel:
        m = ob.modifiers.new("bev", "BEVEL"); m.width = bevel; m.segments = 2; m.angle_limit = math.radians(35)
    return ob


def lathe(name, profile, material, angle=2 * math.pi, steps=48, start=0.0, bevel=0.0):
    """profile: list of (r, z), closed. angle spins about Z from the +X axis (positive = through +Y = the back)."""
    bm = bmesh.new()
    vs = [bm.verts.new((r, 0, z)) for r, z in profile]
    es = [bm.edges.new((vs[i], vs[(i + 1) % len(vs)])) for i in range(len(vs))]
    bmesh.ops.spin(bm, geom=vs + es, angle=angle, steps=steps, axis=(0, 0, 1), cent=(0, 0, 0))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return to_obj(name, bm, material, True, bevel)


def box(name, size, loc, material, bevel=0.0):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    ob = to_obj(name, bm, material, False, bevel); ob.location = loc; return ob


def cyl(name, r, h, loc, material, axis="Z", verts=24):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r, depth=h)
    ob = to_obj(name, bm, material, True)
    ob.location = loc
    if axis == "Y": ob.rotation_euler = (math.pi / 2, 0, 0)
    if axis == "X": ob.rotation_euler = (0, math.pi / 2, 0)
    return ob


def wire(name, a, b, r, material):
    a, b = Vector(a), Vector(b)
    d = b - a
    ob = cyl(name, r, d.length, (a + b) / 2, material, verts=8)
    ob.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    return ob


# ---- foot, column, head (black enamel with brass collars)
foot = lathe("foot", [(0, 0), (0.112, 0), (0.114, 0.006), (0.110, 0.016), (0.092, 0.022), (0.055, 0.031), (0.03, 0.05), (0.0, 0.05)], ENAMEL, steps=72)
lathe("foot_band", [(0.108, 0.0), (0.1165, 0.0), (0.1175, 0.004), (0.1165, 0.008), (0.108, 0.008)], BRASS, steps=72)
col = lathe("column", [(0.0, 0.05), (0.022, 0.05), (0.018, 0.12), (0.0135, 0.30), (0.012, ZP - 0.045), (0.0, ZP - 0.045)], ENAMEL, steps=40)
for z, r in [(0.055, 0.028), (0.19, 0.0185), (ZP - 0.05, 0.02)]:
    lathe(f"collar{z}", [(0.0, z - 0.007), (r, z - 0.007), (r + 0.002, z), (r, z + 0.007), (0.0, z + 0.007)], BRASS, steps=40)
head = box("head", (0.052, 0.028, 0.034), (0, 0, ZP - 0.02), BRASS, 0.003)
cyl("pin", 0.0045, 0.05, (0, 0, ZP), BRASS_DK, axis="Y")
neck = lathe("finial", [(0, ZP + 0.018), (0.005, ZP + 0.018), (0.0035, ZP + 0.03), (0.011, ZP + 0.04), (0.0035, ZP + 0.05), (0, ZP + 0.05)], BRASS, steps=32)
# the reading plate on the column: ivory, with ten ticks, centre tick longer
plate = box("plate", (0.088, 0.006, 0.026), (0, -0.015, ZP - 0.115), IVORY, 0.0015)
for i in range(-5, 6):
    box(f"tick{i}", (0.0013, 0.002, 0.008 if i else 0.015), (i * 0.0075, -0.0185, ZP - 0.117 + (0.0 if i else -0.0035)), INK)

# ---- beam group, rotated about the pin
piv = bpy.data.objects.new("pivot", None); sc.collection.objects.link(piv); piv.location = (0, 0, ZP)
bm = bmesh.new()
prof = [(-0.140, 0.0), (-0.120, 0.008), (-0.045, 0.019), (0.0, 0.022), (0.045, 0.019), (0.120, 0.008), (0.140, 0.0), (0.120, -0.006), (0.045, -0.012), (0.0, -0.014), (-0.045, -0.012), (-0.120, -0.006)]
vs = [bm.verts.new((x, -0.0045, z)) for x, z in prof]
f = bm.faces.new(vs)
r = bmesh.ops.extrude_face_region(bm, geom=[f])
bmesh.ops.translate(bm, vec=(0, 0.009, 0), verts=[v for v in r["geom"] if isinstance(v, bmesh.types.BMVert)])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
beam = to_obj("beam", bm, BRASS, False, 0.0011); beam.parent = piv
for sx in (-1, 1):
    for x in (0.05, 0.095):
        d = cyl(f"rivet{sx}{x}", 0.0032, 0.003, (sx * x, -0.0058, 0.002), BRASS_DK, axis="Y", verts=16); d.parent = piv
    e = cyl(f"edge{sx}", 0.0048, 0.02, (sx * L, 0, -0.002), BRASS_DK, axis="Y", verts=16); e.parent = piv
nd = bm = bmesh.new()
for pts in [[(-0.0052, -0.036), (0.0052, -0.036), (0.0014, -0.128), (-0.0014, -0.128)]]:
    vs = [nd.verts.new((x, -0.012, z)) for x, z in pts]; nd.faces.new(vs)
needle = to_obj("needle", nd, LACQUER, False); needle.parent = piv
bw = cyl("needle_boss", 0.0075, 0.012, (0, -0.012, -0.002), BRASS, axis="Y"); bw.parent = piv

# ---- pans: bowl halves, wires, hook ring
PROFILE = [(0.0, 0.0), (0.07, 0.0), (0.089, 0.020), (PAN_R, PAN_D), (PAN_R - 0.003, PAN_D), (0.085, 0.022), (0.066, 0.004), (0.0, 0.004)]
pans = {}
for side in ("l", "r"):
    grp = bpy.data.objects.new(f"pan_{side}", None); sc.collection.objects.link(grp)
    back = lathe(f"bowl_back_{side}", PROFILE, BRASS, angle=math.pi, steps=28, bevel=0.0008)
    front = lathe(f"bowl_front_{side}", PROFILE, BRASS, angle=-math.pi, steps=28, bevel=0.0008)
    back.parent = grp; front.parent = grp
    rim_top = PAN_D
    wires = [cyl(f"w{side}{k}", 0.0016, 0.1, (0, 0, 0), BRASS, verts=8) for k in range(0)]
    for k, ang in enumerate((90, 215, 325)):
        a = math.radians(ang); px, py = (PAN_R - 0.004) * math.cos(a), (PAN_R - 0.004) * math.sin(a)
        w = wire(f"wire{side}{k}", (px, py, rim_top - 0.002), (0, 0, DROP), 0.0017, BRASS_DK); w.parent = grp
    ring = lathe(f"ring{side}", [(0.0, DROP + 0.002), (0.007, DROP + 0.002), (0.007, DROP + 0.012), (0.0, DROP + 0.012)], BRASS, steps=20); ring.parent = grp
    pans[side] = (grp, back, front)

# ---- the assay office: a stone counter and a wall of glazed cobalt tiles. Two passes share one camera:
#   balance pass: counter and wall are shadow catchers, so the frames carry only the balance and its shadow
#   plate pass:   the room without the balance, three frames wide, for the page to stand the balance in
WALL_Y, TILE, GROUT = 0.55, 0.074, 0.003
def nodes_of(m): return m.node_tree.nodes, m.node_tree.links
STONE = mat("stone", (0.86, 0.84, 0.78), 0.0, 0.28)
n, l = nodes_of(STONE); b = next(x for x in n if x.type == "BSDF_PRINCIPLED")
nz = n.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 260; nz.inputs["Detail"].default_value = 6
rp = n.new("ShaderNodeValToRGB"); rp.color_ramp.elements[0].position = 0.42; rp.color_ramp.elements[0].color = (0.70, 0.66, 0.58, 1); rp.color_ramp.elements[1].position = 0.60; rp.color_ramp.elements[1].color = (0.90, 0.87, 0.79, 1)
l.new(nz.outputs["Fac"], rp.inputs["Fac"]); l.new(rp.outputs["Color"], b.inputs["Base Color"])
GLAZE = mat("glaze", (0.02, 0.10, 0.40), 0.0, 0.45, 1.0)
n, l = nodes_of(GLAZE); b = next(x for x in n if x.type == "BSDF_PRINCIPLED")
oi = n.new("ShaderNodeObjectInfo"); hs = n.new("ShaderNodeHueSaturation"); mth = n.new("ShaderNodeMapRange")
mth.inputs["To Min"].default_value = 0.82; mth.inputs["To Max"].default_value = 1.2
hs.inputs["Color"].default_value = (0.006, 0.030, 0.19, 1)
mh = n.new("ShaderNodeMapRange"); mh.inputs["To Min"].default_value = 0.485; mh.inputs["To Max"].default_value = 0.515
mlt = n.new("ShaderNodeMath"); mlt.operation = "MULTIPLY"; mlt.inputs[1].default_value = 7.31
frc = n.new("ShaderNodeMath"); frc.operation = "FRACT"
l.new(oi.outputs["Random"], mlt.inputs[0]); l.new(mlt.outputs[0], frc.inputs[0]); l.new(frc.outputs[0], mh.inputs["Value"]); l.new(mh.outputs["Result"], hs.inputs["Hue"])
l.new(oi.outputs["Random"], mth.inputs["Value"]); l.new(mth.outputs["Result"], hs.inputs["Value"]); l.new(hs.outputs["Color"], b.inputs["Base Color"])
gz = n.new("ShaderNodeTexNoise"); gz.inputs["Scale"].default_value = 38; gz.inputs["Detail"].default_value = 1.5
bp = n.new("ShaderNodeBump"); bp.inputs["Strength"].default_value = 0.10; bp.inputs["Distance"].default_value = 0.004
l.new(gz.outputs["Fac"], bp.inputs["Height"]); l.new(bp.outputs["Normal"], b.inputs["Coat Normal"])
GROUTM = mat("grout", (0.62, 0.60, 0.54), 0.0, 0.9)

counter = box("counter", (4.0, 2.0, 0.02), (0, WALL_Y - 1.0, -0.01), STONE)
backing = box("backing", (4.0, 0.01, 2.0), (0, WALL_Y + 0.008, 1.0), GROUTM)
import random
random.seed(11)
tm = None; tiles = []
for cx in range(-16, 17):
    for rz in range(0, 13):
        t = box(f"tile{cx}_{rz}", (TILE - GROUT, 0.008, TILE - GROUT), (cx * TILE, WALL_Y, TILE / 2 + rz * TILE + 0.002), GLAZE, 0.0022)
        t.rotation_euler = (random.uniform(-0.012, 0.012), 0, random.uniform(-0.004, 0.004))   # hand-set tiles are never quite flush
        tiles.append(t)
room = [counter, backing] + tiles
catch_floor = box("catch_floor", (4.0, 2.0, 0.002), (0, WALL_Y - 1.0, 0.0002), mat("c1", (0.80, 0.78, 0.72), 0, 1.0)); catch_floor.is_shadow_catcher = True
catch_wall = box("catch_wall", (4.0, 0.002, 2.0), (0, WALL_Y - 0.006, 1.0), mat("c2", (0.03, 0.10, 0.36), 0, 1.0)); catch_wall.is_shadow_catcher = True
catchers = [catch_floor, catch_wall]

cam_d, el = 3.0, math.radians(7)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; SCALE = 0.46 * W / 780
cam.data.ortho_scale = SCALE; cam.data.sensor_fit = "HORIZONTAL"
ty = 0.235
CAM0 = Vector((0, -cam_d * math.cos(el), ty + cam_d * math.sin(el)))
cam.location = CAM0
cam.rotation_euler = (math.pi / 2 - el, 0, 0)


def area(name, loc, size, energy, color=(1, 1, 1), aim=(0, 0, 0.25)):
    ld = bpy.data.lights.new(name, "AREA"); ld.energy = energy * EXPO; ld.size = size; ld.color = color
    o = bpy.data.objects.new(name, ld); sc.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector(aim) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o

EXPO = 0.16
# One window, high on the left and in front. Its frame (four boards in the light path) shades the far wall and
# the ends of the counter, so the room falls off by itself and the balance stands in the pool of light.
TGT = Vector((0.0, 0.55, 0.33)); az, elv = math.radians(5), math.radians(42)
LDIR = Vector((-math.sin(az) * math.cos(elv), -math.cos(az) * math.cos(elv), math.sin(elv)))
key = area("window", tuple(TGT + LDIR * 2.5), 0.30, 900, (1.0, 0.96, 0.88), tuple(TGT))
UPV = (Vector((0, 0, 1)) - LDIR * LDIR.z).normalized(); RTV = UPV.cross(LDIR).normalized()
from mathutils import Matrix
gm = Matrix((RTV, UPV, LDIR)).transposed()
OW, OH, BAR = 1.0, 0.66, 1.6
BLOCK = mat("block", (0.02, 0.02, 0.02), 0, 1.0)
for nm, sz, off in (("gl", (BAR, BAR * 2 + OH, 0.005), (-(OW + BAR) / 2, 0, 0)), ("gr", (BAR, BAR * 2 + OH, 0.005), ((OW + BAR) / 2, 0, 0)),
                    ("gt", (OW, BAR, 0.005), (0, (OH + BAR) / 2, 0)), ("gb", (OW, BAR, 0.005), (0, -(OH + BAR) / 2, 0)),
                    ("mv", (0.03, OH, 0.005), (0.19, 0, 0)), ("mh", (OW, 0.03, 0.005), (0, 0.21, 0))):
    g = box(nm, sz, (0, 0, 0), BLOCK); g.rotation_euler = gm.to_euler(); g.location = TGT + LDIR * 1.0 + gm @ (Vector(off) + Vector((0, -0.11, 0)))
    g.visible_camera = False; g.visible_glossy = False
GOBO = [o for o in sc.objects if o.name in ("gl", "gr", "gt", "gb", "mv", "mh")]
area("fill", (1.3, -1.2, 0.5), 1.6, 55, (0.82, 0.90, 1.0))
area("top", (0.1, -0.5, 1.7), 1.2, 40)
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
bgn = next(x for x in w.node_tree.nodes if x.type == "BACKGROUND"); bgn.inputs["Color"].default_value = (0.55, 0.57, 0.6, 1); bgn.inputs["Strength"].default_value = 0.35

os_makedirs = __import__("os").makedirs; os_makedirs(OUT, exist_ok=True)
balance = [o for o in sc.objects if o.type == "MESH" and o not in room and o not in catchers and o not in GOBO]
fronts = [pans[s][2] for s in pans]; front_set = set(fronts)

if ONLY == "plate":
    PW, PH = 4.0, 1.5
    for o in balance + catchers: o.hide_render = True
    sc.render.film_transparent = False
    sc.render.resolution_x, sc.render.resolution_y = int(W * PW), int(H * PH)
    cam.data.ortho_scale = SCALE * PW
    up = Vector((0, math.sin(el), math.cos(el)))
    cam.location = CAM0 + up * (SCALE * H / W) * (PH - 1) / 2      # same bottom edge as a balance frame
    sc.render.filepath = f"{OUT}/plate.png"
    bpy.ops.render.render(write_still=True)
    print("plate done"); sys.exit(0)

for o in room + GOBO: o.hide_render = True

if ONLY == "layers":
    # The balance as six sprites at level beam, for a page that moves them with transforms instead of swapping 98
    # frames: the stand with the whole balance's shadow, the beam (it only rotates about the pin), the head that covers
    # the beam's middle, and each pan as a
    # back and a front half (they only translate, the camera is orthographic). A part that is out of a sprite still
    # throws its shadow and its bounce light: it is hidden from the camera alone.
    def kids(o):
        out = []
        for c in o.children:
            out += [c] + kids(c)
        return out
    beam_set = set(kids(piv))
    pan_set = {s: set(kids(pans[s][0])) for s in pans}
    stand = [o for o in balance if o not in beam_set and all(o not in pan_set[s] for s in pans)]
    piv.rotation_euler = (0, 0, 0)
    for s, sgn in (("l", -1), ("r", 1)):
        pans[s][0].location = (sgn * L, 0, ZP - DROP)
    bpy.context.view_layer.update()
    # what stands in front of the beam and its needle: the head the beam passes through, the pin, the finial and the
    # reading plate the needle tip runs behind. Drawn again over the beam, so the beam turns inside the head.
    top = {o for o in stand if o.name in ("head", "pin", "finial", "plate") or o.name.startswith("tick")}
    sets = {"stand": (set(stand), True), "beam": (beam_set, False), "top": (top, False)}
    for s in pans:
        sets[f"pan_{s}_back"] = (pan_set[s] - {pans[s][2]}, False)
        sets[f"pan_{s}_front"] = ({pans[s][2]}, False)
    for name, (show, shadow) in sets.items():
        # the beam alone is lit as a free part: where it runs inside the head and the pan rings it would render black,
        # and those places come into view as soon as the sprite turns
        for o in balance: o.hide_render = (name == "beam" and o not in show); o.visible_camera = o in show
        for o in catchers: o.hide_render = not shadow
        sc.render.filepath = f"{OUT}/{name}.png"
        bpy.ops.render.render(write_still=True)
        print("layer", name, flush=True)
    pv = world_to_camera_view(sc, cam, Vector((0, 0, ZP)))
    meta = {"w": W, "h": H, "pivot": [round(pv.x, 5), round(1 - pv.y, 5)], "layers": list(sets), "frames": [], "angles": ANGLES, "step": STEP}
    for th in ANGLES:
        t = math.radians(th); fr = {"angle": th}
        for s, sgn in (("l", -1), ("r", 1)):
            g = Vector((sgn * L * math.cos(t), 0, ZP - sgn * L * math.sin(t) - DROP))
            c = world_to_camera_view(sc, cam, Vector((g.x, g.y, g.z + PAN_D))); b = world_to_camera_view(sc, cam, g)
            fr[s] = {"rim": [round(c.x, 5), round(1 - c.y, 5)], "base": [round(b.x, 5), round(1 - b.y, 5)]}
        meta["frames"].append(fr)
    json.dump(meta, open(f"{OUT}/layers.json", "w"))
    print("layers done"); sys.exit(0)

meta = {"w": W, "h": H, "step": STEP, "angles": ANGLES, "frames": []}
for n, th in enumerate(ANGLES):
    t = math.radians(th)
    piv.rotation_euler = (0, t, 0)           # positive = right end down
    for s, sgn in (("l", -1), ("r", 1)):
        pans[s][0].location = (sgn * L * math.cos(t), 0, ZP - sgn * L * math.sin(t) - DROP)
    bpy.context.view_layer.update()
    fr = {"angle": th}
    for s in ("l", "r"):
        g = pans[s][0].location
        c = world_to_camera_view(sc, cam, Vector((g.x, g.y, g.z + PAN_D)))          # rim, centre
        b = world_to_camera_view(sc, cam, Vector((g.x, g.y, g.z)))                   # base, centre
        fr[s] = {"rim": [round(c.x, 5), round(1 - c.y, 5)], "base": [round(b.x, 5), round(1 - b.y, 5)]}
    meta["frames"].append(fr)
    if ONLY and ONLY != str(n): continue
    for layer in ("back", "front"):
        for o in balance: o.hide_render = (o in front_set) if layer == "back" else (o not in front_set)
        for o in catchers: o.hide_render = layer == "front"
        sc.render.filepath = f"{OUT}/{layer}_{n:02d}.png"
        if __import__("os").path.exists(sc.render.filepath): continue      # resumable
        bpy.ops.render.render(write_still=True)
    print("frame", n, th, flush=True)
json.dump(meta, open(f"{OUT}/scale.json", "w"))
print("done", len(ANGLES))
