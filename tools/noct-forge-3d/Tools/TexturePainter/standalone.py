"""
In-memory 2D Decal Canvas & Standalone Painter.

Provides a standalone 2D canvas for procedural drawing in memory (patterns, decals,
icons) before projecting onto 3D geometry via project_decal.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union
from PIL import Image

from .core.color import ColorType, parse_color
from .core.face_canvas import FaceCanvas


class CanvasRegion(FaceCanvas):
    """Sub-region of a DecalCanvas with local coordinates."""

    def __init__(self, painter: 'DecalCanvas', name: str, x: int, y: int, width: int, height: int):
        super().__init__(width, height)
        self.painter = painter
        self.name = name
        self.x = x
        self.y = y


class DecalCanvas(FaceCanvas):
    """
    In-memory 2D canvas for procedural decal generation and 2D texture sketching.
    Inherits all discrete drawing primitives (draw_rect, draw_circle, draw_line, stamp,
    draw_pattern, apply_noise, apply_gradient, blit, make_seamless) directly from FaceCanvas.
    """

    def __init__(self, width: int, height: int, background: ColorType = (0, 0, 0, 0)):
        if width <= 0 or height <= 0:
            raise ValueError("Canvas dimensions must be positive integers")
        super().__init__(width, height, default_color=background)
        self.regions: Dict[str, CanvasRegion] = {}

    def define_region(self, name: str, x: int, y: int, width: int, height: int) -> CanvasRegion:
        """Defines a named sub-region with local coordinates."""
        if not name or not name.strip():
            raise ValueError("Region name cannot be empty")
        clean_name = name.strip()
        if x < 0 or y < 0 or x + width > self.width or y + height > self.height:
            raise ValueError(f"Region '{clean_name}' ({x}, {y}, {width}x{height}) exceeds canvas {self.width}x{self.height}")
        region = CanvasRegion(self, clean_name, x, y, width, height)
        self.regions[clean_name] = region
        return region

    def tile_grid(self, tile_w: int, tile_h: int, names: Sequence[str]) -> 'DecalCanvas':
        """Subdivide the canvas into a grid of named tiles."""
        cols = self.width // tile_w
        rows = self.height // tile_h
        for idx, name in enumerate(names):
            if idx >= cols * rows:
                break
            col = idx % cols
            row = idx // cols
            self.define_region(name, col * tile_w, row * tile_h, tile_w, tile_h)
        return self

    def region(self, name: str) -> CanvasRegion:
        if name not in self.regions:
            raise KeyError(f"Region '{name}' not found. Available: {list(self.regions.keys())}")
        return self.regions[name]

    def __getattr__(self, item: str):
        if item in self.regions:
            return self.regions[item]
        raise AttributeError(f"'DecalCanvas' object has no attribute or region '{item}'")

    def compose(self) -> Image.Image:
        """Composes root canvas and all defined regions into a single PIL image."""
        composed = self.to_image()
        for reg in self.regions.values():
            reg_img = reg.to_image()
            composed.paste(reg_img, (reg.x, reg.y), reg_img if reg_img.mode == "RGBA" else None)
        return composed

    def save(self, output_path: Union[str, Path], overwrite: bool = True) -> str:
        """Saves composed image directly to a standalone PNG file."""
        path = Path(output_path).resolve()
        if path.suffix.lower() != ".png":
            raise ValueError("Output file must use .png extension")
        if path.exists() and not overwrite:
            raise FileExistsError(f"File {path} already exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        img = self.compose()
        img.save(path, format="PNG")
        return str(path)
