import json
import math
import numpy as np
from PIL import Image, ImageDraw
import sys
import os

def render_asset(asset_name):
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bbmodel_path = os.path.join(repo_root, f'projects/cursed_morsels/assets/{asset_name}/model.bbmodel')
    tex_path = os.path.join(repo_root, f'projects/cursed_morsels/assets/{asset_name}/texture.png')
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(repo_root, '.runtime', 'inspector')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'{asset_name}_3d.png')

    if not os.path.exists(bbmodel_path):
        print(f'Model not found: {bbmodel_path}')
        return
        
    with open(bbmodel_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    tex = None
    if os.path.exists(tex_path):
        tex = Image.open(tex_path).convert('RGBA')
        tex_w, tex_h = tex.size
        tex_arr = np.array(tex)
    else:
        tex_w, tex_h = 128, 128
        tex_arr = np.zeros((128, 128, 4), dtype=np.uint8)

    # Resolution
    W, H = 512, 512
    img = Image.new('RGBA', (W, H), (24, 26, 32, 255))
    draw = ImageDraw.Draw(img)
    
    # Camera angles: Isometric-like perspective
    yaw = math.radians(35)
    pitch = math.radians(25)
    
    cos_y, sin_y = math.cos(yaw), math.sin(yaw)
    cos_p, sin_p = math.cos(pitch), math.sin(pitch)
    
    def project(pt):
        x, y, z = pt
        # rotate yaw
        x1 = x * cos_y + z * sin_y
        z1 = -x * sin_y + z * cos_y
        # rotate pitch
        y2 = y * cos_p - z1 * sin_p
        z2 = y * sin_p + z1 * cos_p
        return x1, y2, z2

    all_polys = []
    
    for el in data.get('elements', []):
        el_type = el.get('type', 'mesh')
        origin = np.array(el.get('origin', [0, 0, 0]), dtype=float)
        
        if el_type == 'mesh':
            verts_dict = el.get('vertices', {})
            faces_dict = el.get('faces', {})
            for f_name, f_data in faces_dict.items():
                v_ids = f_data.get('vertices', [])
                if len(v_ids) < 3:
                    continue
                v_coords = []
                for vid in v_ids:
                    if vid in verts_dict:
                        v_coords.append(np.array(verts_dict[vid], dtype=float) + origin)
                if len(v_coords) < 3:
                    continue
                # sample UV for face color
                uv_map = f_data.get('uv', {})
                sample_color = (180, 180, 180, 255)
                if tex is not None and uv_map:
                    uv_pts = list(uv_map.values())
                    if len(uv_pts) > 0:
                        u_avg = sum(p[0] for p in uv_pts) / len(uv_pts)
                        v_avg = sum(p[1] for p in uv_pts) / len(uv_pts)
                        px = int(np.clip(u_avg * tex_w / 16.0 if u_avg <= 16 else u_avg, 0, tex_w - 1))
                        py = int(np.clip(v_avg * tex_h / 16.0 if v_avg <= 16 else v_avg, 0, tex_h - 1))
                        sample_color = tuple(tex_arr[py, px])
                all_polys.append((v_coords, sample_color))
                
        elif el_type == 'cube':
            f_from = np.array(el.get('from', [0, 0, 0]), dtype=float)
            f_to = np.array(el.get('to', [0, 0, 0]), dtype=float)
            # 8 corners
            c = [
                [f_from[0], f_from[1], f_from[2]],
                [f_to[0], f_from[1], f_from[2]],
                [f_to[0], f_to[1], f_from[2]],
                [f_from[0], f_to[1], f_from[2]],
                [f_from[0], f_from[1], f_to[2]],
                [f_to[0], f_from[1], f_to[2]],
                [f_to[0], f_to[1], f_to[2]],
                [f_from[0], f_to[1], f_to[2]],
            ]
            cube_faces = [
                ([c[0], c[1], c[2], c[3]], 'north'),
                ([c[5], c[4], c[7], c[6]], 'south'),
                ([c[4], c[0], c[3], c[7]], 'west'),
                ([c[1], c[5], c[6], c[2]], 'east'),
                ([c[3], c[2], c[6], c[7]], 'up'),
                ([c[4], c[5], c[1], c[0]], 'down'),
            ]
            for f_pts, f_name in cube_faces:
                f_data = el.get('faces', {}).get(f_name, {})
                uv = f_data.get('uv', [0, 0, 16, 16])
                sample_color = (180, 180, 180, 255)
                if tex is not None:
                    u_avg = (uv[0] + uv[2]) * 0.5
                    v_avg = (uv[1] + uv[3]) * 0.5
                    px = int(np.clip(u_avg * tex_w / 16.0 if u_avg <= 16 else u_avg, 0, tex_w - 1))
                    py = int(np.clip(v_avg * tex_h / 16.0 if v_avg <= 16 else v_avg, 0, tex_h - 1))
                    sample_color = tuple(tex_arr[py, px])
                all_polys.append(([np.array(p) for p in f_pts], sample_color))

    if not all_polys:
        print('No polys found!')
        return

    # Find bounding box
    all_pts = [p for poly, _ in all_polys for p in poly]
    proj_pts = [project(p) for p in all_pts]
    xs = [p[0] for p in proj_pts]
    ys = [p[1] for p in proj_pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    cx = (min_x + max_x) * 0.5
    cy = (min_y + max_y) * 0.5
    span = max(max_x - min_x, max_y - min_y, 1.0)
    scale = (W * 0.75) / span
    
    # Sort polys painter's algorithm
    poly_depth = []
    for poly, col in all_polys:
        proj = [project(p) for p in poly]
        avg_z = sum(p[2] for p in proj) / len(proj)
        # 2D screen points
        screen_pts = [(W * 0.5 + (p[0] - cx) * scale, H * 0.5 - (p[1] - cy) * scale) for p in proj]
        # Calculate 3D normal for simple lighting
        v0, v1, v2 = poly[0], poly[1], poly[2]
        norm = np.cross(v1 - v0, v2 - v0)
        norm_len = np.linalg.norm(norm)
        if norm_len > 1e-6:
            norm /= norm_len
        else:
            norm = np.array([0, 1, 0])
        # Light dot
        light = 0.5 + 0.5 * float(np.dot(norm, np.array([0.4, 0.7, 0.5])))
        shaded_col = (
            int(np.clip(col[0] * light, 0, 255)),
            int(np.clip(col[1] * light, 0, 255)),
            int(np.clip(col[2] * light, 0, 255)),
            255
        )
        poly_depth.append((avg_z, screen_pts, shaded_col))
        
    poly_depth.sort(key=lambda x: x[0])
    
    for _, s_pts, s_col in poly_depth:
        draw.polygon(s_pts, fill=s_col, outline=(30, 30, 35, 120))
        
    img.save(out_path)
    print(f'Rendered {asset_name} to {out_path}')

if __name__ == '__main__':
    render_asset(sys.argv[1])
