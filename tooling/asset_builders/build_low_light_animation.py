#!/usr/bin/env python3
"""Build LCD-ready low-light voice animation frames from the AI sprite sheet."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2] / "firmware"
ASSET_ROOT = ROOT / "assets" / "pets" / "low_light"
SOURCE = ASSET_ROOT / "source" / "low-light-sprite-sheet-v1.png"
FRAMES = ASSET_ROOT / "frames"
LCD = ASSET_ROOT / "lcd"
CANVAS_SIZE = (136, 112)
ACCENT = (77, 215, 123)
FRAME_DURATION_MS = 125


def classify(image: Image.Image) -> Image.Image:
    """Collapse generated glow/anti-aliasing to the kit's strict 3-color art."""
    image = image.convert("RGB")
    result = Image.new("RGB", image.size, "black")
    source = image.load()
    target = result.load()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = source[x, y]
            if (
                green >= 55
                and green > red * 1.18
                and green > blue * 1.18
            ):
                target[x, y] = ACCENT
            elif red + green + blue >= 450:
                target[x, y] = (255, 255, 255)
    return result


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


def build() -> list[Image.Image]:
    sheet = Image.open(SOURCE).convert("RGB")
    if sheet.width % 4 or sheet.height % 2:
        raise ValueError("low-light sheet must use a 4x2 grid")
    cell_width = sheet.width // 4
    cell_height = sheet.height // 2

    FRAMES.mkdir(parents=True, exist_ok=True)
    LCD.mkdir(parents=True, exist_ok=True)
    frames = []

    # Image generation placed each row at a different vertical offset. These
    # equal-height row windows retain the intended bounce while giving every
    # LCD frame identical scale and alignment.
    row_crop_top = (170, 42)
    crop_height = 282
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
        top = row_crop_top[row]
        art = classify(cell.crop((0, top, cell_width, top + crop_height)))
        scaled_height = round(CANVAS_SIZE[0] * art.height / art.width)
        art = art.resize(
            (CANVAS_SIZE[0], scaled_height), Image.Resampling.NEAREST
        )
        frame = Image.new("RGB", CANVAS_SIZE, "black")
        frame.paste(art, (0, (CANVAS_SIZE[1] - scaled_height) // 2))
        frame.save(FRAMES / ("low_light_%d.png" % index))
        (LCD / ("low_light_%d.rgb565" % index)).write_bytes(
            pack_rgb565(frame)
        )
        frames.append(frame)

    frames[0].save(
        ASSET_ROOT / "low_light_animation.gif",
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
        ASSET_ROOT / "low_light_animation_preview.gif",
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
        ASSET_ROOT / "low_light_contact_sheet.png"
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
        "rgb565_pattern": "lcd/low_light_{0..7}.rgb565",
    }
    (ASSET_ROOT / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return frames


if __name__ == "__main__":
    built = build()
    print("built low-light animation:", len(built), "frames")
