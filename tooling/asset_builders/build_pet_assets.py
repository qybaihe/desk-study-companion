#!/usr/bin/env python3
"""Archive the four pet masters and build the first 240x240 LCD sprite."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2] / "firmware"
PET_ROOT = ROOT / "assets" / "pets"
ORIGINALS = PET_ROOT / "originals"
NORMALIZED = PET_ROOT / "normalized"
LCD = PET_ROOT / "lcd"

PETS = (
    (
        "pet_01_idle.png",
        "idle",
        Path("/var/folders/8q/n48vz7vs4g7cjccgy_lsf51w0000gn/T/"
             "codex-clipboard-e2426ee7-73d9-4376-91d0-67bc07080f11.png"),
    ),
    (
        "pet_02_clover.png",
        "clover",
        Path("/var/folders/8q/n48vz7vs4g7cjccgy_lsf51w0000gn/T/"
             "codex-clipboard-422afcca-465a-4d0a-b4a5-c2a3a9ef13a0.png"),
    ),
    (
        "pet_03_red_flower.png",
        "red_flower",
        Path("/var/folders/8q/n48vz7vs4g7cjccgy_lsf51w0000gn/T/"
             "codex-clipboard-76a683dd-f671-453d-8c40-14aa331dee8c.png"),
    ),
    (
        "pet_04_blush.png",
        "blush",
        Path("/var/folders/8q/n48vz7vs4g7cjccgy_lsf51w0000gn/T/"
             "codex-clipboard-d6f44724-38d8-42ed-93f9-4bd574f6503e.png"),
    ),
)


def archive_masters() -> list[dict[str, object]]:
    for directory in (ORIGINALS, NORMALIZED, LCD):
        directory.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, object]] = []
    for index, (filename, pose, attachment) in enumerate(PETS, start=1):
        target = ORIGINALS / filename
        if not target.exists():
            if not attachment.exists():
                raise FileNotFoundError(
                    f"Neither archived master nor attachment exists for {filename}"
                )
            shutil.copy2(attachment, target)

        image = Image.open(target).convert("RGB")
        # All normalized frames retain the same square canvas. This makes future
        # animation alignment/interpolation predictable without altering masters.
        normalized = image.resize((512, 512), Image.Resampling.NEAREST)
        normalized.save(NORMALIZED / filename, optimize=True)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest.append(
            {
                "id": index,
                "pose": pose,
                "master": f"originals/{filename}",
                "normalized": f"normalized/{filename}",
                "master_size": list(image.size),
                "normalized_size": [512, 512],
                "sha256": digest,
            }
        )

    (PET_ROOT / "manifest.json").write_text(
        json.dumps(
            {
                "asset_set": "desk_companion_pet_v1",
                "masters_are_immutable": True,
                "frame_alignment": "normalized files share a 512x512 canvas",
                "pets": manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def pet_masks(filename: str) -> tuple[Image.Image, Image.Image]:
    image = Image.open(ORIGINALS / filename).convert("RGB")
    # Classification is done on a smaller nearest-neighbour canvas. Neutral
    # pixels form the white sheep; saturated pixels form its coloured prop.
    image = image.resize((512, 512), Image.Resampling.NEAREST)
    white_source = Image.new("L", image.size, 0)
    accent_source = Image.new("L", image.size, 0)
    white_pixels = white_source.load()
    accent_pixels = accent_source.load()
    source_pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = source_pixels[x, y]
            maximum = max(red, green, blue)
            minimum = min(red, green, blue)
            if maximum >= 128 and maximum - minimum < 30:
                white_pixels[x, y] = 255
            elif maximum >= 100 and maximum - minimum >= 30:
                accent_pixels[x, y] = 255

    foreground = Image.new("L", image.size, 0)
    foreground = Image.frombytes(
        "L",
        image.size,
        bytes(
            255 if white or accent else 0
            for white, accent in zip(
                white_source.getdata(), accent_source.getdata()
            )
        ),
    )
    bbox = foreground.getbbox()
    if bbox is None:
        raise RuntimeError(f"{filename} has no visible foreground")
    white_source = white_source.crop(bbox)
    accent_source = accent_source.crop(bbox)

    canvas_width, canvas_height = 136, 112
    max_width, max_height = 132, 108
    scale = min(max_width / white_source.width, max_height / white_source.height)
    width = max(1, round(white_source.width * scale))
    height = max(1, round(white_source.height * scale))
    offset = ((canvas_width - width) // 2, (canvas_height - height) // 2)

    white_source = white_source.resize((width, height), Image.Resampling.NEAREST)
    accent_source = accent_source.resize((width, height), Image.Resampling.NEAREST)
    white_canvas = Image.new("L", (canvas_width, canvas_height), 0)
    accent_canvas = Image.new("L", (canvas_width, canvas_height), 0)
    white_canvas.paste(white_source, offset)
    accent_canvas.paste(accent_source, offset)
    white_canvas = white_canvas.point(lambda value: 255 if value >= 128 else 0)
    accent_canvas = accent_canvas.point(lambda value: 255 if value >= 128 else 0)
    return white_canvas, accent_canvas


def pack_hlsb(mask: Image.Image) -> bytes:
    """Pack one-bit rows as MONO_HLSB-compatible bytes."""
    width, height = mask.size
    row_bytes = (width + 7) // 8
    packed = bytearray(row_bytes * height)
    pixels = mask.load()
    for y in range(height):
        offset = y * row_bytes
        for x in range(width):
            if pixels[x, y] >= 128:
                packed[offset + (x >> 3)] |= 1 << (x & 7)
    return bytes(packed)


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/Monaco.ttf",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def build_preview(mask: Image.Image) -> None:
    preview = Image.new("RGB", (240, 240), "black")
    draw = ImageDraw.Draw(preview)
    white = (255, 255, 255)
    font8 = load_font(8)
    font12 = load_font(12)
    font16 = load_font(16)

    preview.paste(Image.new("RGB", mask.size, white), (7, 43), mask)
    draw.text((8, 9), "PET 01", fill=white, font=font8)
    draw.line((7, 28, 143, 28), fill=white)
    draw.text((46, 166), "MOMO", fill=white, font=font16)
    draw.text((31, 189), "DESK BUDDY", fill=white, font=font8)
    draw.line((18, 216, 132, 216), fill=white)
    draw.ellipse((70, 222, 75, 227), fill=white)

    draw.rectangle((153, 4, 235, 235), outline=white)
    draw.text((171, 11), "LIGHT", fill=white, font=font8)
    cx, cy = 194, 45
    draw.rectangle((188, 39, 200, 51), fill=white)
    for x1, y1, x2, y2 in (
        (194, 31, 194, 36), (194, 54, 194, 59),
        (180, 45, 185, 45), (203, 45, 208, 45),
        (184, 35, 187, 38), (201, 52, 204, 55),
        (184, 55, 187, 52), (201, 38, 204, 35),
    ):
        draw.line((x1, y1, x2, y2), fill=white)
    draw.text((162, 69), "3950", fill=white, font=font16)
    draw.text((168, 89), "ADC AVG", fill=white, font=font8)
    draw.rectangle((164, 108, 224, 121), outline=white)
    draw.rectangle((166, 110, 221, 119), fill=white)
    draw.text((171, 134), "96%", fill=white, font=font16)
    draw.text((171, 160), "BRIGHT", fill=white, font=font8)
    draw.line((164, 182, 224, 182), fill=white)
    draw.text((164, 194), "L1 3948", fill=white, font=font8)
    draw.text((164, 210), "L2 3952", fill=white, font=font8)

    preview.save(LCD / "lcd_pet_light_preview_240.png")
    preview.resize((720, 720), Image.Resampling.NEAREST).save(
        LCD / "lcd_pet_light_preview_720.png"
    )


def build_growth_preview(
    white_mask: Image.Image,
    accent_mask: Image.Image,
    accent_color: tuple[int, int, int],
) -> None:
    preview = Image.new("RGB", (240, 240), "black")
    draw = ImageDraw.Draw(preview)
    white = (255, 255, 255)
    font8 = load_font(8)
    font16 = load_font(16)

    preview.paste(Image.new("RGB", white_mask.size, white), (7, 36), white_mask)
    preview.paste(
        Image.new("RGB", accent_mask.size, accent_color),
        (7, 36),
        accent_mask,
    )
    draw.text((8, 9), "PET LV1", fill=white, font=font8)
    draw.line((7, 27, 143, 27), fill=white)
    draw.text((46, 156), "MOMO", fill=white, font=font16)
    draw.text((17, 184), "SESSION 00:42", fill=white, font=font8)
    draw.text((17, 202), "GOAL 4H 17%", fill=white, font=font8)
    draw.text((43, 222), "FOCUS +3", fill=white, font=font8)

    draw.rectangle((153, 4, 235, 235), outline=white)
    draw.text((174, 10), "STATS", fill=white, font=font8)
    draw.text((164, 30), "HP", fill=white, font=font8)
    draw.text((200, 30), "86", fill=white, font=font8)
    draw.rectangle((164, 44, 60 + 164, 53), outline=white)
    draw.rectangle((166, 46, 166 + 47, 51), fill=white)
    draw.text((164, 62), "GROW", fill=white, font=font8)
    draw.text((200, 62), "18", fill=white, font=font8)
    draw.rectangle((164, 76, 224, 85), outline=white)
    draw.rectangle((166, 78, 166 + 10, 83), fill=white)
    draw.text((174, 96), "TODAY", fill=white, font=font8)
    draw.text((174, 110), "00:42", fill=white, font=font8)
    draw.line((164, 126, 224, 126), fill=white)
    draw.text((164, 138), "L 95% OK", fill=white, font=font8)
    draw.text((164, 158), "D 060 OK", fill=white, font=font8)
    draw.line((164, 184, 224, 184), fill=white)
    draw.text((164, 202), "PRESENT", fill=white, font=font8)

    preview.save(LCD / "lcd_pet_growth_preview_240.png")
    preview.resize((720, 720), Image.Resampling.NEAREST).save(
        LCD / "lcd_pet_growth_preview_720.png"
    )


def build_stage_contact_sheet(
    stages: list[tuple[Image.Image, Image.Image, tuple[int, int, int]]],
) -> None:
    sheet = Image.new("RGB", (600, 180), (14, 18, 24))
    draw = ImageDraw.Draw(sheet)
    font = load_font(14)
    for index, (white_mask, accent_mask, accent_color) in enumerate(stages):
        x = index * 150 + 7
        sheet.paste(Image.new("RGB", white_mask.size, "white"), (x, 30), white_mask)
        sheet.paste(
            Image.new("RGB", accent_mask.size, accent_color),
            (x, 30),
            accent_mask,
        )
        draw.text((x + 38, 8), f"STAGE {index + 1}", fill="white", font=font)
        threshold = ("0-24", "25-59", "60-99", "100+")[index]
        draw.text((x + 48, 152), threshold, fill="white", font=font)
    sheet.save(LCD / "pet_growth_stages.png")


def main() -> None:
    manifest = archive_masters()
    accent_colors = (
        (255, 255, 255),
        (77, 215, 123),
        (228, 30, 45),
        (255, 176, 190),
    )
    stages = []
    for index, (filename, _pose, _attachment) in enumerate(PETS, start=1):
        white_mask, accent_mask = pet_masks(filename)
        prefix = f"pet_{index:02d}_136x112"
        white_mask.save(LCD / f"{prefix}_white.png")
        accent_mask.save(LCD / f"{prefix}_accent.png")
        (LCD / f"{prefix}_white.mono").write_bytes(pack_hlsb(white_mask))
        (LCD / f"{prefix}_accent.mono").write_bytes(pack_hlsb(accent_mask))
        stages.append((white_mask, accent_mask, accent_colors[index - 1]))

    # Keep the original stage-1 filename for compatibility with earlier builds.
    stage_one = stages[0][0]
    stage_one.save(LCD / "pet_01_idle_136x112.png")
    packed = pack_hlsb(stage_one)
    (LCD / "pet_01_idle_136x112.mono").write_bytes(packed)
    build_preview(stage_one)
    build_growth_preview(*stages[0])
    build_stage_contact_sheet(stages)
    print(f"archived {len(manifest)} pet masters")
    print(f"LCD masks: 4 stages, 2 layers each, {len(packed)} bytes/layer")


if __name__ == "__main__":
    main()
