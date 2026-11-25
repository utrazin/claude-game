"""Read explicit pixel UVs. Never pack, scale or guess missing coordinates."""
import json
import math

from pathlib import Path

import numpy as np

from .polygon_face_canvas import polygon_mask


class BlockbenchModelParser:
    def __init__(self, bbmodel_path):
        self.bbmodel_path = str(bbmodel_path)
        self.data = json.loads(Path(bbmodel_path).read_text(encoding="utf-8"))
        self._initialize()

    @classmethod
    def from_document(cls, data):
        parser = cls.__new__(cls)
        parser.bbmodel_path = None
        parser.data = data
        parser._initialize()
        return parser

    def _initialize(self):
        from Tools.uv_contract import validate_sharing
        if self.data.get('unhandled_root_fields', {}).get('model_as_code', {}).get('uv_ready') is False:
            raise ValueError('UV stage not finalized; run the UV recipe before painting')
        self.mirrors = {}
        self.sharing = validate_sharing(self.data, mirrors=self.mirrors)
        res = self.data.get("resolution", {})
        self.tex_width = self._integer(res.get("width"), "resolution.width")
        self.tex_height = self._integer(res.get("height"), "resolution.height")
        if min(self.tex_width, self.tex_height) <= 0:
            raise ValueError("Texture resolution must be positive")
        self.textures_info = self.data.get("textures", [])
        packing = self.data.get("unhandled_root_fields", {}).get("model_as_code", {}).get("uv_packing", {})
        self.require_integer_uvs = packing.get('require_integer_uvs', True)
        if not isinstance(self.require_integer_uvs, bool):
            raise ValueError('require_integer_uvs must be a boolean')
        self.island_padding = self._integer(packing.get("island_padding", 0), "uv_packing.island_padding")
        if self.island_padding < 0:
            raise ValueError("uv_packing.island_padding must be non-negative")
        raw_slots = packing.get("textures")
        if raw_slots is not None:
            if not isinstance(raw_slots, list) or not raw_slots:
                raise ValueError("uv_packing.textures must be a non-empty list")
            slots, seen_names = [], set()
            for idx, entry in enumerate(raw_slots):
                if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"]:
                    raise ValueError(f"uv_packing.textures[{idx}]: expected a non-empty name")
                w = self._integer(entry.get("width"), f"uv_packing.textures[{idx}].width")
                h = self._integer(entry.get("height"), f"uv_packing.textures[{idx}].height")
                if min(w, h) <= 0:
                    raise ValueError(f"uv_packing.textures[{idx}]: resolution must be positive")
                if entry["name"] in seen_names:
                    raise ValueError(f"Duplicate UV texture slot name: {entry['name']!r}")
                seen_names.add(entry["name"])
                slots.append({"index": idx, "name": entry["name"], "width": w, "height": h})
            self.texture_slots = slots
            self.tex_width, self.tex_height = slots[0]["width"], slots[0]["height"]
        elif len(self.textures_info) > 1:
            slots, seen_names = [], set()
            for idx, tex in enumerate(self.textures_info):
                raw_name = Path(tex.get("name") or tex.get("relative_path") or f"slot_{idx}").stem or f"slot_{idx}"
                name = raw_name if raw_name not in seen_names else f"{raw_name}_{idx}"
                seen_names.add(name)
                w = self._integer(tex.get("uv_width") or tex.get("width") or self.tex_width, f"textures[{idx}].width")
                h = self._integer(tex.get("uv_height") or tex.get("height") or self.tex_height, f"textures[{idx}].height")
                if min(w, h) <= 0:
                    raise ValueError(f"textures[{idx}]: resolution must be positive")
                slots.append({"index": idx, "name": name, "width": w, "height": h})
            self.texture_slots = slots
        else:
            self.texture_slots = [{"index": 0, "name": "default", "width": self.tex_width, "height": self.tex_height}]
        self.elements = self._extract_elements()

    @staticmethod
    def _integer(value, label):
        if not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value:
            raise ValueError(f"{label}: expected an integer pixel coordinate, got {value!r}")
        return int(value)

    def _coordinate(self, value, label):
        if self.require_integer_uvs:
            return self._integer(value, label)
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value):
            raise ValueError(f'{label}: invalid UV coordinate')
        return float(value)

    @staticmethod
    def _atlas_points_to_canvas(points, width, height, rotation, flip_x, flip_y):
        result = []
        for ax, ay in points:
            if flip_x:
                ax = width - ax
            if flip_y:
                ay = height - ay
            if rotation == 0:
                sx, sy = ax, ay
            elif rotation == 90:
                sx, sy = ay, width - ax
            elif rotation == 180:
                sx, sy = width - ax, height - ay
            else:
                sx, sy = height - ay, ax
            result.append([sx, sy])
        return result

    def _mirror_matches(self, target, source, mapping):
        """Each follower vertex must sit on the owner point its mirror reuses."""
        faces = {(elem.get('name'), name): face for elem in self.data.get('elements', [])
                 for name, face in elem.get('faces', {}).items()}

        def points(face):
            uv = face.get('uv')
            if isinstance(uv, dict):
                return uv
            return dict(enumerate(([uv[0], uv[1]], [uv[2], uv[1]], [uv[2], uv[3]], [uv[0], uv[3]])))

        follower, owner = points(faces[target]), points(faces[source])
        return set(follower) == set(mapping) and all(
            list(follower[key]) == list(owner[mapping[key]]) for key in mapping)

    def _chart_ownership(self):
        """Faces of a UV chart (``model_as_code_chart``) share edge texels; give every texel the chart touches
        to exactly one face: the face containing its centre, else the first face covering part of it.

        A chart whose faces are mirror images (``model_as_code_mirror`` names each face's source) takes the
        ownership of its source chart reflected, texel for texel, so both cover exactly the same texels.

        Returns ({(element, face): (x, y, mask)}, {(element, face): (source ref, K, D)}): owned texels as a bool
        mask at atlas offset (x, y); for mirrored faces, texel (x, y) mirrors source texel (K - 1 - x, y - D)."""
        charts, sources, face_chart = {}, {}, {}
        for elem in self.data.get("elements", []):
            for face_name, face in (elem.get("faces") or {}).items():
                chart, uv = face.get("model_as_code_chart"), face.get("uv")
                if chart and isinstance(uv, dict) and not ("texture" in face and face["texture"] is None):
                    ref = (elem.get("name"), face_name)
                    coords = np.array([uv[k] for k in face.get("vertices", [])], dtype=float)
                    charts.setdefault(chart, []).append((ref, coords))
                    face_chart[ref] = chart
                    if face.get("model_as_code_mirror"):
                        sources[ref] = tuple(face["model_as_code_mirror"])
        result, mirrors, grids = {}, {}, {}

        def store(members, owner, x0, y0):
            for index, (ref, coords) in enumerate(members):
                ys, xs = np.nonzero(owner == index)
                if not len(xs):
                    # a sliver whose only texel another sliver took (a fan of thin triangles inside one texel):
                    # it stays a chart face and owns nothing; its neighbours paint the texels it touches
                    fx, fy = (int(math.floor(v)) for v in coords.min(axis=0))
                    result[ref] = (fx, fy, np.zeros((1, 1), dtype=bool))
                    continue
                ox, oy = int(xs.min()), int(ys.min())
                result[ref] = (x0 + ox, y0 + oy, owner[oy:int(ys.max()) + 1, ox:int(xs.max()) + 1] == index)

        def reflected(chart, members):
            """Ownership of a mirrored chart from its source chart's, or None when it is not an exact mirror."""
            if not all(ref in sources for ref, _ in members):
                return None
            source_chart = face_chart.get(sources[members[0][0]])
            if source_chart is None or source_chart not in grids or source_chart == chart:
                return None
            sx0, sy0, source_owner, source_members = grids[source_chart]
            position = {ref: i for i, (ref, _) in enumerate(source_members)}
            coords = dict(source_members)
            ref, mine = members[0]
            theirs = coords.get(sources[ref])
            if theirs is None or len(theirs) != len(mine):
                return None
            k = mine[:, 0].min() + theirs[:, 0].max()          # u' = K - u
            d = mine[:, 1].min() - theirs[:, 1].min()          # v' = v + D
            if abs(k - round(k)) > 1e-9 or abs(d - round(d)) > 1e-9:
                return None
            k, d = int(round(k)), int(d and round(d))
            index_of = np.full(len(source_members) + 1, -1, dtype=np.int32)
            for i, (ref, _) in enumerate(members):
                j = position.get(sources[ref])
                if j is None:
                    return None
                index_of[j] = i
            owner = np.where(source_owner[:, ::-1] >= 0, index_of[source_owner[:, ::-1]], -1)
            for ref, _ in members:
                mirrors[ref] = (sources[ref], k, d)
            return owner, k - (sx0 + source_owner.shape[1]), sy0 + d

        # Source charts first, so mirrored charts can reflect them.
        for chart, members in sorted(charts.items(), key=lambda kv: any(ref in sources for ref, _ in kv[1])):
            done = reflected(chart, members)
            if done is not None:
                owner, x0, y0 = done
                grids[chart] = (x0, y0, owner, members)
                store(members, owner, x0, y0)
                continue
            for ref, _ in members:
                mirrors.pop(ref, None)
            every = np.concatenate([coords for _, coords in members])
            x0, y0 = (int(math.floor(v)) for v in every.min(axis=0))
            x1, y1 = (int(math.ceil(v)) for v in every.max(axis=0))
            owner = np.full((y1 - y0, x1 - x0), -1, dtype=np.int32)
            boxes = []
            for coords in (c for _, c in members):
                fx, fy = (int(math.floor(v)) for v in coords.min(axis=0))
                fw, fh = (int(math.ceil(v)) - o for v, o in zip(coords.max(axis=0), (fx, fy)))
                boxes.append((fx, fy, max(fw, 1), max(fh, 1)))
            for conservative in (False, True):
                for index, ((_, coords), (fx, fy, fw, fh)) in enumerate(zip(members, boxes)):
                    local = [[u - fx, v - fy] for u, v in coords]
                    covered = np.asarray(polygon_mask(fw, fh, local, conservative), dtype=np.uint8) > 0
                    window = owner[fy - y0:fy - y0 + fh, fx - x0:fx - x0 + fw]
                    window[covered & (window < 0)] = index
            for index, (_, coords) in enumerate(members):     # a sliver owning no texel takes its centroid's
                if not (owner == index).any():
                    cx, cy = (int(math.floor(v)) for v in coords.mean(axis=0))
                    owner[min(max(cy - y0, 0), owner.shape[0] - 1), min(max(cx - x0, 0), owner.shape[1] - 1)] = index
            grids[chart] = (x0, y0, owner, members)
            store(members, owner, x0, y0)
        return result, mirrors

    def _extract_elements(self):
        elems = {}
        chart_owned, chart_mirrors = self._chart_ownership()
        self.chart_mirrors = chart_mirrors     # mirrored face -> (source face, K, D): texel (x, y) <- (K - 1 - x, y - D)
        # Per texture slot: last face to claim each atlas texel (-1: free), and per face its (owner, region).
        claims = {s["index"]: np.full((s["height"], s["width"]), -1, dtype=np.int32) for s in self.texture_slots}
        claim_owners = {s["index"]: np.full((s["height"], s["width"]), -1, dtype=np.int32) for s in self.texture_slots}
        claimants, owner_ids = [], {}
        for elem in self.data.get("elements", []):
            if elem.get("type", "cube") not in ("cube", "mesh"):
                continue
            name = elem.get("name")
            if not name or name in elems:
                raise ValueError(f"Missing or duplicate element name: {name!r}")
            if self.data.get("meta", {}).get("box_uv", False) or (
                    elem.get("type", "cube") == "cube" and (
                        elem.get("box_uv", False) or elem.get("autouv", 0) != 0)):
                raise ValueError(f"{name}: UV mode is not finalized; run py -3.12 -m Tools.uv_packer <model> first")
            tags = elem.get("model_as_code_tags", [])
            if (not isinstance(tags, list) or
                    any(not isinstance(tag, str) or not tag for tag in tags)):
                raise ValueError(f"{name}: model_as_code_tags must be non-empty strings")
            out = dict(uuid=elem.get("uuid"), kind=elem.get("type", "cube"),
                       tags=tuple(dict.fromkeys(tags)),
                       **{"from": elem.get("from"), "to": elem.get("to")}, faces={})
            elems[name] = out
            raw_faces = elem.get("faces")
            if not raw_faces:
                raise ValueError(f"{name}: missing explicit UVs; generate the layout in code first")
            for face_name, face in raw_faces.items():
                if "texture" in face and face["texture"] is None:
                    continue
                label = f"{name}.{face_name}"
                raw_tex = face.get("texture", False)
                if raw_tex is False:
                    slot_idx = 0
                elif isinstance(raw_tex, int) and not isinstance(raw_tex, bool) and 0 <= raw_tex < len(self.texture_slots):
                    slot_idx = raw_tex
                else:
                    raise ValueError(f"{label}: invalid texture slot index {raw_tex!r}")
                slot_info = self.texture_slots[slot_idx]
                slot_w, slot_h = slot_info["width"], slot_info["height"]
                uv = face.get("uv")
                layout = "rectangle"
                points = None
                chart = face.get("model_as_code_chart")
                if (name, face_name) in chart_owned:
                    x, y, owned = chart_owned[(name, face_name)]
                    h, w = owned.shape
                    coords = [[self._coordinate(v, label) for v in uv[k]] for k in face.get("vertices", [])]
                    points = [[u - x, v - y] for u, v in coords]
                    ref = (name, face_name)
                    owner_id = owner_ids.setdefault(ref, len(owner_ids))
                    if x < 0 or y < 0 or x + w > slot_w or y + h > slot_h:
                        raise ValueError(f"{label}: UV outside texture resolution")
                    window = claims[slot_idx][y:y+h, x:x+w]
                    owners = claim_owners[slot_idx][y:y+h, x:x+w]
                    conflict = owned & (owners >= 0) & (owners != owner_id)
                    if conflict.any():
                        row, column = np.argwhere(conflict)[0]
                        raise ValueError(f"{label}: UV overlap with {claimants[window[row, column]]}")
                    window[owned] = len(claimants)
                    owners[owned] = owner_id
                    claimants.append((ref, (uv, 0)))
                    out["faces"][face_name] = dict(
                        uv=uv, x=x, y=y, w=w, h=h, flip_x=False, flip_y=False, rotation=0,
                        layout="polygon", points=points, canvas_points=points, conservative=True,
                        owned_mask=owned, chart=chart, mirror=chart_mirrors.get((name, face_name)),
                        group=face.get("model_as_code_group"),
                        source_face=face.get("model_as_code_source_face"), owner=None,
                        texture=slot_idx, texture_name=slot_info["name"])
                    continue
                if isinstance(uv, dict):
                    order = face.get("vertices", [])
                    if len(order) not in (3, 4) or len(set(order)) != len(order) or set(order) != set(uv):
                        raise ValueError(f"{label}: polygon UV keys must match the ordered face vertices")
                    coords = [uv[k] for k in order]
                    if any(not isinstance(c, (list, tuple)) or len(c) != 2 for c in coords):
                        raise ValueError(f"{label}: invalid vertex UV")
                    coords = [[self._coordinate(v, label) for v in c] for c in coords]
                    if not self.require_integer_uvs:
                        from lib.polygon_math import validate_contour
                        validate_contour(tuple(map(tuple, coords)))
                    area2 = sum(coords[i][0] * coords[(i+1) % len(coords)][1] -
                                coords[(i+1) % len(coords)][0] * coords[i][1]
                                for i in range(len(coords)))
                    if len(set(map(tuple, coords))) != len(coords) or area2 == 0:
                        raise ValueError(f"{label}: degenerate polygon UV")
                    xs, ys = [c[0] for c in coords], [c[1] for c in coords]
                    x, y, max_x, max_y = min(xs), min(ys), max(xs), max(ys)
                    if not self.require_integer_uvs:
                        if any(abs(v-round(v)) > 1e-8 for v in (x+max_x,y+max_y)):
                            raise ValueError(f'{label}: UV bounds center must align to half pixels')
                    w, h = max_x - x, max_y - y
                    rectangular = (len(coords) == 4 and coords == [
                        [coords[0][0], coords[0][1]], [coords[2][0], coords[0][1]],
                        [coords[2][0], coords[2][1]], [coords[0][0], coords[2][1]]])
                    if rectangular and (self.require_integer_uvs or all(v == int(v) for p in coords for v in p)):
                        u1, v1 = coords[0]
                        u2, v2 = coords[2]
                    else:
                        layout = "polygon"
                        x, y, max_x, max_y = math.floor(x), math.floor(y), math.ceil(max_x), math.ceil(max_y)
                        points = [[u-x, v-y] for u, v in coords]
                        u1, v1, u2, v2 = x, y, max_x, max_y
                elif isinstance(uv, list) and len(uv) == 4:
                    u1, v1, u2, v2 = uv
                else:
                    raise ValueError(f"{label}: missing explicit face UV rectangle")
                u1, v1, u2, v2 = [self._integer(v, label) for v in (u1, v1, u2, v2)]
                x, y, w, h = min(u1, u2), min(v1, v2), abs(u2-u1), abs(v2-v1)
                if not w or not h:
                    raise ValueError(f"{label}: empty UV rectangle")
                if x < 0 or y < 0 or x+w > slot_w or y+h > slot_h:
                    raise ValueError(f"{label}: UV outside texture resolution")
                rot = self._integer(face.get("rotation", 0), label)
                if rot not in (0, 90, 180, 270):
                    raise ValueError(f"{label}: unsupported UV rotation {rot}")
                ref = (name, face_name)
                owner = self.sharing.get(ref, ref)
                region = (uv if layout == "polygon" else (u1, v1, u2, v2), rot)
                mask = polygon_mask(w, h, points, True) if layout == "polygon" else None
                canvas_points = (self._atlas_points_to_canvas(
                    points, w, h, rot, u1 > u2, v1 > v2)
                    if layout == "polygon" else None)
                if mask is not None and not mask.getbbox():
                    raise ValueError(f'{label}: empty polygon coverage')
                covered = (np.ones((h, w), dtype=bool) if mask is None
                           else np.asarray(mask, dtype=np.uint8) > 0)
                window = claims[slot_idx][y:y+h, x:x+w]
                owners = claim_owners[slot_idx][y:y+h, x:x+w]
                owner_id = owner_ids.setdefault(owner, len(owner_ids))
                conflict = covered & (owners >= 0) & (owners != owner_id)
                if conflict.any():
                    row, column = np.argwhere(conflict)[0]
                    raise ValueError(f"{label}: UV overlap with {claimants[window[row, column]]}")
                window[covered] = len(claimants)
                owners[covered] = owner_id
                claimants.append((owner, region))
                out["faces"][face_name] = dict(
                    uv=uv, x=x, y=y, w=w, h=h,
                    flip_x=u1 > u2, flip_y=v1 > v2, rotation=rot,
                    layout=layout, points=points, canvas_points=canvas_points,
                    conservative=(layout == "polygon" or not self.require_integer_uvs),
                    group=face.get("model_as_code_group"),
                    source_face=face.get("model_as_code_source_face"),
                    owner=owner if ref in self.sharing else None,
                    texture=slot_idx, texture_name=slot_info["name"])
        self.claimed_by_slot = {idx: grid >= 0 for idx, grid in claims.items()}
        self.claimed = self.claimed_by_slot[0]          # atlas 0 texels some face paints (the rest is padding)
        from Tools.uv_contract import region_targets
        regions = region_targets(self.data)
        for target, source in self.sharing.items():
            if any(ref[0] not in elems or ref[1] not in elems[ref[0]]['faces'] for ref in (target, source)):
                raise ValueError(f'Missing shared UV face: {target} -> {source}')
            a, b = elems[target[0]]['faces'][target[1]], elems[source[0]]['faces'][source[1]]
            if a.get('texture', 0) != b.get('texture', 0):
                raise ValueError(f'Shared UV faces must use the same texture slot: {target} -> {source}')
            if target in regions:
                # A flat region: every face shows the owner's island, whatever its own shape.
                a['region'] = True
                if any(a[k] != b[k] for k in ('x', 'y', 'w', 'h')):
                    raise ValueError(f'Flat UV region differs from its owner island: {target} -> {source}')
                continue
            if target in self.mirrors:
                if any(a[k] != b[k] for k in ('x', 'y', 'w', 'h', 'rotation', 'layout')) or \
                        not self._mirror_matches(target, source, self.mirrors[target]):
                    raise ValueError(f'Mirrored UV layout differs: {target} -> {source}')
                continue
            if any(a[k] != b[k] for k in ('x', 'y', 'w', 'h', 'flip_x', 'flip_y',
                                          'rotation', 'layout', 'points', 'canvas_points')):
                raise ValueError(f'Shared UV layout differs: {target} -> {source}')
        return elems
