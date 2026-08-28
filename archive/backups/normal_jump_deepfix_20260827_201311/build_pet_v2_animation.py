#!/usr/bin/env python3
"""Convert generated 2x2 pet sprite sheets into LCD-ready animation masks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops


ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "assets" / "pets" / "v2"
GENERATED = ASSET_ROOT / "generated"
FRAMES = ASSET_ROOT / "frames"
LCD = ASSET_ROOT / "lcd"
CANVAS_SIZE = (136, 112)

ANIMATIONS = {
    "normal": {
        "sheet": GENERATED / "normal_jump_sprite_sheet.png",
        "accent": (255, 255, 255),
        "duration_ms": 220,
        # Leave vertical headroom for the visible jump.  The generated poses
        # are centred independently before these deliberate LCD offsets are
        # applied: crouch, rise, apex, landing.
        "max_width": 116,
        "max_height": 92,
        "y_offsets": (7, -2, -10, 6),
    },
    "sick": {
        "sheet": GENERATED / "sick_sprite_sheet.png",
        "accent": (171, 216, 253),
        "duration_ms": 500,
    },
    "evolved": {
        "sheet": GENERATED / "evolved_sprite_sheet.png",
        "accent": (254, 176, 192),
        "duration_ms": 400,
    },
}


def sheet_frames(path: Path) -> list[Image.Image]:
    sheet = Image.open(path).convert("RGB")
    width, height = sheet.size
    x_edges = (0, width // 2, width)
    y_edges = (0, height // 2, height)
    return [
        sheet.crop((x_edges[column], y_edges[row], x_edges[column + 1], y_edges[row + 1]))
        for row, column in ((0, 0), (0, 1), (1, 0), (1, 1))
    ]


def classify(frame: Image.Image, state: str) -> tuple[Image.Image, Image.Image]:
    white = Image.new("L", frame.size, 0)
    accent = Image.new("L", frame.size, 0)
    source_pixels = frame.load()
    white_pixels = white.load()
    accent_pixels = accent.load()
    for y in range(frame.height):
        for x in range(frame.width):
            red, green, blue = source_pixels[x, y]
            maximum = max(red, green, blue)
            minimum = min(red, green, blue)
            chroma = maximum - minimum
            if maximum >= 145 and chroma < 38:
                white_pixels[x, y] = 255
            elif state == "sick" and blue >= 135 and blue - red >= 25:
                accent_pixels[x, y] = 255
            elif state == "evolved" and red >= 170 and red - green >= 28:
                accent_pixels[x, y] = 255
    return white, accent


def normalize(
    masks: list[tuple[Image.Image, Image.Image]],
    max_width: int = 132,
    max_height: int = 108,
    y_offsets: tuple[int, ...] | None = None,
) -> list[tuple[Image.Image, Image.Image]]:
    measurements = []
    for white, accent in masks:
        white_bbox = white.getbbox()
        total_bbox = ImageChops.lighter(white, accent).getbbox()
        if white_bbox is None or total_bbox is None:
            raise RuntimeError("animation frame has no pet foreground")
        center_x = (white_bbox[0] + white_bbox[2]) / 2
        center_y = (white_bbox[1] + white_bbox[3]) / 2
        measurements.append((center_x, center_y, total_bbox))

    max_left = max(center_x - bbox[0] for center_x, _center_y, bbox in measurements)
    max_right = max(bbox[2] - center_x for center_x, _center_y, bbox in measurements)
    max_top = max(center_y - bbox[1] for _center_x, center_y, bbox in measurements)
    max_bottom = max(bbox[3] - center_y for _center_x, center_y, bbox in measurements)
    scale = min(
        max_width / (max_left + max_right),
        max_height / (max_top + max_bottom),
    )

    if y_offsets is None:
        y_offsets = (0,) * len(masks)
    if len(y_offsets) != len(masks):
        raise ValueError("one y offset is required for every animation frame")

    canvas_width, canvas_height = CANVAS_SIZE
    result = []
    for (white, accent), (center_x, center_y, _bbox), y_offset in zip(
        masks, measurements, y_offsets
    ):
        resized_size = (
            max(1, round(white.width * scale)),
            max(1, round(white.height * scale)),
        )
        white = white.resize(resized_size, Image.Resampling.NEAREST)
        accent = accent.resize(resized_size, Image.Resampling.NEAREST)
        offset = (
            round(canvas_width / 2 - center_x * scale),
            round(canvas_height / 2 - center_y * scale + y_offset),
        )
        white_canvas = Image.new("L", CANVAS_SIZE, 0)
        accent_canvas = Image.new("L", CANVAS_SIZE, 0)
        white_canvas.paste(white, offset)
        accent_canvas.paste(accent, offset)
        result.append((white_canvas, accent_canvas))
    return result


def pack_hlsb(mask: Image.Image) -> bytes:
    width, height = mask.size
    row_bytes = (width + 7) // 8
    data = bytearray(row_bytes * height)
    pixels = mask.load()
    for y in range(height):
        for x in range(width):
            if pixels[x, y] >= 128:
                data[y * row_bytes + (x >> 3)] |= 1 << (x & 7)
    return bytes(data)


def composite(
    white: Image.Image,
    accent: Image.Image,
    accent_color: tuple[int, int, int],
) -> Image.Image:
    image = Image.new("RGB", CANVAS_SIZE, "black")
    image.paste(Image.new("RGB", CANVAS_SIZE, "white"), (0, 0), white)
    image.paste(Image.new("RGB", CANVAS_SIZE, accent_color), (0, 0), accent)
    return image


def pack_rgb565(image: Image.Image) -> bytes:
    """Pack pixels in the high-byte-first order expected by ST7789."""
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


def main() -> None:
    FRAMES.mkdir(parents=True, exist_ok=True)
    LCD.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "canvas": list(CANVAS_SIZE), "animations": {}}

    for state, spec in ANIMATIONS.items():
        raw_frames = sheet_frames(spec["sheet"])
        masks = normalize(
            [classify(frame, state) for frame in raw_frames],
            max_width=spec.get("max_width", 132),
            max_height=spec.get("max_height", 108),
            y_offsets=spec.get("y_offsets"),
        )
        preview_frames = []
        for index, (white, accent) in enumerate(masks):
            stem = f"{state}_{index}"
            white.save(FRAMES / f"{stem}_white.png")
            accent.save(FRAMES / f"{stem}_accent.png")
            (LCD / f"{stem}_white.mono").write_bytes(pack_hlsb(white))
            (LCD / f"{stem}_accent.mono").write_bytes(pack_hlsb(accent))
            composed = composite(white, accent, spec["accent"])
            composed.save(FRAMES / f"{stem}.png")
            (LCD / f"{stem}.rgb565").write_bytes(pack_rgb565(composed))
            preview_frames.append(composed)

        duration = spec["duration_ms"]
        preview_frames[0].save(
            ASSET_ROOT / f"{state}_animation.gif",
            save_all=True,
            append_images=preview_frames[1:],
            duration=duration,
            loop=0,
            disposal=2,
        )
        large_frames = [
            frame.resize((544, 448), Image.Resampling.NEAREST)
            for frame in preview_frames
        ]
        large_frames[0].save(
            ASSET_ROOT / f"{state}_animation_preview.gif",
            save_all=True,
            append_images=large_frames[1:],
            duration=duration,
            loop=0,
            disposal=2,
        )
        manifest["animations"][state] = {
            "frames": 4,
            "duration_ms": duration,
            "sheet": str(spec["sheet"].relative_to(ASSET_ROOT)),
            "sheet_sha256": hashlib.sha256(spec["sheet"].read_bytes()).hexdigest(),
            "accent_rgb": list(spec["accent"]),
            "frame_pattern": f"lcd/{state}_{{0..3}}_(white|accent).mono",
            "rgb565_pattern": f"lcd/{state}_{{0..3}}.rgb565",
        }

    normal_white = Image.open(
        ROOT / "assets" / "pets" / "lcd" / "pet_01_136x112_white.png"
    ).convert("L")
    normal_accent = Image.new("L", CANVAS_SIZE, 0)
    normal = composite(normal_white, normal_accent, (255, 255, 255))
    normal.save(FRAMES / "normal.png")
    (LCD / "normal.rgb565").write_bytes(pack_rgb565(normal))
    manifest["normal_rgb565"] = "lcd/normal.rgb565"
    manifest["normal_schedule"] = {
        "mode": "idle_then_one_shot",
        "interval_ms": 60_000,
        "frame_duration_ms": ANIMATIONS["normal"]["duration_ms"],
        "frames": 4,
    }

    (ASSET_ROOT / "animation_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print("built normal, sick and evolved animations: 4 frames each")


if __name__ == "__main__":
    main()
