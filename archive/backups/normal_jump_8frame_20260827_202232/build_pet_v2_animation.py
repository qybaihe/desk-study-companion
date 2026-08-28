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
        # A short anticipation, quick lift, readable apex and soft landing.
        "frame_durations_ms": (260, 220, 340, 260),
        # Every generated frame is normalized to exactly the same foreground
        # width.  Only its baseline changes, so the sheep moves vertically
        # instead of appearing to shrink and grow.
        "target_width": 108,
        "bottom_positions": (108, 100, 92, 108),
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


def normalize_jump(
    masks: list[tuple[Image.Image, Image.Image]],
    target_width: int,
    bottom_positions: tuple[int, ...],
) -> list[tuple[Image.Image, Image.Image]]:
    """Normalize a jump without changing apparent character scale.

    Image-generation sprite sheets often vary the character size slightly
    between panels.  Scaling every foreground to one width and anchoring each
    frame by its bottom edge removes that visual pop while preserving genuine
    pose changes such as a crouch.
    """
    if len(masks) != len(bottom_positions):
        raise ValueError("one bottom position is required for every jump frame")

    canvas_width, canvas_height = CANVAS_SIZE
    result = []
    for (white, accent), bottom in zip(masks, bottom_positions):
        foreground = ImageChops.lighter(white, accent)
        bbox = foreground.getbbox()
        if bbox is None:
            raise RuntimeError("jump frame has no pet foreground")

        white = white.crop(bbox)
        accent = accent.crop(bbox)
        target_height = max(1, round(white.height * target_width / white.width))
        if target_height > canvas_height:
            raise RuntimeError("normalized jump frame is taller than its canvas")

        size = (target_width, target_height)
        white = white.resize(size, Image.Resampling.NEAREST)
        accent = accent.resize(size, Image.Resampling.NEAREST)
        x = (canvas_width - target_width) // 2
        y = bottom - target_height
        if y < 0 or bottom > canvas_height:
            raise RuntimeError("jump baseline places a frame outside its canvas")

        white_canvas = Image.new("L", CANVAS_SIZE, 0)
        accent_canvas = Image.new("L", CANVAS_SIZE, 0)
        white_canvas.paste(white, (x, y))
        accent_canvas.paste(accent, (x, y))
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
    manifest = {"version": 2, "canvas": list(CANVAS_SIZE), "animations": {}}
    normal_idle = None

    for state, spec in ANIMATIONS.items():
        raw_frames = sheet_frames(spec["sheet"])
        classified = [classify(frame, state) for frame in raw_frames]
        if state == "normal":
            masks = normalize_jump(
                classified,
                target_width=spec["target_width"],
                bottom_positions=spec["bottom_positions"],
            )
        else:
            masks = normalize(classified)
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

        frame_durations = spec.get("frame_durations_ms")
        duration = frame_durations or spec["duration_ms"]
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
        animation_manifest = {
            "frames": 4,
            "duration_ms": (
                spec.get("duration_ms")
                or round(sum(frame_durations) / len(frame_durations))
            ),
            "sheet": str(spec["sheet"].relative_to(ASSET_ROOT)),
            "sheet_sha256": hashlib.sha256(spec["sheet"].read_bytes()).hexdigest(),
            "accent_rgb": list(spec["accent"]),
            "frame_pattern": f"lcd/{state}_{{0..3}}_(white|accent).mono",
            "rgb565_pattern": f"lcd/{state}_{{0..3}}.rgb565",
        }
        if frame_durations:
            animation_manifest["frame_durations_ms"] = list(frame_durations)
            animation_manifest["total_duration_ms"] = sum(frame_durations)
        manifest["animations"][state] = animation_manifest

        if state == "normal":
            # The resting sprite is byte-for-byte the landing frame.  Returning
            # from the one-shot animation therefore has no scale/position jump.
            normal_idle = preview_frames[3].copy()

            contact = Image.new("RGB", (CANVAS_SIZE[0] * 2, CANVAS_SIZE[1] * 2))
            for index, frame in enumerate(preview_frames):
                contact.paste(
                    frame,
                    ((index % 2) * CANVAS_SIZE[0], (index // 2) * CANVAS_SIZE[1]),
                )
            contact.resize((544, 448), Image.Resampling.NEAREST).save(
                ASSET_ROOT / "normal_jump_contact_sheet.png"
            )

    if normal_idle is None:
        raise RuntimeError("normal landing frame was not built")
    normal = normal_idle
    normal.save(FRAMES / "normal.png")
    (LCD / "normal.rgb565").write_bytes(pack_rgb565(normal))
    manifest["normal_rgb565"] = "lcd/normal.rgb565"
    manifest["normal_schedule"] = {
        "mode": "idle_then_one_shot",
        "interval_ms": 60_000,
        "frame_durations_ms": list(ANIMATIONS["normal"]["frame_durations_ms"]),
        "total_duration_ms": sum(ANIMATIONS["normal"]["frame_durations_ms"]),
        "frames": 4,
    }

    (ASSET_ROOT / "animation_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print("built normal, sick and evolved animations: 4 frames each")


if __name__ == "__main__":
    main()
