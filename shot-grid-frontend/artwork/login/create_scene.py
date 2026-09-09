"""为 Shot Grid 登录页生成可重复编辑、渲染的微缩数字片场。"""
import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

TAU = math.tau
DURATION = 10
FPS = 24
END = DURATION * FPS


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=1100)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--animation", action="store_true")
    parser.add_argument("--samples", type=int, default=48)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    # Blender 保存工程后可能改变相对路径基准，所有输出提前转换为绝对路径。
    args.output = args.output.resolve()
    return args


def material(name, color, metal=0, roughness=0.4, emission=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Metallic"].default_value = metal
    shader.inputs["Roughness"].default_value = roughness
    if emission:
        shader.inputs["Emission Color"].default_value = (*color, 1)
        shader.inputs["Emission Strength"].default_value = emission
    return mat


def finish(obj, name, mat=None, parent=None):
    obj.name = name
    if mat:
        obj.data.materials.append(mat)
    if parent:
        obj.parent = parent
    return obj


def empty(name, loc=(0, 0, 0), rot=0):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler.z = rot
    return obj


def box(name, loc, size, mat, bevel=0.04, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = finish(bpy.context.object, name, mat, parent)
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new("柔和加工边缘", "BEVEL")
        modifier.width = bevel
        modifier.segments = 3
        obj.modifiers.new("加权法线", "WEIGHTED_NORMAL")
    return obj


def cylinder(name, loc, radius, depth, mat, parent=None, axis="Z", vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = finish(bpy.context.object, name, mat, parent)
    if axis == "Y":
        obj.rotation_euler.x = math.pi / 2
    elif axis == "X":
        obj.rotation_euler.y = math.pi / 2
    bevel = obj.modifiers.new("车削倒角", "BEVEL")
    bevel.width = min(0.012, depth / 4)
    bevel.segments = 2
    for polygon in obj.data.polygons:
        polygon.use_smooth = len(polygon.vertices) == 4
    obj.modifiers.new("加权法线", "WEIGHTED_NORMAL")
    return obj


def sphere(name, loc, radius, mat, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=radius, location=loc)
    obj = finish(bpy.context.object, name, mat, parent)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    return obj


def line(name, coords, thickness, mat, parent=None, closed=False):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = thickness
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(coords) - 1)
    for point, coord in zip(spline.points, coords):
        point.co = (*coord, 1)
    spline.use_cyclic_u = closed
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    return finish(obj, name, mat, parent)


def circle(name, loc, radius, thickness, mat, parent=None, plane="XY"):
    coords = []
    for index in range(128):
        a = index / 128 * TAU
        x, y = radius * math.cos(a), radius * math.sin(a)
        coords.append((loc[0] + x, loc[1] + y, loc[2]) if plane == "XY"
                      else (loc[0] + x, loc[1], loc[2] + y))
    return line(name, coords, thickness, mat, parent, closed=True)


def text(name, body, loc, size, mat, parent=None, ground=False):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body
    curve.size = size
    curve.extrude = 0.0004
    curve.space_character = 1.15
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    if not ground:
        obj.rotation_euler.x = math.pi / 2
    return finish(obj, name, mat, parent)


def face(name, xz, y, mat, parent):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(x, y, z) for x, z in xz], [], [list(range(len(xz)))])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return finish(obj, name, mat, parent)


def area(name, loc, target, power, color, size):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = power
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def loop_float(obj, offset=0, amplitude=0.08):
    origin = obj.location.copy()
    rotation = obj.rotation_euler.z
    # 首尾状态及导数相同；第 241 帧只作闭环关键帧，不输出重复尾帧。
    for frame in range(1, END + 2, 4):
        t = (frame - 1) / END * TAU
        obj.location = origin + Vector((0.035 * math.sin(t + offset), 0, amplitude * math.sin(t + offset)))
        obj.rotation_euler.z = rotation + 0.025 * math.sin(t + offset)
        obj.keyframe_insert(data_path="location", frame=frame)
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)


def build(args):
    # 从工厂空场景构建，不读取用户当前打开的 Blender 文件。
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.name = "Shot Grid · 微缩数字片场"
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = args.samples
    scene.eevee.use_raytracing = True
    scene.render.resolution_x = args.size
    scene.render.resolution_y = args.size
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = END
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 15
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = (0.15, 0.20, 0.28, 1)
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = 0.3
    scene.view_settings.view_transform = "AgX"

    black = material("机身 · 石墨黑", (0.035, 0.043, 0.054), 0.55, 0.3)
    rubber = material("橡胶 · 细哑光", (0.012, 0.018, 0.023), 0.05, 0.53)
    silver = material("金属 · 拉丝钛", (0.24, 0.30, 0.35), 0.8, 0.28)
    gold = material("金属 · 香槟金", (0.63, 0.36, 0.13), 0.75, 0.28)
    amber = material("导光 · 琥珀", (1.0, 0.45, 0.11), 0.35, 0.28, 2.4)
    white = material("丝印 · 暖白", (0.79, 0.83, 0.82), 0.05, 0.4)
    glass = material("镜片 · 蓝绿镀膜", (0.025, 0.18, 0.21), 0.8, 0.1)
    led = material("面光 · 暖白", (1.0, 0.8, 0.52), 0, 0.4, 4)
    red = material("指示灯 · 录制", (0.9, 0.055, 0.012), 0, 0.3, 2)
    screen = material("显示屏 · 深蓝", (0.018, 0.037, 0.055), 0.2, 0.4, 0.5)
    teal = material("分镜 · 青灰", (0.095, 0.29, 0.31), 0.25, 0.4, 0.4)
    pale = material("分镜 · 浅青", (0.29, 0.55, 0.57), 0.15, 0.4, 0.5)
    stage_mat = material("台面 · 玄武岩", (0.045, 0.062, 0.075), 0.5, 0.35)
    floor_mat = material("背景 · 无缝深灰", (0.013, 0.021, 0.029), 0.25, 0.42)

    box("无缝摄影棚地面", (0, 0, -0.31), (200, 200, 0.2), floor_mat)
    cylinder("片场底座", (0, 0, -0.025), 3.05, 0.38, black, vertices=128)
    cylinder("片场顶面", (0, 0, 0.185), 2.94, 0.08, stage_mat, vertices=128)
    circle("台座香槟金腰线", (0, 0, 0.11), 3.055, 0.016, gold)
    circle("制作流程轨道", (0, 0, 0.232), 2.7, 0.012, gold)
    circle("内侧轨道", (0, 0, 0.234), 2.58, 0.004, silver)
    for index in range(64):
        a = index * TAU / 64
        outer = 2.82 if index % 4 == 0 else 2.79
        line("台面刻度", [(2.75 * math.cos(a), 2.75 * math.sin(a), 0.234),
                        (outer * math.cos(a), outer * math.sin(a), 0.234)], 0.006, silver)
    for index in range(4):
        a = -2.6 + index * 0.45
        sphere("流程节点", (2.7 * math.cos(a), 2.7 * math.sin(a), 0.255), 0.043, amber)
    text("台面铭文", "SHOT GRID  /  PRODUCTION STAGE", (-1.5, -2.2, 0.24), 0.105, white, ground=True)

    # 主体为带导轨、对焦齿环、监视器和云台的电影摄影机。
    rig = empty("电影摄影机总成", (-1.0, -0.5, 0.24), math.radians(-13))
    for a in [0.2, 2.3, 4.4]:
        end = (0.75 * math.cos(a), 0.75 * math.sin(a), 0.025)
        line("三脚架外支腿", [(0, 0, 0.92), end], 0.045, black, rig)
        line("三脚架亮部", [(0, 0, 0.84), (end[0] * 0.68, end[1] * 0.68, 0.24)], 0.018, silver, rig)
        sphere("三脚架脚垫", end, 0.075, rubber, rig)
    cylinder("液压云台", (0, 0, 1.04), 0.2, 0.24, black, rig)
    circle("云台金色锁环", (0, 0, 1.0), 0.2, 0.016, gold, rig)
    box("摄影机底板", (0, -0.15, 1.2), (0.82, 1.45, 0.11), silver, parent=rig)
    for x in [-0.31, 0.31]:
        line("镜头支撑导轨", [(x, -1.2, 1.17), (x, 0.72, 1.17)], 0.035, silver, rig)
    box("摄影机机身", (0, 0.02, 1.64), (0.92, 0.94, 0.77), black, 0.095, rig)
    box("后侧电池", (0, 0.64, 1.61), (0.72, 0.3, 0.70), rubber, 0.07, rig)
    box("上部提手", (0, 0.09, 2.25), (0.15, 0.83, 0.10), black, parent=rig)
    for y in [-0.19, 0.36]:
        box("提手支柱", (0, y, 2.11), (0.12, 0.10, 0.26), silver, parent=rig)
    for i in range(9):
        box("散热格栅", (0.467, -0.27 + i * 0.07, 1.85), (0.014, 0.025, 0.16), rubber, 0.002, rig)
    for x, y, z in [(0.473, -0.3, 1.43), (0.473, 0.17, 1.43), (0.473, 0.29, 1.76)]:
        cylinder("侧面控制旋钮", (x, y, z), 0.06, 0.045, silver, rig, "X", 32)
    cylinder("镜头卡口", (0, -0.49, 1.66), 0.31, 0.13, silver, rig, "Y")
    for y, radius, depth, mat in [
        (-0.68, 0.32, 0.27, black), (-0.89, 0.37, 0.18, rubber),
        (-1.03, 0.36, 0.09, gold), (-1.16, 0.39, 0.18, black),
        (-1.28, 0.41, 0.065, silver), (-1.32, 0.375, 0.035, rubber),
        (-1.345, 0.31, 0.012, glass), (-1.355, 0.22, 0.013, glass)
    ]:
        cylinder("电影镜头", (0, y, 1.66), radius, depth, mat, rig, "Y")
    for i in range(48):
        a = i * TAU / 48
        line("对焦齿环刻纹", [(0.375 * math.cos(a), -0.84, 1.66 + 0.375 * math.sin(a)),
                           (0.375 * math.cos(a), -0.96, 1.66 + 0.375 * math.sin(a))], 0.009, black, rig)
    for radius in [0.16, 0.25, 0.30]:
        circle("镜片同心镀膜", (0, -1.367, 1.66), radius, 0.006, pale, rig, "XZ")
    cylinder("镜头光阑", (0, -1.372, 1.66), 0.09, 0.012, rubber, rig, "Y", 8)
    sphere("录制指示灯", (0.31, -0.457, 1.89), 0.024, red, rig)
    text("镜头铭牌", "SG  /  35", (-0.33, -0.463, 1.39), 0.068, white, rig)
    monitor = box("机顶监视器", (0.26, 0.0, 2.47), (0.72, 0.10, 0.44), black, parent=rig)
    box("机顶监视器画面", (0.26, -0.058, 2.47), (0.62, 0.01, 0.34), screen, 0.012, rig)
    line("监视器画面", [(-0.01, -0.067, 2.36), (0.18, -0.067, 2.54), (0.28, -0.067, 2.43),
                       (0.42, -0.067, 2.57), (0.53, -0.067, 2.36)], 0.009, pale, rig)

    def storyboard(name, loc, width, height, rotation, label, accent, phase):
        parent = empty(name, loc, rotation)
        box("悬浮分镜金属外框", (0, 0, 0), (width, 0.10, height), silver, 0.07, parent)
        box("悬浮分镜内框", (0, -0.06, 0), (width - 0.035, 0.04, height - 0.035), black, 0.055, parent)
        box("分镜显示屏", (0, -0.086, 0.005), (width - 0.17, 0.012, height - 0.17), screen, 0.035, parent)
        w, h = width / 2 - 0.13, height / 2 - 0.13
        # 程序化山景，无真实项目、客户或员工数据。
        face("远山分镜", [(-w, -h + 0.19), (-w, -0.04), (-w * 0.6, h * 0.34),
                       (-w * 0.31, h * 0.0), (w * 0.14, h * 0.65), (w * 0.6, h * 0.1),
                       (w, h * 0.4), (w, -h + 0.19)], -0.10, teal, parent)
        face("近山分镜", [(-w, -h + 0.19), (-w, -h * 0.1), (-w * 0.5, h * 0.16),
                       (w * 0.22, -h * 0.22), (w * 0.61, h * 0.23), (w, -h * 0.1),
                       (w, -h + 0.19)], -0.11, pale, parent)
        cylinder("分镜太阳", (-w * 0.52, -0.104, h * 0.48), height * 0.075, 0.004, accent, parent, "Y")
        line("画面中线", [(-w, -0.12, -h + 0.17), (w, -0.12, -h + 0.17)], 0.004, silver, parent)
        text("分镜版本标记", label, (-w, -0.123, -h + 0.055), height * 0.052, white, parent)
        sphere("分镜状态灯", (w - 0.05, -0.13, -h + 0.09), 0.02, accent, parent)
        for xsign in [-1, 1]:
            for zsign in [-1, 1]:
                x, z = xsign * (w - 0.045), zsign * (h - 0.045)
                line("分镜安全框", [(x - xsign * 0.13, -0.122, z), (x, -0.122, z),
                                  (x, -0.122, z - zsign * 0.09)], 0.005, gold, parent)
        loop_float(parent, phase)
        return parent

    storyboard("主分镜 · 制作", (0.25, 1.27, 2.55), 2.7, 1.7, math.radians(-8),
               "001  /  SHOT DEVELOPMENT", amber, 0)
    storyboard("候选分镜 · 版本", (1.82, 0.0, 1.88), 1.62, 1.13, math.radians(-16),
               "V002  /  REVIEW", amber, math.pi / 2)
    storyboard("资产分镜 · 草图", (-1.9, 1.1, 2.0), 1.14, 0.84, math.radians(12),
               "ASSET  /  001", pale, math.pi)

    # 左右片场灯具带支架与遮扉，发光面朝向场景前方。
    for index, (x, y, z) in enumerate([(-2.05, 0.9, 3.45), (2.12, 1.18, 3.1)]):
        light_rig = empty("片场灯具", (x, y, 0.24), -0.16 if index == 0 else 0.24)
        line("灯架立柱", [(0, 0, 0.05), (0, 0, z - 0.22)], 0.025, silver, light_rig)
        cylinder("灯架紧固", (0, 0, 1.35), 0.06, 0.14, black, light_rig)
        for a in [0, 2.1, 4.2]:
            line("灯架三脚", [(0, 0, 0.24), (0.34 * math.cos(a), 0.34 * math.sin(a), 0.01)], 0.025, black, light_rig)
        box("柔光箱背板", (0, 0, z), (0.82, 0.16, 0.61), black, 0.055, light_rig)
        box("柔光箱发光面", (0, -0.09, z), (0.68, 0.025, 0.47), led, 0.025, light_rig)
        for dx in [-0.45, 0.45]:
            flap = box("灯具侧遮扉", (dx, -0.15, z), (0.20, 0.045, 0.66), black, 0.012, light_rig)
            flap.rotation_euler.z = -0.5 if dx < 0 else 0.5
        box("灯具上遮扉", (0, -0.15, z + 0.36), (0.9, 0.25, 0.035), black, 0.012, light_rig)

    slate = empty("场记板", (0.78, -1.37, 0.62), math.radians(-13))
    box("场记板主体", (0, 0, 0.23), (0.95, 0.065, 0.64), black, 0.025, slate)
    text("场记板标记", "SHOT GRID", (-0.39, -0.042, 0.30), 0.11, white, slate)
    text("场记板镜号", "SCENE  001     TAKE  01", (-0.39, -0.043, 0.13), 0.05, white, slate)
    line("场记板分栏线", [(-0.39, -0.043, 0.245), (0.39, -0.043, 0.245)], 0.004, silver, slate)
    hinge = empty("场记板活动拍板")
    hinge.parent = slate
    hinge.location = (-0.475, 0, 0.60)
    box("活动拍板", (0.475, 0, 0), (0.95, 0.08, 0.14), black, 0.012, hinge)
    for i in range(5):
        x = 0.045 + i * 0.19
        face("拍板斜纹", [(x, -0.07), (x + 0.085, -0.07), (x + 0.15, 0.07), (x + 0.065, 0.07)],
             -0.044, white, hinge)
    for frame in range(1, END + 2, 4):
        hinge.rotation_euler.y = -0.10 - 0.11 * (1 - math.cos((frame - 1) / END * TAU))
        hinge.keyframe_insert(data_path="rotation_euler", frame=frame)

    # 轻微环绕运镜与缓慢漂浮；灯光亮度固定，避免闪烁。
    area("主光 · 大面积暖白", (0, -5, 7), (0, 0, 1.3), 1500, (1.0, 0.82, 0.63), 6)
    area("轮廓光 · 冷青", (1, 4, 5.5), (0, 0, 1.6), 1900, (0.45, 0.70, 1.0), 5)
    area("侧光 · 琥珀", (-4, 0, 3.5), (-0.7, 0, 1.7), 1150, (1.0, 0.46, 0.16), 4)
    area("镜头补光", (4, -5, 3), (-1, -0.7, 1.7), 450, (0.65, 0.85, 1.0), 3)
    bpy.ops.object.camera_add()
    camera = bpy.context.object
    camera.name = "登录页主摄影机"
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 8.3
    camera.data.lens = 48
    camera.data.clip_end = 250
    scene.camera = camera
    target = Vector((0, 0, 1.40))
    for frame in range(1, END + 2, 4):
        t = (frame - 1) / END * TAU
        a = math.radians(25) + math.radians(2.0) * math.sin(t)
        camera.location = (11 * math.sin(a), -11 * math.cos(a), 7.0 + 0.09 * math.sin(t))
        camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
    scene.frame_set(1)
    args.output.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(args.output / "frames" / "stage_")
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output / "shot-grid-login.blend"))
    print(f"SCENE_READY objects={len(scene.objects)} frames={END} size={args.size}", flush=True)
    if args.preview:
        scene.render.filepath = str(args.output / "preview.png")
        bpy.ops.render.render(write_still=True)
    if args.animation:
        (args.output / "frames").mkdir(exist_ok=True)
        scene.render.filepath = str(args.output / "frames" / "stage_")
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    build(parse_args())
