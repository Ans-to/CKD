"""Procedural Blender-only visual production for The Rise and Fall of Nokia.

No image, video, font, texture, or web asset is loaded. All scenes are meshes,
curves, materials, particles, lights, camera animation, and Blender text.
Run with Python containing bpy 4.5+: python scripts/blender/nokia_documentary_15m.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "scripts/blender/nokia_documentary_15m.json"
PALETTE = {
    "navy": (0.012, 0.024, 0.052, 1), "deep": (0.004, 0.008, 0.02, 1),
    "blue": (0.06, 0.23, 0.42, 1), "cyan": (0.12, 0.72, 0.86, 1),
    "teal": (0.12, 0.58, 0.48, 1), "gold": (0.98, 0.54, 0.16, 1),
    "paper": (0.88, 0.91, 0.95, 1), "muted": (0.40, 0.53, 0.67, 1),
    "green": (0.24, 0.72, 0.43, 1), "red": (0.83, 0.22, 0.22, 1),
    "silver": (0.42, 0.52, 0.64, 1), "rubber": (0.035, 0.05, 0.07, 1),
}


def material(name, color, metallic=0.0, roughness=0.45, emission=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = color
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        key = "Emission Color" if "Emission Color" in bsdf.inputs else "Emission"
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = color
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission
    return m


def cube(name, loc, size, mat, bevel=0.04):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        b = o.modifiers.new("Manufactured edge radii", "BEVEL")
        b.width = min(bevel, min(size) * 0.22)
        b.segments = 2
        if max(size)>0.45:
            o.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
    o.data.materials.append(mat)
    return o


def sphere(name, loc, scale, mat, segments=24, rings=16):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, radius=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return o


def text(body, loc, size, mat, name=None, align="CENTER"):
    c = bpy.data.curves.new(name or body[:32], "FONT")
    c.body, c.size, c.align_x, c.extrude = body, size, align, 0.001
    o = bpy.data.objects.new(name or body[:32], c)
    bpy.context.collection.objects.link(o)
    o.location = loc
    o.rotation_euler.x = math.radians(90)
    o.data.materials.append(mat)
    return o


def curve(name, points, mat, radius=0.025, resolution=2):
    c = bpy.data.curves.new(name, "CURVE")
    c.dimensions, c.resolution_u, c.bevel_depth, c.bevel_resolution = "3D", resolution, radius, 3
    sp = c.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for p, xyz in zip(sp.points, points):
        p.co = (*xyz, 1)
    o = bpy.data.objects.new(name, c)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(mat)
    return o


def phone(name, x, z, scale, mats, touch=False, clamshell=False):
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root.location = (x, 0, z)
    body, trim, screen, key = mats
    w, h = ((0.92, 2.15) if not touch else (1.16, 2.36))
    shell = cube(name + " shell", (x, 0, z), (w, 0.26, h), body, 0.11)
    parts = [shell]
    if touch:
        parts += [cube(name+" glass bezel",(x,-0.145,z+0.02),(w*0.82,0.035,h*0.80),trim,0.08),
                  cube(name+" glass",(x,-0.17,z+0.02),(w*0.73,0.018,h*0.70),screen,0.06)]
        for r in range(4):
            for c in range(3):
                parts.append(cube(name+f" UI tile {r}-{c}",(x+(c-1)*0.22,-0.19,z+0.43-r*0.28),(0.13,0.025,0.13),key,0.035))
    else:
        parts += [cube(name+" display trim",(x,-0.15,z+0.52),(w*0.66,0.06,0.58),trim,0.06),
                  cube(name+" display",(x,-0.185,z+0.52),(w*0.55,0.018,0.45),screen,0.025),
                  cube(name+" earpiece",(x,-0.16,z+h*0.38),(0.28,0.045,0.045),trim,0.02),
                  cube(name+" compact antenna",(x+0.28,0.03,z+h*0.5+0.07),(0.07,0.07,0.16),trim,0.025),
                  text("12:08",(x,-0.205,z+0.56),0.12,mats[3],name+" monochrome clock")]
        key_labels=("1","2","3","4","5","6","7","8","9","*","0","#")
        for r in range(4):
            for c in range(3):
                cx=x+(c-1)*0.22; kz=z-0.22-r*0.22
                parts.append(cube(name+f" key {r}-{c}",(cx,-0.17,kz),(0.15,0.08,0.12),key,0.035))
                parts.append(text(key_labels[r*3+c],(cx,-0.22,kz-0.025),0.065,mats[2],name+f" key legend {r}-{c}"))
    if clamshell:
        seam=cube(name+" hinge",(x,-0.01,z),(w*0.9,0.29,0.07),trim,0.025); parts.append(seam)
    for o in parts:
        world=o.matrix_world.copy(); o.parent=root; o.matrix_world=world
    return root


def set_visibility(objects, start, end, total):
    a=max(1,start); b=max(a+2,end)
    for o in objects:
        o.hide_render=True; o.keyframe_insert(data_path="hide_render",frame=max(1,a-1))
        o.hide_render=False; o.keyframe_insert(data_path="hide_render",frame=a)
        o.hide_render=False; o.keyframe_insert(data_path="hide_render",frame=max(a,b-1))
        if b < total:
            o.hide_render=True; o.keyframe_insert(data_path="hide_render",frame=b)


def phone_lineup(mats, count=5):
    out=[]
    for i in range(count):
        x=(i-(count-1)/2)*1.65
        p=phone(f"Procedural phone generation {i+1}",x,0,1,mats,touch=i>=4,clamshell=i==2)
        p.rotation_euler.z=(i-2)*0.045
        out.append(p)
        cube(f"Rotating display plinth {i+1}",(x,0,-1.48),(1.22,1.0,0.30),mats[1],0.12)
        cyl=None
    return out


def build_scene_group(idx, entry, mats, start, end, total_frames, render_fps):
    before=set(bpy.data.objects)
    m=mats
    accent=[m["gold"],m["cyan"],m["teal"],m["green"],m["red"]][idx%5]
    title_mat=m["paper"]
    text(entry["title"].upper(),(0,-3.2,3.2),0.56,title_mat,"Scene title")
    text(f"{idx+1:02d}  /  13",(-5.7,-3.2,3.0),0.2,m["muted"],"Chapter index",align="LEFT")

    phone_mats=(m["phone"],m["trim"],m["glass"],m["silver"])
    touch_mats=(m["touch"],m["trim"],m["glass"],m["cyan"])
    if idx==0:
        p=phone("Classic generic handset",0,0.05,1,phone_mats,touch=False)
        p.rotation_euler.z=-0.12
        cube("Circular reveal dais",(0,0,-1.55),(3.2,2.3,0.35),m["trim"],0.18)
        for i in range(24):
            ang=i*math.tau/24; sphere("Procedural dust",(math.cos(ang)*4.4,0.8,math.sin(ang)*2.2),(0.025,0.025,0.025),m["cyan"],8,6)
    elif idx==1:
        cube("Paper mill main hall",(-1.7,0,0),(4.8,2.4,2.5),m["paperwood"],0.18)
        cube("Mill roof",(-1.7,0,1.45),(5.0,2.6,0.25),m["roof"],0.08)
        for i in range(3): cube(f"Mill windows {i}",(-3.1+i*1.4,-1.23,0.1),(0.58,0.07,0.88),m["glass"],0.04)
        for x,h in ((-3.0,3.8),(-0.8,4.7),(1.0,3.7)):
            cube("Mill chimney",(x,0.15,h/2),(0.48,0.55,h),m["brick"],0.08)
            for j in range(7): sphere("Procedural steam",(x+0.2*math.sin(j),0.2,h+0.45+j*0.35),(0.35+j*0.05,0.3,0.26),m["smoke"],12,8)
        curve("Nokianvirta river",[(-6,-1.4,-1.0),(-3,-1.2,-1.15),(0,-1.0,-1.0),(3,-0.7,-1.2),(6,-0.4,-1.0)],m["cyan"],0.3)
        for i in range(9):
            x=-5.0+i*1.25
            cube("Timber stack",(x,0.8,-1.25),(0.8,0.5,0.3),m["paperwood"],0.05)
        # Native cone meshes form a sparse Finnish pine line; trunks and branches
        # are all Blender geometry, not imported background art.
        for i,x in enumerate((-5.3,-4.1,3.5,4.7,5.7)):
            cube("Pine trunk",(x,1.0,-0.15),(0.18,0.18,1.5),m["brick"],0.03)
            for tier in range(3):
                bpy.ops.mesh.primitive_cone_add(vertices=12,radius1=0.8-tier*0.15,radius2=0.03,depth=1.45,location=(x,1.0,0.7+tier*0.72))
                pine=bpy.context.object; pine.name="Procedural pine tier"; pine.data.materials.append(m["green"])
        # A water wheel is a modeled object on the mill race, with visible spokes.
        bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=1.15,depth=0.18,location=(-4.35,-1.35,-0.2),rotation=(math.pi/2,0,0))
        wheel=bpy.context.object; wheel.name="Paper mill water wheel"; wheel.data.materials.append(m["trim"])
        for j in range(12):
            a=math.tau*j/12
            curve("Water-wheel spoke",[(-4.35,-1.48,-0.2),(-4.35+math.cos(a)*1.05,-1.48,-0.2+math.sin(a)*1.05)],m["gold"],0.035)
    elif idx==2:
        phone_lineup(phone_mats,5)
        text("ANALOG  →  DIGITAL  →  POCKET",(0,-3.2,2.55),0.26,m["cyan"],"Evolution label")
    elif idx==3:
        sphere("Procedural network globe",(0,0,0),(2.65,2.65,2.65),m["ocean"],48,32)
        # Coarse, explicitly schematic land silhouettes are native mesh geometry.
        # Longitudes are projected toward the camera-facing negative-Y hemisphere.
        continents={
            "North America":[(-166,70),(-145,72),(-128,58),(-124,45),(-116,32),(-105,24),(-93,18),(-82,25),(-78,8),(-97,15),(-112,24),(-130,43),(-151,58)],
            "South America":[(-80,10),(-68,8),(-58,-7),(-50,-20),(-55,-36),(-66,-55),(-75,-43),(-79,-20)],
            "Eurasia":[(-10,70),(20,72),(45,60),(68,58),(93,62),(120,56),(150,48),(160,38),(137,31),(120,16),(103,8),(83,18),(65,24),(48,35),(29,36),(17,46),(3,42),(-8,53)],
            "Africa":[(-17,35),(4,37),(28,31),(48,12),(41,-10),(33,-31),(17,-35),(4,-25),(-5,-5),(-15,16)],
            "Australia":[(112,-11),(132,-10),(153,-18),(146,-34),(128,-40),(114,-31)],
            "Greenland":[(-53,82),(-31,79),(-21,68),(-39,59),(-58,63),(-68,74)],
        }
        radius=2.74
        def globe_point(lon,lat):
            lo,la=math.radians(lon),math.radians(lat)
            return (radius*math.cos(la)*math.sin(lo),-radius*math.cos(la)*math.cos(lo),radius*math.sin(la))
        for land_name,outline in continents.items():
            ring_ll=[]
            for q,(lon1,lat1) in enumerate(outline):
                lon2,lat2=outline[(q+1)%len(outline)]
                steps=max(1,math.ceil(max(abs(lon2-lon1),abs(lat2-lat1))/6))
                for k in range(steps):
                    t=k/steps; ring_ll.append((lon1+(lon2-lon1)*t,lat1+(lat2-lat1)*t))
            center_lon=sum(p[0] for p in outline)/len(outline); center_lat=sum(p[1] for p in outline)/len(outline)
            verts=[globe_point(center_lon,center_lat)]
            radial_layers=6
            for layer in range(1,radial_layers+1):
                t=layer/radial_layers
                for lon,lat in ring_ll:
                    verts.append(globe_point(center_lon+(lon-center_lon)*t,center_lat+(lat-center_lat)*t))
            n=len(ring_ll); faces=[]
            for i in range(n): faces.append((0,1+i,1+(i+1)%n))
            for layer in range(1,radial_layers):
                inner=1+(layer-1)*n; outer=1+layer*n
                for i in range(n):
                    nxt=(i+1)%n
                    faces.extend(((inner+i,outer+i,outer+nxt),(inner+i,outer+nxt,inner+nxt)))
            mesh=bpy.data.meshes.new(land_name+" schematic mesh"); mesh.from_pydata(verts,[],faces); mesh.materials.append(m["green"]); mesh.update()
            ob=bpy.data.objects.new(land_name+" schematic continent",mesh); bpy.context.collection.objects.link(ob)
        text("SCHEMATIC GLOBAL NETWORK",(0,-3.3,-2.8),0.20,m["muted"],"Globe context label")
        for lat in range(-60,61,30):
            r=2.66*math.cos(math.radians(lat)); z=2.66*math.sin(math.radians(lat))
            pts=[(r*math.cos(a),r*math.sin(a),z) for a in [math.radians(k) for k in range(0,361,5)]]
            curve("Globe latitude",pts,m["cyan"],0.012)
        for lon in range(0,180,30):
            pts=[]
            for k in range(-90,91,4):
                a=math.radians(k); b=math.radians(lon)
                pts.append((2.67*math.cos(a)*math.cos(b),2.67*math.cos(a)*math.sin(b),2.67*math.sin(a)))
            curve("Globe longitude",pts,m["silver"],0.012)
        for a,b in ((-1.8,0.7),(0.2,1.9),(1.4,-0.8),(-0.4,-1.6)):
            curve("Animated route",[(a,-2.3,0),(a*0.45,-2.75,1.3),(b,-2.3,0.2)],m["gold"],0.035)
        for i in range(5):
            cube("Q4 2007 market-share bar",(-4.6+i*0.65,0,-1.3+i*0.24),(0.36,0.42,0.5+i*0.24),m["gold"] if i==4 else m["blue"],0.04)
        text("~40%  |  NOKIA Q4 2007 ESTIMATE",(0,-3.3,-2.2),0.28,m["paper"],"Market share annotation")
    elif idx==4:
        phone_lineup(phone_mats,5)
        curve("Peak-era timeline",[(-5.0,-1.35,-2.45),(5.0,-1.35,-2.45)],m["gold"],0.035)
        for j,label in enumerate(("1982","1991","1998","2007")):
            x=-4.2+j*2.8
            sphere("Timeline milestone",(x,-1.4,-2.45),(0.10,0.10,0.10),m["cyan"],12,8)
            text(label,(x,-1.45,-2.78),0.17,m["paper"],"Timeline year")
        text("A GENERIC PRODUCT LINEUP — NOT EXACT MODEL REPLICAS",(0,-3.15,2.55),0.16,m["muted"],"Product caveat")
        for i in range(5):
            sphere("Rotating product plinth",((i-2)*1.65,1,-1.6),(0.73,0.73,0.16),m["gold"],24,12)
    elif idx==5:
        left=phone("Physical-key smartphone",-2,0,1,phone_mats,False)
        right=phone("Touchscreen smartphone",2,0,1,touch_mats,True)
        curve("Interface transformation arc",[(-2,-1,0),(0,-2,1.5),(2,-1,0)],m["gold"],0.06)
        text("HARDWARE  →  SOFTWARE EXPERIENCE",(0,-3.25,-2.1),0.25,m["paper"],"Transformation label")
    elif idx in (6,7):
        n=18 if idx==6 else 28
        nodes=[]
        for i in range(n):
            x=((i%7)-3)*1.25; z=(i//7-1)*1.18+0.1*math.sin(i)
            ob=sphere("Ecosystem node" if idx==6 else "Software node",(x,0,z),(0.16,0.16,0.16),m["cyan"] if i%3 else accent,12,8)
            nodes.append((x,z))
        for i,(x,z) in enumerate(nodes):
            for j in range(i+1,min(i+4,len(nodes))):
                xx,zz=nodes[j]
                curve("App ecosystem link" if idx==6 else "Branching software link",[(x,0,z),(xx,0,zz)],m["silver"] if idx==6 else m["red"],0.012)
        for i in range(7):
            cube("Application tile",(-3+i, -0.9, -2.2),(0.55,0.18,0.55),m["gold"] if i%2 else m["teal"],0.12)
        text("USERS  •  DEVELOPERS  •  SERVICES",(0,-3.2,-2.75),0.25,m["paper"],"Ecosystem labels")
    elif idx==8:
        # Analyst-estimated smartphone share, not total-device share. The years
        # are deliberately sparse; no interpolated values are implied.
        years=("2007","2008","2009","2010","H1 2013")
        values=(49.4,43.7,41.1,34.2,3.0)
        points=[]
        for i,(year,value) in enumerate(zip(years,values)):
            x=-4.2+i*2.1; height=value/50.0*3.8
            cube(f"Nokia smartphone market-share {year}",(x,0,-1.45+height/2),(0.82,0.65,height),m["cyan"] if i<2 else m["red"],0.08)
            text(f"{value:g}%",(x,-0.48,-1.45+height+0.27),0.22,m["paper"],f"Share value {year}")
            text(year,(x,-0.55,-1.95),0.17,m["paper"],f"Year {year}")
            points.append((x,-0.82,-1.45+height))
        curve("Analyst share trend",points,m["gold"],0.045)
        text("SMARTPHONE MARKET SHARE  •  GARTNER ESTIMATES",(0,-3.0,2.35),0.20,m["paper"],"Chart caveat")
        text("SOURCE: BBC SUMMARY OF GARTNER DATA  |  NOT TOTAL HANDSET SHARE",(0,-3.0,2.02),0.14,m["muted"],"Chart source")
    elif idx==9:
        cube("Nokia corporate building",(-2,0,0),(3.0,2.2,4.4),m["blue"],0.12)
        cube("Microsoft corporate building",(2.0,0,0),(3.0,2.2,4.4),m["teal"],0.12)
        for x in (-2,2):
            for row in range(7):
                for col in range(3): cube("Office window",(x+(col-1)*0.72,-1.14,-1.8+row*0.54),(0.32,0.04,0.24),m["glass"],0.02)
        curve("Transaction bridge",[(-0.4,-1.5,0),(0,-1.8,2.2),(0.4,-1.5,0)],m["gold"],0.12)
        text("€5.44 BILLION  |  ANNOUNCED 2013  •  CLOSED 2014",(0,-3.5,-2.65),0.20,m["paper"],"Deal value and dates")
    elif idx==10:
        labels=("SOFTWARE","ECOSYSTEM","ORGANIZATION","STRATEGY","EXPECTATIONS")
        for i,label in enumerate(labels):
            x=(i-2)*2.15
            cube("Lesson plinth",(x,0,-1.25),(1.55,1.0,0.48),m["trim"],0.12)
            ob=sphere("Lesson concept",(x,0,0.1),(0.55,0.55,0.55),[m["cyan"],m["gold"],m["teal"],m["red"],m["green"]][i],20,12)
            text(label,(x,-1.05,-0.65),0.14,m["paper"],"Lesson label")
    elif idx==11:
        for i in range(5):
            x=-4+i*2
            cube("Telecom tower mast",(x,0,0.2),(0.14,0.14,4.5),m["silver"],0.02)
            for z in (-1.4,-0.3,0.8,1.9):
                curve("Tower brace",[(x-0.8,0,z),(x+0.8,0,z),(x,0,z+0.85)],m["cyan"],0.035)
            for y in (-0.2,0.2): cube("Sector antenna",(x+0.18,y,1.6),(0.24,0.2,0.9),m["paper"],0.05)
        for i in range(5): curve("Fiber route",[(-5,-0.4,-1.5+i*0.18),(0,-0.6,-1.9+i*0.16),(5,-0.3,-1.4+i*0.18)],m["gold" if i%2 else "teal"],0.025)
        text("5G  •  NETWORKS  •  SOFTWARE  •  CONNECTIVITY",(0,-3.2,-2.55),0.22,m["paper"],"Modern Nokia label")
    else:
        phone("Classic generic handset",-2.0,0.0,1,phone_mats,False)
        phone("Modern generic touchscreen",2.0,0.0,1,touch_mats,True)
        curve("Continuity orbit",[(-3,-0.4,-1.4),(-1,-1.2,-2.0),(1,-1.2,-2.0),(3,-0.4,-1.4)],m["gold"],0.045)
        text("A MARKET CAN CHANGE FASTER THAN A LEADER",(0,-3.2,2.7),0.34,m["paper"],"Final message")

    # Bake the chapter's native geometry, text and curves into one mesh object.
    # Material slots and shape are retained; collapsing Blender object/draw-call
    # overhead is important for long EEVEE renders on CPU-only hosted runners.
    renderables=[o for o in bpy.data.objects if o not in before and o.type in {"MESH","CURVE","FONT"}]
    for obj in renderables:
        if obj.parent:
            world_matrix=obj.matrix_world.copy(); obj.parent=None; obj.matrix_world=world_matrix
    bpy.ops.object.select_all(action="DESELECT")
    for obj in renderables: obj.select_set(True)
    if renderables:
        bpy.context.view_layer.objects.active=renderables[0]
        bpy.ops.object.convert(target="MESH")
        renderables=list(bpy.context.selected_objects)
        if len(renderables)>1:
            bpy.ops.object.join()
        merged=bpy.context.view_layer.objects.active
        created=[merged] if merged else []
    else:
        created=[]
    bpy.ops.object.select_all(action="DESELECT")
    set_visibility(created,start,end,total_frames)
    root=bpy.data.objects.new(f"Scene motion root {idx+1}",None)
    bpy.context.collection.objects.link(root)
    for obj in created:
        world_matrix=obj.matrix_world.copy()
        obj.parent=root
        obj.matrix_world=world_matrix
    # Animate model groups as a whole for a slow, continuous camera-like drift.
    root.rotation_euler.z=0.0; root.keyframe_insert(data_path="rotation_euler",frame=start)
    root.rotation_euler.z=0.035; root.keyframe_insert(data_path="rotation_euler",frame=end)
    root.scale=(0.001,0.001,0.001); root.keyframe_insert(data_path="scale",frame=start)
    transition=max(1,round(0.6*render_fps))
    root.scale=(1,1,1); root.keyframe_insert(data_path="scale",frame=min(end,start+transition))
    if end < total_frames:
        root.scale=(1,1,1); root.keyframe_insert(data_path="scale",frame=max(start,end-transition))
        root.scale=(0.001,0.001,0.001); root.keyframe_insert(data_path="scale",frame=end)
    return root


def build(timings_path, output_path, preview_seconds=0):
    spec=json.loads(SPEC.read_text())
    timings=json.loads(Path(timings_path).read_text())
    total_seconds=float(preview_seconds or 900)
    fps=int(spec["fps"])
    total_frames=round(total_seconds*fps)
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.materials): bpy.data.materials.remove(block)
    m={k:material(k,v,metallic=0.25 if k in ("silver","trim","phone","touch") else 0.0,roughness=0.32 if k in ("glass","phone","touch") else 0.58,emission=0.12 if k in ("cyan","gold","teal") else 0.0) for k,v in PALETTE.items()}
    m.update({
        "phone":material("Graphite polymer",PALETTE["rubber"],0.35,0.26),
        "touch":material("Modern anodized titanium",PALETTE["silver"],0.68,0.24),
        "trim":material("Brushed metal trim",PALETTE["silver"],0.72,0.25),
        "glass":material("Dark display glass",(0.006,0.022,0.04,1),0.12,0.16,0.06),
        "paperwood":material("Warm timber and paper stock",(0.31,0.19,0.09,1),0,0.82),
        "roof":material("Mill roof",(0.12,0.16,0.19,1),0.2,0.65),
        "brick":material("Industrial brick",(0.30,0.12,0.09,1),0,0.8),
        "smoke":material("Steam volume proxy",(0.46,0.53,0.60,1),0,0.85),
        "ocean":material("Globe ocean",(0.012,0.08,0.18,1),0.2,0.55),
    })
    scene=bpy.context.scene
    world=bpy.data.worlds.new("Procedural midnight studio"); world.use_nodes=True
    world.node_tree.nodes["Background"].inputs["Color"].default_value=PALETTE["navy"]
    world.node_tree.nodes["Background"].inputs["Strength"].default_value=0.22; scene.world=world
    floor=cube("Infinite procedural studio floor",(0,0,-3.4),(200,200,0.2),m["navy"],0.01)
    camdata=bpy.data.cameras.new("Cinematic camera"); camera=bpy.data.objects.new("Cinematic camera",camdata); bpy.context.collection.objects.link(camera); scene.camera=camera
    target=bpy.data.objects.new("Camera focus target",None); bpy.context.collection.objects.link(target)
    con=camera.constraints.new("TRACK_TO"); con.target=target; con.track_axis="TRACK_NEGATIVE_Z"; con.up_axis="UP_Y"
    for frame,x in ((1,-0.45),(total_frames,0.45)):
        camera.location=(x,-18,7.8); camera.keyframe_insert(data_path="location",frame=frame)
        target.location=(0,0,0); target.keyframe_insert(data_path="location",frame=frame)
    camdata.lens=52
    for name,loc,power,color,size in (("Warm key",(-7,-9,10),1800,(1.0,0.72,0.48),7),("Cool fill",(7,-5,4),1300,(0.35,0.60,1.0),6),("Rim",(0,5,8),2200,(0.15,0.75,1.0),5)):
        ld=bpy.data.lights.new(name,"AREA"); ld.energy=power; ld.color=color; ld.shape="DISK"; ld.size=size
        lo=bpy.data.objects.new(name,ld); bpy.context.collection.objects.link(lo); lo.location=loc; lo.rotation_euler=(Vector((0,0,0))-lo.location).to_track_quat("-Z","Y").to_euler()
    # Sparse ambient motes are one joined native mesh, not 100 per-frame draw calls.
    ambient=[]
    for i in range(24):
        x=math.sin(i*12.9898)*5.5; y=1.5+math.cos(i*8.233)*1.2; z=-1.3+(i%17)*0.19
        ambient.append(sphere("Procedural ambient mote",(x,y,z),(0.012,0.012,0.012),m["cyan"],8,6))
    if ambient:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in ambient: obj.select_set(True)
        bpy.context.view_layer.objects.active=ambient[0]
        bpy.ops.object.join()
        bpy.ops.object.select_all(action="DESELECT")
    cursor=1
    entries=spec["scenes"][:len(timings["scenes"])]
    for idx,entry in enumerate(entries):
        duration=float(timings["scenes"][idx]["duration_seconds"])
        start=cursor; end=min(total_frames,cursor+round(duration*fps))
        build_scene_group(idx,entry,m,start,end,total_frames,fps)
        cursor=end
    scene.render.engine="BLENDER_EEVEE_NEXT"
    # Render the procedural scene directly at the final 30-fps cadence, then use
    # Blender VSE only for audio assembly and upscale to the 1280x720 delivery.
    scene.eevee.taa_render_samples=1
    scene.render.resolution_x=int(spec["resolution"][0]); scene.render.resolution_y=int(spec["resolution"][1]); scene.render.resolution_percentage=50
    scene.render.fps=fps; scene.render.fps_base=1.0
    scene.frame_start=1; scene.frame_end=total_frames
    scene.render.image_settings.file_format="FFMPEG"
    scene.render.ffmpeg.format="MPEG4"; scene.render.ffmpeg.codec="H264"; scene.render.ffmpeg.constant_rate_factor="HIGH"; scene.render.ffmpeg.ffmpeg_preset="GOOD"
    scene.render.filepath=str(output_path); scene.render.use_file_extension=True
    scene.view_settings.view_transform="AgX"
    scene.render.threads_mode="AUTO"
    # Smooth camera and root motion; deliberate chapter cuts stay on exact narration boundaries.
    for obj in bpy.context.scene.objects:
        if obj.animation_data and obj.animation_data.action:
            for fc in obj.animation_data.action.fcurves:
                for kp in fc.keyframe_points: kp.interpolation="BEZIER"
    scene.frame_set(1)
    bpy.ops.render.render(animation=True)
    return total_frames


def cli_args():
    argv=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else sys.argv[1:]
    result={"timings":"output/timings.json","output":"output/visuals.mp4","preview_seconds":0}
    i=0
    while i<len(argv):
        if argv[i] in ("--timings","--output","--preview-seconds") and i+1<len(argv):
            key={"--timings":"timings","--output":"output","--preview-seconds":"preview_seconds"}[argv[i]]
            result[key]=float(argv[i+1]) if key=="preview_seconds" else argv[i+1]; i+=2
        else: i+=1
    return result


if __name__=="__main__":
    a=cli_args(); build(a["timings"],a["output"],a["preview_seconds"])
