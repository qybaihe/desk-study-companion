#!/usr/bin/env python3
"""Build LCD-ready rest/drink reminder frames from the AI sprite sheet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2] / "firmware"
ASSET_ROOT = ROOT / "assets" / "pets" / "rest_break"
SOURCE = ASSET_ROOT / "source" / "rest-break-sprite-sheet-v1.png"
FRAMES = ASSET_ROOT / "frames"
LCD = ASSET_ROOT / "lcd"
CANVAS_SIZE = (136, 112)
NORMALIZED_SOURCE_SIZE = (390, 320)
ACCENT = (228, 30, 45)
FRAME_DURATION_MS = 125


def classify(image: Image.Image) -> Image.Image:
    """Collapse generated soft pixels to black, white, and reference red."""
    image = image.convert("RGB")
    result = Image.new("RGB", image.size, "black")
    source = image.load()
    target = result.load()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = source[x, y]
            if red >= 55 and red > green * 1.18 and red > blue * 1.18:
                target[x, y] = ACCENT
            elif red + green + blue >= 450:
                target[x, y] = (255, 255, 255)
    return result


def foreground_bbox(image: Image.Image):
    """Return the non-black bounding box of a classified RGB image."""
    mask = Image.new("1", image.size)
    source = image.load()
    target = mask.load()
    for y in range(image.height):
        for x in range(image.width):
            target[x, y] = 255 if source[x, y] != (0, 0, 0) else 0
    return mask.getbbox()


def remove_grid_edge_fragments(image: Image.Image) -> Image.Image:
    """Remove tiny pieces spilled across a neighboring generated grid cell."""
    pixels = image.load()
    visited = set()
    width, height = image.size
    for start_y in range(height):
        for start_x in range(width):
            start = (start_x, start_y)
            if start in visited or pixels[start_x, start_y] == (0, 0, 0):
                continue
            pending = [start]
            visited.add(start)
            component = []
            touches_edge = False
            while pending:
                x, y = pending.pop()
                component.append((x, y))
                if x == 0 or x == width - 1:
                    touches_edge = True
                for delta_x, delta_y in (
                    (-1, -1), (0, -1), (1, -1),
                    (-1, 0), (1, 0),
                    (-1, 1), (0, 1), (1, 1),
                ):
                    candidate = (x + delta_x, y + delta_y)
                    if (
                        0 <= candidate[0] < width
                        and 0 <= candidate[1] < height
                        and candidate not in visited
                        and pixels[candidate[0], candidate[1]] != (0, 0, 0)
                    ):
                        visited.add(candidate)
                        pending.append(candidate)
            if touches_edge and len(component) < 1_000:
                for x, y in component:
                    pixels[x, y] = (0, 0, 0)
    return image


def pack_rgb565(image: Image.Image) -> bytes:
    """Pack pixels high-byte first for the board's ST7789 driver."""
    data = bytearray(image.width * image.height * 2)
    position = 0
    for red, green, blue in image.getdata():
        value = (
            ((red & 0xF8) << 8)
            | ((green & 0xFC) << 3)
            | (blue >> 3)
        )
        data[position] = value >> 8
        data[position + 1] = value & 0xFF
        position += 2
    return bytes(data)


def normalize_cell(cell: Image.Image) -> Image.Image:
    """Keep one scale across frames while removing generated grid offsets."""
    art = remove_grid_edge_fragments(classify(cell))
    bbox = foreground_bbox(art)
    if bbox is None:
        raise ValueError("rest-break frame contains no foreground")
    subject = art.crop(bbox)
    if (
        subject.width > NORMALIZED_SOURCE_SIZE[0]
        or subject.height > NORMALIZED_SOURCE_SIZE[1]
    ):
        raise ValueError("rest-break frame exceeds normalized source canvas")
    normalized = Image.new("RGB", NORMALIZED_SOURCE_SIZE, "black")
    normalized.paste(
        subject,
        (
            (NORMALIZED_SOURCE_SIZE[0] - subject.width) // 2,
            (NORMALIZED_SOURCE_SIZE[1] - subject.height) // 2,
        ),
    )
    return normalized.resize(CANVAS_SIZE, Image.Resampling.NEAREST)


def build() -> list[Image.Image]:
    sheet = Image.open(SOURCE).convert("RGB")
    if sheet.width % 4 or sheet.height % 2:
        raise ValueError("rest-break sheet must use a 4x2 grid")
    cell_width = sheet.width // 4
    cell_height = sheet.height // 2

    FRAMES.mkdir(parents=True, exist_ok=True)
    LCD.mkdir(parents=True, exist_ok=True)
    frames = []
    for index in range(8):
        column = index % 4
        row = index // 4
        cell = sheet.crop(
            (
                column * cell_width,
                row * cell_height,
                (column + 1) * cell_width,
                (row + 1) * cell_height,
            )
        )
        frame = normalize_cell(cell)
        frame.save(FRAMES / ("rest_break_%d.png" % index))
        (LCD / ("rest_break_%d.rgb565" % index)).write_bytes(
            pack_rgb565(frame)
        )
        frames.append(frame)

    frames[0].save(
        ASSET_ROOT / "rest_break_animation.gif",
        save_all=True,
        append_images=frames[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        disposal=2,
    )
    large = [
        frame.resize((544, 448), Image.Resampling.NEAREST)
        for frame in frames
    ]
    large[0].save(
        ASSET_ROOT / "rest_break_animation_preview.gif",
        save_all=True,
        append_images=large[1:],
        duration=FRAME_DURATION_MS,
        loop=0,
        disposal=2,
    )

    contact = Image.new("RGB", (CANVAS_SIZE[0] * 4, CANVAS_SIZE[1] * 2))
    for index, frame in enumerate(frames):
        contact.paste(
            frame,
            ((index % 4) * CANVAS_SIZE[0], (index // 4) * CANVAS_SIZE[1]),
        )
    contact.resize((1088, 448), Image.Resampling.NEAREST).save(
        ASSET_ROOT / "rest_break_contact_sheet.png"
    )

    manifest = {
        "version": 1,
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "canvas": list(CANVAS_SIZE),
        "frames": 8,
        "frame_duration_ms": FRAME_DURATION_MS,
        "loop_duration_ms": FRAME_DURATION_MS * 8,
        "accent_rgb": list(ACCENT),
        "rgb565_pattern": "lcd/rest_break_{0..7}.rgb565",
    }
    (ASSET_ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return frames


if __name__ == "__main__":
    built = build()
    print("built rest-break animation:", len(built), "frames")
