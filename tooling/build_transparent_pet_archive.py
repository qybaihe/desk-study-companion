#!/usr/bin/env python3
"""Build a verified transparent-background archive of every pet image."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "firmware" / "assets" / "pets"
DEFAULT_OUTPUT = (
    REPO_ROOT / "releases" / "lulu-sheep-transparent-assets-v1.zip"
)
IMAGE_SUFFIXES = {".png", ".gif"}
FLOOD_THRESHOLD = 24
ZIP_TIMESTAMP = (2026, 8, 28, 0, 0, 0)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()


def transparent_frame(frame: Image.Image, source_name: str) -> Image.Image:
    """Remove only the border-connected background and preserve black details."""
    rgba = frame.convert("RGBA")
    width, height = rgba.size
    corners = ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1))

    for corner in corners:
        red, green, blue, alpha = rgba.getpixel(corner)
        if alpha == 0:
            continue
        if max(red, green, blue) > 64:
            raise ValueError(
                f"{source_name}: corner {corner} is not a dark background pixel"
            )
        ImageDraw.floodfill(
            rgba,
            corner,
            value=(0, 0, 0, 0),
            thresh=FLOOD_THRESHOLD,
        )

    alpha_min, _alpha_max = rgba.getchannel("A").getextrema()
    if alpha_min != 0:
        raise ValueError(f"{source_name}: transparency validation failed")
    if any(rgba.getpixel(corner)[3] != 0 for corner in corners):
        raise ValueError(f"{source_name}: one or more corners remain opaque")
    return rgba


def save_png(source: Path, destination: Path) -> tuple[int, int, int]:
    with Image.open(source) as image:
        output = transparent_frame(image, source.as_posix())
        output.save(destination, format="PNG", optimize=True)
        return output.width, output.height, 1


def gif_palette_frame(rgba: Image.Image) -> Image.Image:
    """Reserve palette index 0 for binary GIF transparency."""
    quantized = rgba.convert("RGB").quantize(
        colors=255,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.NONE,
    )
    alpha = rgba.getchannel("A")
    pixels = list(quantized.get_flattened_data())
    alpha_pixels = list(alpha.get_flattened_data())
    output = Image.new("P", rgba.size, color=0)
    output.putdata([
        0 if alpha_value == 0 else color_index + 1
        for color_index, alpha_value in zip(pixels, alpha_pixels)
    ])
    source_palette = quantized.getpalette() or []
    palette = [0, 0, 0] + source_palette[: 255 * 3]
    palette.extend([0] * (768 - len(palette)))
    output.putpalette(palette)
    output.info["transparency"] = 0
    output.info["disposal"] = 2
    return output


def save_gif(source: Path, destination: Path) -> tuple[int, int, int]:
    frames: list[Image.Image] = []
    durations: list[int] = []
    with Image.open(source) as animation:
        loop = int(animation.info.get("loop", 0))
        for index in range(getattr(animation, "n_frames", 1)):
            animation.seek(index)
            frames.append(
                gif_palette_frame(
                    transparent_frame(
                        animation.convert("RGBA"), f"{source.as_posix()}#{index}"
                    )
                )
            )
            durations.append(int(animation.info.get("duration", 100)))

    frames[0].save(
        destination,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=loop,
        disposal=2,
        transparency=0,
        background=0,
        optimize=False,
    )
    return frames[0].width, frames[0].height, len(frames)


def verify_image(path: Path) -> tuple[int, int, int]:
    with Image.open(path) as image:
        width, height = image.size
        frame_count = getattr(image, "n_frames", 1)
        for index in range(frame_count):
            image.seek(index)
            rgba = image.convert("RGBA")
            alpha_min, _alpha_max = rgba.getchannel("A").getextrema()
            if alpha_min != 0:
                raise ValueError(f"{path}: frame {index} has invalid alpha")
            corners = (
                (0, 0),
                (width - 1, 0),
                (0, height - 1),
                (width - 1, height - 1),
            )
            if any(rgba.getpixel(point)[3] != 0 for point in corners):
                raise ValueError(f"{path}: frame {index} has an opaque corner")
        return width, height, frame_count


def write_zip(source_dir: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in source_dir.rglob("*") if item.is_file()):
            relative = path.relative_to(source_dir).as_posix()
            info = zipfile.ZipInfo(relative, date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)


def build(output: Path) -> dict[str, object]:
    sources = sorted(
        path
        for path in SOURCE_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    if not sources:
        raise RuntimeError("No pet images found")

    with tempfile.TemporaryDirectory(prefix="transparent-pets-") as temp_name:
        stage = Path(temp_name) / "lulu-sheep-transparent-assets-v1"
        image_root = stage / "images"
        entries: list[dict[str, object]] = []

        for source in sources:
            relative = source.relative_to(SOURCE_ROOT)
            destination = image_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix.lower() == ".png":
                width, height, frame_count = save_png(source, destination)
            else:
                width, height, frame_count = save_gif(source, destination)
            verify_image(destination)
            entries.append(
                {
                    "source_path": source.relative_to(REPO_ROOT).as_posix(),
                    "archive_path": (Path("images") / relative).as_posix(),
                    "format": source.suffix.lower().lstrip("."),
                    "width": width,
                    "height": height,
                    "frames": frame_count,
                    "transparent_background_verified": True,
                    "source_sha256": sha256(source),
                    "output_sha256": sha256(destination),
                }
            )

        manifest = {
            "package": "lulu-sheep-transparent-assets-v1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_git_commit": git_commit(),
            "source_root": "firmware/assets/pets",
            "image_count": len(entries),
            "png_count": sum(entry["format"] == "png" for entry in entries),
            "gif_count": sum(entry["format"] == "gif" for entry in entries),
            "all_backgrounds_transparent": True,
            "conversion": {
                "method": "border-connected corner background to alpha",
                "flood_threshold": FLOOD_THRESHOLD,
                "black_features_preserved": True,
            },
            "files": entries,
        }
        (stage / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (stage / "README.md").write_text(
            "# 噜噜羊透明背景素材包 v1\n\n"
            f"- 图片总数：{len(entries)}\n"
            f"- PNG：{manifest['png_count']}\n"
            f"- GIF：{manifest['gif_count']}\n"
            "- 所有图片及GIF逐帧验证：四角透明且包含透明像素。\n"
            "- 只移除与画布边缘连通的背景，羊脸、耳朵、眼睛等黑色细节保持不变。\n"
            "- 包内也保留LCD白色层/强调色层等技术图片；没有强调色的空层会是全透明图片。\n"
            "- `images/` 保留原素材目录结构，`manifest.json` 包含尺寸和SHA-256。\n",
            encoding="utf-8",
        )
        sums = "\n".join(
            f"{entry['output_sha256']}  {entry['archive_path']}" for entry in entries
        )
        (stage / "SHA256SUMS.txt").write_text(sums + "\n", encoding="utf-8")
        write_zip(stage, output)

    sidecar = output.with_suffix(output.suffix + ".sha256")
    sidecar.write_text(f"{sha256(output)}  {output.name}\n", encoding="utf-8")
    return {
        "output": str(output),
        "sha256": sha256(output),
        "size_bytes": output.stat().st_size,
        "image_count": len(sources),
        "png_count": sum(path.suffix.lower() == ".png" for path in sources),
        "gif_count": sum(path.suffix.lower() == ".gif" for path in sources),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    print(json.dumps(build(arguments.output.resolve()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
