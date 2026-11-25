"""glTF 2.0 delivery from serialized BBModel geometry, UVs, rigs and numeric clips.

Specification: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
No modeling, UV or paint recipes are executed.
"""
from __future__ import annotations

import base64
import json
import math
import struct
from pathlib import Path
import numpy as np
from PIL import Image

from lib.animation_sampling import sample
from lib.polygon_decomposition import newell_normal, temporary_triangle_indices


def quaternion(degrees):
    x, y, z = [math.radians(float(value)) / 2 for value in degrees]
    sx, sy, sz, cx, cy, cz = math.sin(x), math.sin(y), math.sin(z), math.cos(x), math.cos(y), math.cos(z)
    return [sx*cy*cz-cx*sy*sz, cx*sy*cz+sx*cy*sz, cx*cy*sz-sx*sy*cz, cx*cy*cz+sx*sy*sz]


def matrix(node):
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    result = np.eye(4)
    result[:3, :3] = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                      [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                      [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
    result[:3, :3] *= node.get("scale", [1, 1, 1])
    result[:3, 3] = node.get("translation", [0, 0, 0])
    return result


def cube_faces(element):
    start, end = element["from"], element["to"]
    inflate = element.get("inflate", 0)
    x0, y0, z0 = [min(a, b)-inflate for a, b in zip(start, end)]
    x1, y1, z1 = [max(a, b)+inflate for a, b in zip(start, end)]
    return {
        "north": [(x1,y0,z0),(x0,y0,z0),(x0,y1,z0),(x1,y1,z0)],
        "south": [(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)],
        "west": [(x0,y0,z0),(x0,y0,z1),(x0,y1,z1),(x0,y1,z0)],
        "east": [(x1,y0,z1),(x1,y0,z0),(x1,y1,z0),(x1,y1,z1)],
        "up": [(x0,y1,z1),(x1,y1,z1),(x1,y1,z0),(x0,y1,z0)],
        "down": [(x0,y0,z0),(x1,y0,z0),(x1,y0,z1),(x0,y0,z1)]}


# glTF sampler (magFilter, minFilter): NEAREST for pixel art; LINEAR + LINEAR_MIPMAP_LINEAR for painted textures.
GLTF_FILTERS = {"nearest": (9728, 9728), "linear": (9729, 9987)}


class GLBWriter:
    def __init__(self, data, *, texture=None, scope=None, scale=1/16, fps=60, texture_filter="nearest"):
        self.data, self.texture, self.scope = data, texture, Path(scope).resolve() if scope else None
        if not math.isfinite(scale) or scale <= 0 or fps <= 0:
            raise ValueError("Scale and sampling fps must be positive")
        self.scale, self.fps = scale, fps
        if texture_filter not in GLTF_FILTERS:
            raise ValueError("texture_filter must be nearest or linear")
        self.texture_filter = texture_filter
        self.doc = {"asset": {"version": "2.0", "generator": "NoctAssetForge3D"},
                    "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [], "meshes": [],
                    "bufferViews": [], "accessors": []}
        self.buffer = bytearray()
        self.ids, self.parents, self.rest, self.owners = {}, {}, {}, {}
        self.elements = {element["uuid"]: element for element in data.get("elements", [])}
        self.groups = {group["uuid"]: group for group in data.get("groups", [])}
        self.pending = []
        self.handled = set()
        self.node({"name": data.get("name", "asset")})

    def node(self, data, parent=None):
        index = len(self.doc["nodes"])
        self.doc["nodes"].append(data)
        if parent is not None:
            self.doc["nodes"][parent].setdefault("children", []).append(index)
            self.parents[index] = parent
        return index

    def view(self, blob, target=None):
        self.buffer.extend(b"\0" * (-len(self.buffer) % 4))
        record = {"buffer": 0, "byteOffset": len(self.buffer), "byteLength": len(blob)}
        if target:
            record["target"] = target
        self.buffer.extend(blob)
        self.doc["bufferViews"].append(record)
        return len(self.doc["bufferViews"])-1

    def accessor(self, values, kind, *, component=5126, target=None, bounds=False):
        array = np.asarray(values, dtype="<f4" if component == 5126 else "<u2")
        if not np.isfinite(array).all() or not len(array):
            raise ValueError("Empty or nonfinite accessor")
        record = {"bufferView": self.view(array.tobytes(), target), "componentType": component,
                  "count": len(values), "type": kind}
        if bounds:
            flat = array.reshape(len(values), -1)
            record.update(min=flat.min(axis=0).tolist(), max=flat.max(axis=0).tolist())
        self.doc["accessors"].append(record)
        return len(self.doc["accessors"])-1

    def world(self, index):
        result = matrix(self.doc["nodes"][index])
        if index in self.parents:
            result = self.world(self.parents[index]) @ result
        return result

    def hierarchy(self, raw, parent=0, owner=None):
        uid = raw if isinstance(raw, str) else raw.get("uuid")
        if uid in self.handled:
            raise ValueError(f"Duplicate/cyclic outliner UUID: {uid}")
        self.handled.add(uid)
        item = self.groups.get(uid) or self.elements.get(uid) or raw
        if not isinstance(item, dict):
            raise ValueError(f"Unknown outliner reference: {uid}")
        kind = item.get("type", "group")
        if kind in ("cube", "mesh") or ("from" in item and "to" in item):
            if item.get("visibility", True) and item.get("export", True):
                self.geometry(item, parent, owner)
            return
        if kind not in ("group", "armature", "armature_bone"):
            raise ValueError(f"Unsupported BBModel node type {kind!r}")
        pivot, rotation = item.get("origin", [0,0,0]), item.get("rotation", [0,0,0])
        node = self.node({"name": item.get("name", str(uid)), "translation": pivot,
                          "rotation": quaternion(rotation), "extras": {"bbmodel_uuid": uid}}, parent)
        self.ids[uid], self.rest[uid] = node, (pivot, rotation)
        if kind == "armature":
            owner = uid
        if kind == "armature_bone":
            self.owners[uid] = owner
        content = node
        if kind == "group":
            content = self.node({"name": item.get("name", "group")+"_content", "translation": [-v for v in pivot]}, node)
        for child in (raw.get("children", item.get("children", [])) if isinstance(raw, dict) else item.get("children", [])):
            self.hierarchy(child, content, owner)

    def materials(self):
        textures = self.data.get("textures", [])
        if isinstance(self.texture, (list, tuple)):
            textures = [
                {**(textures[i] if i < len(textures) else {}), "relative_path": str(p), "name": Path(p).name}
                for i, p in enumerate(self.texture)
            ]
            for t in textures:
                t.pop("source", None)
        elif self.texture:
            if len(textures) > 1:
                raise ValueError("Texture variant overrides require a single-atlas BBModel")
            textures = [{"relative_path": str(self.texture)}]
        result = []
        for texture in textures:
            source = texture.get("source", "")
            if source.startswith("data:image/"):
                blob = base64.b64decode(source.split(",", 1)[1], validate=True)
            else:
                path = Path(texture.get("relative_path") or texture.get("path") or "")
                path = path if path.is_absolute() else self.model.parent / path
                path = path.resolve()
                if self.scope and not path.is_relative_to(self.scope):
                    raise ValueError(f"Texture leaves project: {path}")
                blob = path.read_bytes()
            import io
            with Image.open(io.BytesIO(blob)) as image:
                mime = {"PNG": "image/png", "JPEG": "image/jpeg"}.get(image.format)
                image.verify()
            if not mime:
                raise ValueError("GLB textures must be PNG or JPEG")
            self.doc.setdefault("images", []).append({"bufferView": self.view(blob), "mimeType": mime})
            index = len(self.doc["images"])-1
            self.doc.setdefault("textures", []).append({"source": index, "sampler": 0})
            result.append({"name": texture.get("name", "atlas"), "pbrMetallicRoughness": {
                "baseColorTexture": {"index": index}, "metallicFactor": 0, "roughnessFactor": 1},
                "doubleSided": texture.get("render_sides") != "front", "alphaMode": "MASK", "alphaCutoff": .05})
        if textures:
            mag, minify = GLTF_FILTERS[self.texture_filter]
            self.doc["samplers"] = [{"magFilter": mag, "minFilter": minify, "wrapS": 33071, "wrapT": 33071}]
        self.doc["materials"] = result or [{"pbrMetallicRoughness": {"metallicFactor": 0, "roughnessFactor": 1}, "doubleSided": True}]

    def geometry(self, item, parent, owner):
        origin = item.get("origin", [0,0,0])
        weighted = owner and any(kind == "armature_bone" for kind in [e.get("type") for e in self.elements.values()])
        cube = item.get("type", "cube") == "cube"
        faces = item.get("faces", {})
        chunks = {}
        definitions = cube_faces(item) if cube else {key: [item["vertices"][vertex] for vertex in face["vertices"]]
                                                   for key, face in faces.items()}
        resolution = self.data.get("resolution", {})
        width, height = resolution.get("width", 16), resolution.get("height", 16)
        for name, points in definitions.items():
            face = faces.get(name, {})
            if faces and (name not in faces or face.get("texture", False) is None):
                continue
            normal = np.asarray(newell_normal(points), dtype=float)
            length = np.linalg.norm(normal)
            if length < 1e-12:
                continue
            normal /= length
            uv = face.get("uv")
            vertex_keys = [None]*4 if cube else face["vertices"]
            if cube:
                u1, v1, u2, v2 = uv if isinstance(uv, list) and len(uv) == 4 else [0,0,0,0]
                coords = [[u1,v2],[u2,v2],[u2,v1],[u1,v1]]
                shift = (int(face.get("rotation", 0)) // 90) % 4
                coords = coords[shift:]+coords[:shift]
            else:
                coords = [uv.get(key, [0,0]) if isinstance(uv, dict) else [0,0] for key in vertex_keys]
            textured = bool(self.doc.get("images"))
            if textured and (not uv or not width or not height):
                raise ValueError(f"Missing explicit UV for textured face {item['name']}/{name}")
            material = face.get("texture", 0)
            material = 0 if material is False else material
            if not isinstance(material, int) or not 0 <= material < len(self.doc["materials"]):
                raise ValueError(f"Invalid material reference: {material}")
            texture_records = self.data.get("textures", [])
            texture_record = texture_records[material] if material < len(texture_records) else {}
            face_width = texture_record.get("uv_width") or texture_record.get("width") or width or 16
            face_height = texture_record.get("uv_height") or texture_record.get("height") or height or 16
            chunk = chunks.setdefault(material, {"position": [], "normal": [], "uv": [], "keys": []})
            for triangle in temporary_triangle_indices(points):
                for index in triangle:
                    point = np.asarray(points[index], dtype=float)
                    if cube:
                        point -= origin
                    elif weighted:
                        point += origin
                    chunk["position"].append(point.tolist())
                    chunk["normal"].append(normal.tolist())
                    chunk["uv"].append([coords[index][0]/face_width, coords[index][1]/face_height])
                    chunk["keys"].append(vertex_keys[index])
        if not chunks:
            return
        mesh = {"name": item.get("name", "mesh"), "primitives": []}
        for material, chunk in chunks.items():
            attributes = {"POSITION": self.accessor(chunk["position"], "VEC3", target=34962, bounds=True),
                          "NORMAL": self.accessor(chunk["normal"], "VEC3", target=34962),
                          "TEXCOORD_0": self.accessor(chunk["uv"], "VEC2", target=34962)}
            mesh["primitives"].append({"attributes": attributes, "material": material})
        self.doc["meshes"].append(mesh)
        record = {"name": item.get("name", "mesh"), "mesh": len(self.doc["meshes"])-1,
                  "extras": {"bbmodel_uuid": item["uuid"]}}
        if not weighted:
            record.update(translation=origin, rotation=quaternion(item.get("rotation", [0,0,0])))
        # glTF skinning ignores the skinned mesh node's local and ancestor
        # transforms. Weighted BBModel vertices are already in model space, so
        # make these nodes scene roots; the skeleton remains under the scaled
        # scene node and drives deformation through joints.
        node = self.node(record, None if weighted else parent)
        if weighted:
            self.doc["scenes"][0]["nodes"].append(node)
        self.ids[item["uuid"]] = node
        self.rest[item["uuid"]] = (record.get("translation", [0,0,0]), item.get("rotation", [0,0,0]))
        if weighted:
            self.pending.append((node, item, owner, chunks))

    def skins(self):
        skin_cache = {}
        for node, item, owner, chunks in self.pending:
            bones = [e for uid, e in self.elements.items() if e.get("type") == "armature_bone" and self.owners.get(uid) == owner]
            joints = [self.ids[e["uuid"]] for e in bones]
            if not joints:
                raise ValueError("Weighted mesh has no skeleton")
            matrices = [(np.linalg.inv(self.world(joint)) @ self.world(node)).flatten(order="F").tolist() for joint in joints]
            # Meshes of one rig usually share joints and bind matrices; glTF lets them share one skin.
            key = (tuple(joints), tuple(round(value, 6) for matrix in matrices for value in matrix))
            if key not in skin_cache:
                skin = {"joints": joints, "inverseBindMatrices": self.accessor(matrices, "MAT4")}
                self.doc.setdefault("skins", []).append(skin)
                skin_cache[key] = len(self.doc["skins"])-1
            self.doc["nodes"][node]["skin"] = skin_cache[key]
            mesh = self.doc["meshes"][self.doc["nodes"][node]["mesh"]]
            prefix = item["uuid"][:6]+":"
            for primitive, chunk in zip(mesh["primitives"], chunks.values()):
                indices, weights = [], []
                for key in chunk["keys"]:
                    values = [(i, e.get("vertex_weights", {}).get(prefix+str(key), 0)) for i, e in enumerate(bones)]
                    values = [(i, float(w)) for i, w in values if w > 0]
                    if not values or len(values) > 4:
                        raise ValueError(f"Vertex {key}: export needs 1–4 bone influences")
                    total = sum(w for _, w in values)
                    indices.append([i for i, _ in values]+[0]*(4-len(values)))
                    weights.append([w/total for _, w in values]+[0]*(4-len(values)))
                primitive["attributes"].update(JOINTS_0=self.accessor(indices, "VEC4", component=5123, target=34962),
                                                WEIGHTS_0=self.accessor(weights, "VEC4", target=34962))

    def animations(self):
        for clip in self.data.get("animations", []):
            animation = {"name": clip["name"], "channels": [], "samplers": [], "extras": {"loop": clip.get("loop", "once")}}
            for uid, track in clip.get("animators", {}).items():
                if uid == "effects":
                    raise ValueError(f"Animation {clip['name']!r} contains Blockbench effects; glTF has no equivalent effect/event track")
                if uid not in self.ids:
                    raise ValueError(f"Animation targets unsupported/missing control {uid}")
                pivot, rest_rotation = self.rest[uid]
                keyframes = track.get("keyframes", [])
                unsupported = sorted({str(key.get("channel")) for key in keyframes
                                      if key.get("channel") not in {"position", "rotation", "scale"}})
                if unsupported:
                    raise ValueError(f"Animation {clip['name']!r} on control {uid} uses channels that glTF cannot encode: {unsupported}")
                for channel, path in (("position", "translation"), ("rotation", "rotation"), ("scale", "scale")):
                    keys = [dict(key) for key in keyframes if key.get("channel") == channel]
                    if not keys:
                        continue
                    for key in keys:
                        points = key.get("data_points", [])
                        if len(points) > 1 and points[0] != points[1]:
                            discontinuity = dict(key)
                            discontinuity["time"] = float(key["time"]) + 0.004
                            discontinuity["data_points"] = [points[1]]
                            discontinuity["interpolation"] = "linear"
                            discontinuity.pop("bezier_left_time", None)
                            discontinuity.pop("bezier_left_value", None)
                            discontinuity.pop("bezier_right_time", None)
                            discontinuity.pop("bezier_right_value", None)
                            keys.append(discontinuity)
                    keys.sort(key=lambda key: key["time"])
                    if any(float(key["time"]) < 0 or not math.isfinite(float(key["time"])) for key in keys):
                        raise ValueError("Animation times must be nonnegative and finite")
                    if len({key["time"] for key in keys}) != len(keys):
                        raise ValueError("Duplicate animation key times")
                    modes = {key.get("interpolation", "linear") for key in keys}
                    if not modes <= {"linear", "step", "catmullrom", "bezier"}:
                        raise ValueError(f"Unsupported animation interpolation: {modes}")
                    end = max(float(clip.get("length", 0)), float(keys[-1]["time"]))
                    if len(keys) == 1 or modes == {"step"}:
                        times = [float(key["time"]) for key in keys]
                    else:
                        times = sorted({float(key["time"]) for key in keys} | {min(i/self.fps, end) for i in range(math.ceil(end*self.fps)+1)} |
                                       {max(0, float(b["time"])-1e-5) for a, b in zip(keys, keys[1:]) if a.get("interpolation") == "step"})
                    values, previous = [], (0.0, 0.0, 0.0)
                    for time in times:
                        value = sample(keys, time, previous=previous,
                                       context=f"animation {clip['name']!r}, control {uid}, channel {channel}")
                        previous = tuple(value)
                        if channel == "position":
                            value = [a+b for a, b in zip(pivot, value)]
                        elif channel == "rotation":
                            value = quaternion([a+b for a, b in zip(rest_rotation, value)])
                            if values and sum(a*b for a, b in zip(values[-1], value)) < 0:
                                value = [-v for v in value]
                        values.append(value)
                    animation["samplers"].append({"input": self.accessor(times, "SCALAR", bounds=True),
                        "output": self.accessor(values, "VEC4" if channel == "rotation" else "VEC3"),
                        "interpolation": "STEP" if modes == {"step"} else "LINEAR"})
                    animation["channels"].append({"sampler": len(animation["samplers"])-1, "target": {"node": self.ids[uid], "path": path}})
            if animation["channels"]:
                self.doc.setdefault("animations", []).append(animation)

    def build(self, model):
        self.model = Path(model)
        self.materials()
        for raw in self.data.get("outliner", []):
            self.hierarchy(raw)
        for uid, item in self.elements.items():
            if uid not in self.handled:
                self.hierarchy(uid)
        if not self.doc["meshes"]:
            raise ValueError("No visible geometry selected for export")
        self.skins()
        self.animations()
        self.doc["nodes"][0]["scale"] = [self.scale]*3
        self.doc["buffers"] = [{"byteLength": len(self.buffer)}]
        encoded = json.dumps(self.doc, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        encoded += b" "*(-len(encoded)%4)
        self.buffer.extend(b"\0"*(-len(self.buffer)%4))
        total = 12+8+len(encoded)+8+len(self.buffer)
        return struct.pack("<4sII", b"glTF", 2, total)+struct.pack("<II", len(encoded), 0x4e4f534a)+encoded+struct.pack("<II", len(self.buffer), 0x004e4942)+self.buffer
