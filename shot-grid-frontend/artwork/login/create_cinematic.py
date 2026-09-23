"""电影片头版：发光光圈、立体胶片与制作流程；使用独立后台进程渲染。"""
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from create_scene import area, box, circle, cylinder, empty, face, line, material, sphere, text

OUT = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
END = 288
TAU = math.tau
random.seed(24)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
scene.name = 'SHOT GRID · 光影引擎'
scene.render.engine = 'BLENDER_EEVEE'
scene.eevee.taa_render_samples = 48
scene.eevee.use_raytracing = False
scene.render.resolution_x = 1200
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = END
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.world.use_nodes = True
world = next(n for n in scene.world.node_tree.nodes if n.type == 'BACKGROUND')
world.inputs[0].default_value = (.006, .012, .024, 1)
world.inputs[1].default_value = .3
scene.view_settings.view_transform = 'AgX'

black = material('黑色陶瓷', (.012,.022,.035), .7,.22)
metal = material('钛合金', (.12,.19,.26), .8,.24)
goldmetal = material('香槟金', (.62,.28,.07), .75,.25)
gold = material('熔金光轨', (1,.31,.035), .2,.2, 6)
cyan = material('电光青', (.015,.7,1), .2,.25, 5)
white = material('光学白', (.72,.88,1), .1,.35, 1.3)
ink = material('深空屏幕', (.004,.014,.022), .25,.36)
mountain = material('远山青', (.018,.16,.22), .3,.4, .3)
front = material('前景青', (.035,.32,.35), .4,.4, .3)
font = bpy.data.fonts.load('C:/Windows/Fonts/msyh.ttc')

def label(body, loc, size, mat=white, parent=None):
    o = text(body, body, loc, size, mat, parent)
    if any(ord(c)>127 for c in body):
        o.data.font=font
    return o

def loop(o, amplitude=.13, phase=0):
    base=o.location.copy()
    rot=Vector(o.rotation_euler)
    for f in range(1,END+2,4):
        t=(f-1)/END*TAU
        o.location=base+Vector((.12*math.sin(t+phase),.22*math.sin(t+phase),amplitude*math.sin(t+phase)))
        o.rotation_euler=rot+Vector((.035*math.sin(t+phase),.055*math.sin(t+phase),.055*math.sin(t+phase)))
        o.keyframe_insert(data_path='location',frame=f)
        o.keyframe_insert(data_path='rotation_euler',frame=f)

# 中央光学核心：实体齿环、虹膜叶片和内嵌微缩山景。
core=empty('中央电影光圈', (0,1,2.75))
core.rotation_euler.z=-.08
for y,r,thick,mat in [(0,2.0,.14,metal),(-.16,1.91,.035,gold),(-.21,1.77,.10,black),(-.30,1.66,.018,cyan),(-.33,1.57,.065,goldmetal)]:
    circle('镜头环', (0,y,0),r,thick,mat,core,'XZ')
for i in range(64):
    a=i*TAU/64
    r=1.99
    o=box('对焦环刻齿',(r*math.cos(a),0,r*math.sin(a)),(.07,.32,.13),goldmetal if i%4==0 else metal,.015,core)
    o.rotation_euler.y=math.pi/2-a
rotor=empty('虹膜旋转总成')
rotor.parent=core
for i in range(12):
    a=i*TAU/12
    coords=[]
    for r,da in [(1.56,0),(1.55,.48),(1.12,.64),(1.06,.26)]:
        coords.append((r*math.cos(a+da),r*math.sin(a+da)))
    face('光圈叶片',coords,-.37,metal if i%2 else goldmetal,rotor)
for f in range(1,END+2,4):
    rotor.rotation_euler.y=.20*math.sin((f-1)/END*TAU)
    rotor.keyframe_insert(data_path='rotation_euler',frame=f)
cylinder('核心画面', (0,.05,0),1.50,.04,ink,core,'Y',96)
cylinder('微缩日轮', (.25,-.04,.40),.52,.02,gold,core,'Y',64)
face('远山', [(-1.4,-.1),(-.8,.7),(-.35,.03),(.18,.62),(.67,-.05),(1.3,.30),(1.40,-.45),(.6,-1.24),(-.6,-1.24),(-1.4,-.4)],-.10,mountain,core)
face('近山', [(-1.30,-.42),(-.72,.01),(-.25,-.35),(.30,.08),(.8,-.42),(1.2,-.3),(.75,-1.12),(0,-1.40),(-.75,-1.1)],-.15,front,core)
label('SHOT GRID',(-1.04,-.47,-.08),.32,white,core)
label('FILM PRODUCTION',(-.89,-.47,-.38),.105,white,core)
loop(core,.08)

# 围绕光圈的三维能量轨道；柔和连续运动而非频闪。
def orbit(t, radius=3.0, phase=0):
    return (radius*math.cos(t), .9+1.4*math.sin(t),2.55+.75*math.sin(t+phase))
for j in range(3):
    coords=[orbit(i/160*TAU,2.65+j*.32,j*.55) for i in range(161)]
    line('环绕光轨',coords,.011 if j else .023,cyan if j==1 else gold)
    # 带渐细尾迹的彗星随轨道流动。
    for k in range(6):
        o=sphere('轨道光流',orbit(0),.045*(1-k/8),cyan if j==1 else gold)
        for f in range(1,END+2,4):
            t=(f-1)/END*TAU+j*1.5-k*.045
            o.location=orbit(t,2.65+j*.32,j*.55)
            o.keyframe_insert(data_path='location',frame=f)

# 曲面胶片横贯画面，实体边框与齿孔形成强透视纵深。
def ribbon(u):
    return Vector((u, -.85+.07*u*u, .55+.42*math.sin(u*.70)))
for dz in [-.37,.37]:
    line('胶片金属边', [tuple(ribbon(-5.5+i*11/100)+Vector((0,0,dz))) for i in range(101)],.045,metal)
    line('胶片发光边', [tuple(ribbon(-5.5+i*11/100)+Vector((0,-.05,dz))) for i in range(101)],.013,gold)
for i in range(58):
    u=-5.4+i*10.8/57
    p=ribbon(u)
    for dz in [-.28,.28]:
        box('胶片齿孔',tuple(p+Vector((0,-.035,dz))),(.095,.03,.075),white,.01)
for i in range(9):
    u=-4.8+i*1.2
    p=ribbon(u)
    tile=empty('胶片镜头帧',p)
    box('胶片帧', (0,0,0),(1.05,.06,.44),ink,.02,tile)
    line('胶片山景',[(-.43,-.05,-.12),(-.20,-.05,.13),(.05,-.05,-.08),(.25,-.05,.1),(.43,-.05,-.12)],.012,cyan,tile)

# 两张大幅悬浮分镜，摆脱仪表盘式四宫格。
def shot(name, loc, angle, version, accent):
    p=empty(name,loc)
    p.rotation_euler.z=angle
    box('悬浮画面框',(0,0,0),(2.65,.14,1.7),metal,.07,p)
    box('悬浮画面',(0,-.09,0),(2.52,.03,1.57),ink,.025,p)
    cylinder('镜头落日',(.55,-.13,.26),.30,.012,accent,p,'Y',48)
    face('镜头山脉',[(-1.2,-.5),(-1.2,-.1),(-.65,.46),(-.15,-.08),(.4,.33),(1.2,-.3),(1.2,-.5)],-.14,mountain,p)
    face('镜头前景',[(-1.2,-.52),(-.65,-.09),(0,-.32),(.55,.02),(1.2,-.30),(1.2,-.52)],-.16,front,p)
    label(version,(-1.13,-.19,-.68),.14,white,p)
    line('分镜亮边',[(-1.29,-.1,.80),(1.29,-.1,.80)],.018,accent,p)
    loop(p,.18,1 if angle>0 else 3)
    return p
s1=shot('分镜输入',(-3.45,.10,3.15),.13,'SH 024  /  V001',gold)
s2=shot('审核最佳版本',(3.5,-.15,2.8),-.17,'V002  /  BEST',cyan)
line('审核框选',[(.06,-.20,-.1),(.80,-.20,-.1),(.80,-.20,.52),(.06,-.20,.52)],.014,gold,s2,closed=True)
circle('审核通过',(-.84,-.21,.43),.17,.012,cyan,s2,'XZ')
line('通过勾',[(-.94,-.23,.42),(-.86,-.23,.34),(-.72,-.23,.51)],.018,cyan,s2)

# 中文流程作为空间中的字幕牌，保留项目辨识度。
for i,(body,sub,x) in enumerate([('分镜 / 资产','SHOTS & ASSETS',-4.6),('任务 / 排期','PRODUCTION',-1.85),('版本 / 审核','VERSION & REVIEW',.80),('最终交付','FINAL DELIVERY',3.4)]):
    p=empty(body,(x,-1.6,-.15))
    label(body,(0,0,0),.23,white,p)
    label(sub,(0,0,-.23),.095,cyan if i>1 else gold,p)
    line('阶段底光',[(0,.03,-.35),(1.6,.03,-.35)],.014,cyan if i>1 else gold,p)

# 稀疏背景光点和纵向光柱增强空间层次。
for i in range(70):
    sphere('深空光尘',(random.uniform(-8,8),random.uniform(3,7),random.uniform(-1,7)),random.uniform(.008,.026),cyan if i%3 else gold)
for x in [-5.7,5.7]:
    line('纵向轮廓光',[(x,3,-1),(x,3,5.6)],.018,cyan)
area('金色侧逆光',(-5,0,7),(0,1,2),2000,(1,.35,.08),5)
area('青色侧逆光',(5,2,6),(0,1,2),2300,(.04,.6,1),5)
area('正面柔光',(0,-6,6),(0,1,2),1100,(.55,.75,1),7)

# 使用透视镜头做可闭环的推进和环绕，避免长时间急速旋转。
bpy.ops.object.camera_add()
camera=bpy.context.object
camera.name='电影片头摄影机'
camera.data.type='PERSP'
camera.data.lens=48
scene.camera=camera
for f in range(1,END+2,4):
    t=(f-1)/END*TAU
    camera.location=(2.5*math.sin(t),-19.8+1.1*math.sin(t),6.0+.4*math.cos(t))
    camera.rotation_euler=(Vector((0,.3,2.1))-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.keyframe_insert(data_path='location',frame=f)
    camera.keyframe_insert(data_path='rotation_euler',frame=f)

# Blender 5 的合成器节点组，辉光由真实高亮材质产生。
tree=bpy.data.node_groups.new('电影柔光合成','CompositorNodeTree')
scene.compositing_node_group=tree
tree.interface.new_socket(name='Image',in_out='OUTPUT',socket_type='NodeSocketColor')
source=tree.nodes.new('CompositorNodeRLayers')
glare=tree.nodes.new('CompositorNodeGlare')
glare.inputs['Type'].default_value='Fog Glow'
glare.inputs['Quality'].default_value='High'
glare.inputs['Strength'].default_value=.45
glare.inputs['Size'].default_value=.3
sink=tree.nodes.new('NodeGroupOutput')
tree.links.new(source.outputs['Image'],glare.inputs['Image'])
tree.links.new(glare.outputs['Image'],sink.inputs['Image'])
scene.frame_set(1)
scene.render.filepath=str(OUT/'frames'/'cinematic_')
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'shot-grid-cinematic.blend'))
scene.render.filepath=str(OUT/'preview.png')
bpy.ops.render.render(write_still=True)
if '--animation' in sys.argv:
    (OUT/'frames').mkdir(exist_ok=True)
    scene.render.filepath=str(OUT/'frames'/'cinematic_')
    bpy.ops.render.render(animation=True)
