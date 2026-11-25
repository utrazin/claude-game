"""External PNG delivery and verified, UV-preserving model registration."""
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from PIL import Image


class TextureExporter:
    """File-level PNG delivery and UV-preserving BBModel texture registration."""
    @staticmethod
    def slot_png_path(base_png_path, slot_name: str = "default") -> Path:
        """Resolve the PNG path for ``slot_name`` from a base texture path."""
        path = Path(base_png_path)
        if not slot_name or slot_name == "default":
            return path
        suffix = f"_{slot_name}"
        if path.stem.endswith(suffix):
            return path
        return path.with_name(f"{path.stem}{suffix}{path.suffix}")

    @staticmethod
    def base_png_path(png_path, slot_name: str = "default") -> Path:
        """Recover the base texture path when ``png_path`` already includes ``_<slot_name>``."""
        path = Path(png_path)
        if slot_name and slot_name != "default":
            suffix = f"_{slot_name}"
            if path.stem.endswith(suffix) and len(path.stem) > len(suffix):
                return path.with_name(f"{path.stem[:-len(suffix)]}{path.suffix}")
        return path

    @staticmethod
    def model_texture_slots(data: dict) -> list[dict]:
        """Return ordered texture slot dicts ``[{"name": str, "width": int, "height": int}, ...]``."""
        packing = data.get("unhandled_root_fields", {}).get("model_as_code", {}).get("uv_packing", {})
        packed_slots = packing.get("textures")
        if isinstance(packed_slots, list) and packed_slots:
            return [
                {
                    "name": str(slot.get("name") or f"slot_{idx}"),
                    "width": int(slot["width"]),
                    "height": int(slot["height"]),
                }
                for idx, slot in enumerate(packed_slots)
            ]
        res = data.get("resolution") or {}
        w, h = int(res.get("width", 16)), int(res.get("height", 16))
        textures = data.get("textures") or []
        if len(textures) > 1:
            slots = []
            for idx, tex in enumerate(textures):
                name = Path(str(tex.get("name") or f"slot_{idx}")).stem
                if name.startswith("texture_") and len(name) > len("texture_"):
                    name = name[len("texture_"):]
                tw = int(tex.get("uv_width") or tex.get("width") or w)
                th = int(tex.get("uv_height") or tex.get("height") or h)
                slots.append({"name": name or f"slot_{idx}", "width": tw, "height": th})
            return slots
        return [{"name": "default", "width": w, "height": h}]

    @staticmethod
    def model_slot_png_paths(data: dict, base_png_path) -> list[tuple[dict, Path]]:
        """Return ``[(slot_dict, resolved_png_path), ...]`` for every texture slot on ``data``."""
        base = Path(base_png_path)
        return [(slot, TextureExporter.slot_png_path(base, slot["name"]))
                for slot in TextureExporter.model_texture_slots(data)]

    @staticmethod
    def save_png(image, output_path, overwrite=True, backup=True):
        path = Path(output_path).resolve()
        if path.suffix.lower() != ".png":
            raise ValueError("Texture output must use the .png extension")
        if path.exists() and not overwrite:
            raise FileExistsError(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and backup:
            shutil.copy2(path, str(path) + ".bak")
        fd, temp = tempfile.mkstemp(dir=path.parent, suffix=".png")
        os.close(fd)
        try:
            image.save(temp, format="PNG")
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return str(path)

    @staticmethod
    def save_temp(image, prefix="tex_preview_", suffix=".png"):
        fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
        os.close(fd)
        image.save(path, format="PNG")
        return path

    @staticmethod
    def check_model(bbmodel_path, expected_data=None):
        if expected_data is not None:
            # The painter validated expected_data when it loaded; an unchanged file
            # needs no second validation.
            data = json.loads(Path(bbmodel_path).read_text(encoding="utf-8"))
            if data != expected_data:
                raise ValueError("Model changed since painting began; reload it and repaint before saving")
            return data
        from .core.bbmodel_parser import BlockbenchModelParser
        return BlockbenchModelParser(bbmodel_path).data

    @staticmethod
    def register_textures(slot_pngs: dict, bbmodel_path, *, base_png_path=None,
                          expected_data=None, backup=True, render_sides=None):
        """Register one or more slot PNGs with matching dimensions into ``bbmodel_path``."""
        data = TextureExporter.check_model(bbmodel_path, expected_data)
        slots = TextureExporter.model_texture_slots(data)
        previous = data.get("textures", [])
        model_path = Path(bbmodel_path).resolve()

        resolved_pngs = {}
        for idx, p in slot_pngs.items():
            slot_idx = int(idx)
            if not (0 <= slot_idx < len(slots)):
                raise ValueError(f"Texture slot index {slot_idx} out of range for {len(slots)} slot(s)")
            png_path = Path(p).resolve()
            if model_path == png_path:
                raise ValueError("PNG and model must have different paths")
            slot = slots[slot_idx]
            with Image.open(png_path) as image:
                if image.format != "PNG" or image.size != (slot["width"], slot["height"]):
                    raise ValueError("PNG resolution does not match model; resizing is forbidden")
            resolved_pngs[slot_idx] = png_path

        for elem in data["elements"]:
            for face in elem.get("faces", {}).values():
                if "texture" not in face:
                    face["texture"] = 0
                elif face["texture"] is not None:
                    tex = face["texture"]
                    if tex is False or not isinstance(tex, int):
                        face["texture"] = 0
                    elif 0 <= tex < len(slots):
                        face["texture"] = int(tex)
                    else:
                        raise ValueError(f"Face texture index {tex} out of range for {len(slots)} slot(s)")

        new_textures = []
        for idx, slot in enumerate(slots):
            if idx in resolved_pngs:
                slot_png = resolved_pngs[idx]
            elif base_png_path is not None:
                slot_png = TextureExporter.slot_png_path(base_png_path, slot["name"]).resolve()
                if model_path == slot_png:
                    raise ValueError("PNG and model must have different paths")
                if slot_png.exists():
                    with Image.open(slot_png) as image:
                        if image.format != "PNG" or image.size != (slot["width"], slot["height"]):
                            raise ValueError("PNG resolution does not match model; resizing is forbidden")
            elif idx < len(previous) and previous[idx].get("relative_path"):
                slot_png = (model_path.parent / previous[idx]["relative_path"]).resolve()
            else:
                raise ValueError(f"Missing PNG path for texture slot {slot['name']!r}")

            if isinstance(render_sides, dict):
                rs = render_sides.get(slot["name"], render_sides.get(idx))
            else:
                rs = render_sides
            if rs is None:
                if idx < len(previous):
                    rs = previous[idx].get("render_sides", "auto")
                elif previous:
                    rs = previous[0].get("render_sides", "auto")
                else:
                    rs = "auto"
            if rs not in ("auto", "front", "double"):
                raise ValueError("render_sides must be auto, front or double")

            new_textures.append({
                "uuid": previous[idx].get("uuid", str(uuid.uuid4())) if idx < len(previous) else str(uuid.uuid4()),
                "id": str(idx),
                "name": slot_png.name,
                "relative_path": Path(os.path.relpath(slot_png, model_path.parent)).as_posix(),
                "width": slot["width"],
                "height": slot["height"],
                "uv_width": slot["width"],
                "uv_height": slot["height"],
                "mode": "link",
                "internal": False,
                "saved": True,
                "visible": True,
                "render_mode": "default",
                "render_sides": rs,
                "frame_time": 1,
                "frame_order_type": "loop",
                "frame_order": "",
                "frame_interpolate": False,
            })

        data["textures"] = new_textures
        if backup:
            shutil.copy2(model_path, str(model_path) + ".bak")
        fd, temp = tempfile.mkstemp(dir=model_path.parent, suffix=".bbmodel")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2)
            os.replace(temp, model_path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
        return str(model_path)

    @staticmethod
    def register_texture(png_path, bbmodel_path, *, expected_data=None, backup=True, render_sides=None):
        """Register a PNG with matching dimensions; never repack UVs or compare versions."""
        return TextureExporter.register_textures(
            {0: png_path},
            bbmodel_path,
            base_png_path=png_path,
            expected_data=expected_data,
            backup=backup,
            render_sides=render_sides,
        )
