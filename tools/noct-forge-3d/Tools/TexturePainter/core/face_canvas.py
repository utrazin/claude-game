import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image, ImageDraw
from .color import ColorType, parse_color, color_add_noise, color_lerp

class FaceCanvas:
    """
    Represents a 2D face of an element or in-memory canvas (upright local coordinates).
    (0, 0) is the top-left corner of the face.
    Optionally supports an alpha mask for arbitrary polygonal UV islands.
    """
    def __init__(self, width: int, height: int, default_color: ColorType = (0, 0, 0, 0),
                 mask: Optional[Image.Image] = None):
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.image = Image.new("RGBA", (self.width, self.height), parse_color(default_color))
        self.draw = ImageDraw.Draw(self.image)
        if mask is not None:
            self.mask = mask
            self._clip()

    def _clip(self) -> 'FaceCanvas':
        if getattr(self, "mask", None) is not None:
            alpha = self.image.getchannel("A")
            self.image.putalpha(Image.composite(alpha, Image.new("L", alpha.size, 0), self.mask))
        return self

    def clear(self, color: ColorType = (0, 0, 0, 0)) -> 'FaceCanvas':
        """Clear the face with specified color (default transparent)."""
        return self.fill(color)

    def fill(self, color: ColorType) -> 'FaceCanvas':
        """Fill the entire face with specified color."""
        c = parse_color(color)
        self.image.paste(c, [0, 0, self.width, self.height])
        return self._clip()

    def set_pixel(self, x: int, y: int, color: ColorType, wrap: bool = False) -> 'FaceCanvas':
        """Set color of a specific pixel on the face (with wrap support for seamless textures)."""
        if wrap:
            x = x % self.width
            y = y % self.height
        if 0 <= x < self.width and 0 <= y < self.height:
            mask = getattr(self, "mask", None)
            if mask is None or mask.getpixel((x, y)) > 0:
                self.image.putpixel((x, y), parse_color(color))
        return self

    def get_pixel(self, x: int, y: int) -> Tuple[int, int, int, int]:
        """Get RGBA color of a pixel."""
        if 0 <= x < self.width and 0 <= y < self.height:
            mask = getattr(self, "mask", None)
            if mask is None or mask.getpixel((x, y)) > 0:
                return self.image.getpixel((x, y))
        return (0, 0, 0, 0)

    def read_pixels(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """RGBA rows (N, 4) at in-bounds pixels; pixels outside the mask read as transparent, as in get_pixel."""
        pixels = np.asarray(self.image)[ys, xs].astype(np.int64)
        mask = getattr(self, "mask", None)
        if mask is not None:
            pixels[np.asarray(mask)[ys, xs] == 0] = 0
        return pixels

    def write_pixels(self, xs: np.ndarray, ys: np.ndarray, colors) -> 'FaceCanvas':
        """Set RGBA rows at in-bounds pixels in one pass; as in set_pixel, masked pixels are left untouched."""
        colors = np.asarray(colors, dtype=np.uint8).reshape(-1, 4)
        mask = getattr(self, "mask", None)
        if mask is not None:
            keep = np.asarray(mask)[ys, xs] > 0
            xs, ys, colors = xs[keep], ys[keep], colors[keep]
        if len(xs):
            pixels = np.array(self.image)
            pixels[ys, xs] = colors
            self.image.paste(Image.fromarray(pixels, "RGBA"))
        return self

    def draw_rect(self, x: int, y: int, w: int, h: int, color: ColorType, fill: bool = True) -> 'FaceCanvas':
        """Draw a rectangle (filled or outline)."""
        c = parse_color(color)
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(self.width - 1, x + w - 1), min(self.height - 1, y + h - 1)
        if x1 <= x2 and y1 <= y2:
            if fill:
                self.draw.rectangle([x1, y1, x2, y2], fill=c)
            else:
                self.draw.rectangle([x1, y1, x2, y2], outline=c)
        return self._clip()

    def draw_line(self, x1: int, y1: int, x2: int, y2: int, color: ColorType) -> 'FaceCanvas':
        """Draw a straight or diagonal line."""
        c = parse_color(color)
        self.draw.line([(x1, y1), (x2, y2)], fill=c)
        return self._clip()

    def draw_circle(self, xc: int, yc: int, radius: int, color: ColorType, fill: bool = False) -> 'FaceCanvas':
        """Draw a discrete circle using the midpoint algorithm (Bresenham) without antialiasing."""
        c = parse_color(color)
        r = int(radius)
        ox = int(xc)
        oy = int(yc)
        if r <= 0:
            return self.set_pixel(ox, oy, c)

        x = 0
        y = r
        d = 3 - 2 * r

        def _plot_span(y_pos, x_start, x_end):
            if 0 <= y_pos < self.height:
                x_min = max(0, min(x_start, x_end))
                x_max = min(self.width - 1, max(x_start, x_end))
                if x_min <= x_max:
                    for px in range(x_min, x_max + 1):
                        self.set_pixel(px, y_pos, c)

        while y >= x:
            if fill:
                _plot_span(oy + y, ox - x, ox + x)
                _plot_span(oy - y, ox - x, ox + x)
                _plot_span(oy + x, ox - y, ox + y)
                _plot_span(oy - x, ox - y, ox + y)
            else:
                for px, py in (
                    (ox + x, oy + y), (ox - x, oy + y), (ox + x, oy - y), (ox - x, oy - y),
                    (ox + y, oy + x), (ox - y, oy + x), (ox + y, oy - x), (ox - y, oy - x)
                ):
                    self.set_pixel(px, py, c)
            x += 1
            if d > 0:
                y -= 1
                d = d + 4 * (x - y) + 10
            else:
                d = d + 4 * x + 6

        return self._clip()

    def apply_noise(self, variance: int = 8, seed: Optional[int] = None) -> 'FaceCanvas':
        """Apply random noise to each visible pixel for pixel-art style texture."""
        if variance <= 0:
            return self
        rng = random.Random(0 if seed is None else seed)
        for y in range(self.height):
            for x in range(self.width):
                px = self.get_pixel(x, y)
                if px[3] > 0:
                    noisy = color_add_noise(px, variance, rng=rng)
                    self.set_pixel(x, y, noisy)
        return self._clip()

    def apply_gradient(self, top_color: ColorType, bottom_color: ColorType) -> 'FaceCanvas':
        """Apply a smooth vertical gradient."""
        if self.height <= 1:
            return self.fill(top_color)
        for y in range(self.height):
            t = y / float(self.height - 1)
            c = color_lerp(top_color, bottom_color, t)
            for x in range(self.width):
                self.set_pixel(x, y, c)
        return self._clip()

    def draw_pattern(self, pattern: List[str], palette: Dict[str, ColorType]) -> 'FaceCanvas':
        """Draw a character matrix using a palette dictionary."""
        for y, row in enumerate(pattern):
            if y >= self.height:
                break
            for x, char in enumerate(row):
                if x >= self.width:
                    break
                if char in palette:
                    c = parse_color(palette[char])
                    if c[3] > 0:
                        self.set_pixel(x, y, c)
        return self._clip()

    def stamp(self, pattern: List[str], palette: Dict[str, ColorType], *,
              anchor: str = "center", offset_px: Tuple[int, int] = (0, 0),
              clip: bool = False) -> 'FaceCanvas':
        """Place an exact pixel pattern by anchor without scaling or smoothing."""
        if not pattern or any(not isinstance(row, str) for row in pattern):
            raise ValueError("stamp pattern must contain at least one text row")
        pattern_width = len(pattern[0])
        if pattern_width == 0 or any(len(row) != pattern_width for row in pattern):
            raise ValueError("stamp pattern rows must have one non-zero width")
        if (not isinstance(offset_px, (tuple, list)) or len(offset_px) != 2 or
                any(isinstance(value, bool) or not isinstance(value, int) for value in offset_px)):
            raise ValueError("offset_px must contain two integers")
        anchors = {
            "top_left": (0, 0),
            "top": ((self.width - pattern_width) // 2, 0),
            "top_right": (self.width - pattern_width, 0),
            "left": (0, (self.height - len(pattern)) // 2),
            "center": ((self.width - pattern_width) // 2,
                       (self.height - len(pattern)) // 2),
            "right": (self.width - pattern_width,
                      (self.height - len(pattern)) // 2),
            "bottom_left": (0, self.height - len(pattern)),
            "bottom": ((self.width - pattern_width) // 2,
                       self.height - len(pattern)),
            "bottom_right": (self.width - pattern_width,
                             self.height - len(pattern)),
        }
        normalized_anchor = anchor.lower().replace("-", "_")
        if normalized_anchor not in anchors:
            raise ValueError(f"Unsupported stamp anchor: {anchor!r}")
        origin_x = anchors[normalized_anchor][0] + offset_px[0]
        origin_y = anchors[normalized_anchor][1] + offset_px[1]
        if not clip and (origin_x < 0 or origin_y < 0 or
                         origin_x + pattern_width > self.width or
                         origin_y + len(pattern) > self.height):
            raise ValueError("stamp does not fit the face; pass clip=True to clip explicitly")
        for row_index, row in enumerate(pattern):
            for column_index, symbol in enumerate(row):
                if symbol not in palette:
                    continue
                color = parse_color(palette[symbol])
                x, y = origin_x + column_index, origin_y + row_index
                if color[3] and (clip or (0 <= x < self.width and 0 <= y < self.height)):
                    self.set_pixel(x, y, color)
        return self._clip()

    def blit(self, source: Union['FaceCanvas', Image.Image, str, Path], x: int = 0, y: int = 0) -> 'FaceCanvas':
        """Composite another image, PNG path or FaceCanvas onto this one."""
        if isinstance(source, (str, Path)):
            with Image.open(source) as opened:
                source = opened.convert("RGBA")
        src_img = source.image if isinstance(source, FaceCanvas) else source
        self.image.paste(src_img, (x, y), src_img if src_img.mode == 'RGBA' else None)
        return self._clip()

    def to_image(self) -> Image.Image:
        return self.image.copy()

    def make_seamless(self, border_width: int = 1) -> 'FaceCanvas':
        """Smooth opposite borders to ensure texture tiles seamlessly."""
        if self.width <= 1 or self.height <= 1 or border_width < 1:
            return self
        for y in range(self.height):
            for b in range(border_width):
                left_c = self.get_pixel(b, y)
                right_c = self.get_pixel(self.width - 1 - b, y)
                if left_c[3] > 0 and right_c[3] > 0:
                    avg_c = color_lerp(left_c, right_c, 0.5)
                    self.set_pixel(b, y, avg_c)
                    self.set_pixel(self.width - 1 - b, y, avg_c)
        for x in range(self.width):
            for b in range(border_width):
                top_c = self.get_pixel(x, b)
                bot_c = self.get_pixel(x, self.height - 1 - b)
                if top_c[3] > 0 and bot_c[3] > 0:
                    avg_c = color_lerp(top_c, bot_c, 0.5)
                    self.set_pixel(x, b, avg_c)
                    self.set_pixel(x, self.height - 1 - b, avg_c)
        return self._clip()

    def export_png(self, path: Union[str, Path]) -> str:
        """Save canvas image directly to a PNG file."""
        out = Path(path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        self.image.save(out, format="PNG")
        return str(out)
