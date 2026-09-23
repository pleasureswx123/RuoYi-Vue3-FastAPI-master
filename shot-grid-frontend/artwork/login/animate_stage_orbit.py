"""在保留的四阶段展台工程上生成从高到低的环绕运镜。"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

root = Path(__file__).resolve().parents[3]
output = root / 'output/login-stage-orbit'
output.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(root / 'output/login-workflow/shot-grid-workflow.blend'))
scene = bpy.context.scene
camera = scene.camera
camera.animation_data_clear()
camera.data.animation_data_clear()
camera.name = '高低环绕摄影机'
camera.data.type = 'PERSP'
camera.data.lens = 48
camera.data.clip_end = 1000
# 扩大摄影棚地面，低机位时不会露出有限地面的边缘。
for obj in scene.objects:
    if obj.name == '无限暗色地面':
        obj.scale.x *= 10
        obj.scale.y *= 10
scene.render.resolution_x = 1200
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.frame_start = 1
scene.frame_end = 288
scene.render.fps = 24
target = Vector((0, 0, 1.8))

# 从高位俯视缓慢下降，同时沿正面左右环绕；回程闭合，避免跳帧。
# 不绕到展台背面，以保持四块正面信息的可见性。
for frame in range(1, 290):
    phase = (frame - 1) / 288 * math.tau
    elevation = math.radians(35 + 17 * math.cos(phase))
    azimuth = math.radians(8 + 27 * math.sin(phase))
    radius = 24
    camera.location = target + Vector((
        radius * math.cos(elevation) * math.sin(azimuth),
        -radius * math.cos(elevation) * math.cos(azimuth),
        radius * math.sin(elevation),
    ))
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.keyframe_insert(data_path='location', frame=frame)
    camera.keyframe_insert(data_path='rotation_euler', frame=frame)

scene.frame_set(1)
scene.render.filepath = str(output / 'frames/orbit_')
bpy.ops.wm.save_as_mainfile(filepath=str(output / 'shot-grid-stage-orbit.blend'))
if '--animation' in sys.argv:
    (output / 'frames').mkdir(exist_ok=True)
    bpy.ops.render.render(animation=True)
else:
    for frame in [1, 73, 145, 217]:
        scene.frame_set(frame)
        scene.render.filepath = str(output / f'preview_{frame:04d}.png')
        bpy.ops.render.render(write_still=True)
