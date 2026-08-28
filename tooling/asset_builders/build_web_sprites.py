#!/usr/bin/env python3
"""把 iOS 端的小羊逐帧素材打包成 Landing Page 用的横向精灵图。

iOS 端 (apps/ios/Resources/Assets.xcassets) 每个状态一组 animXxxN.png，
各状态画布尺寸不同但像素栅格一致（都是 LCD 母版的 6 倍最近邻放大）。
本脚本按「脸罩水平中心 + 画布底边(着地线)」对齐到统一画布，再横向拼成
一条精灵图，供 CSS steps() 逐帧播放。

输出: apps/landing/assets/sheep/<state>.png + sprites.json
"""
import json
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "apps/ios/Resources/Assets.xcassets"
OUT = ROOT / "apps/landing/assets/sheep"

# (状态, 前缀, 帧数, fps) —— fps 与 apps/ios/Sources/Models.swift 的 PetForm.animation 一致
STATES = [
    ("normal",    "animNormal",    31, 14.0),
    ("lowlight",  "animLowLight",   8,  8.0),
    ("restbreak", "animRestBreak",  8,  8.0),
    ("evolved",   "animEvolved",    4,  5.0),
    ("sick",      "animSick",       4,  3.5),
]
DOWNSCALE = 2          # 6x 母版降到 3x，仍是整数倍，保持像素锐利


def face_center_x(im):
    """脸罩（纯黑块）最宽一行的水平中心，作为对齐锚点。"""
    px = im.load()
    w, h = im.size
    best = (0, 0)
    for y in range(h):
        run = start = 0
        for x in range(w + 1):
            r, g, b, a = px[x, y] if x < w else (255, 255, 255, 0)
            if a > 128 and r < 40 and g < 40 and b < 40:
                if run == 0:
                    start = x
                run += 1
            else:
                if run > best[0]:
                    best = (run, start)
                run = 0
    return best[1] + best[0] / 2


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    loaded, anchors = {}, {}
    for key, prefix, n, _ in STATES:
        frames = [Image.open(SRC / f"{prefix}{i}.imageset/{prefix}{i}.png").convert("RGBA")
                  for i in range(n)]
        loaded[key] = frames
        anchors[key] = face_center_x(frames[0])

    # 统一画布：左右取各状态锚点两侧的最大延伸，底边对齐
    left = max(anchors[k] for k, *_ in STATES)
    right = max(loaded[k][0].width - anchors[k] for k, *_ in STATES)
    half = int(max(left, right))
    cw, ch = half * 2, max(loaded[k][0].height for k, *_ in STATES)

    meta = {"frameWidth": cw // DOWNSCALE, "frameHeight": ch // DOWNSCALE, "states": {}}
    for key, prefix, n, fps in STATES:
        sheet = Image.new("RGBA", (cw * n, ch), (0, 0, 0, 0))
        dx = int(half - anchors[key])
        for i, f in enumerate(loaded[key]):
            sheet.paste(f, (i * cw + dx, ch - f.height), f)
        sheet = sheet.resize((sheet.width // DOWNSCALE, sheet.height // DOWNSCALE), Image.NEAREST)
        path = OUT / f"{key}.png"
        sheet.save(path, optimize=True)
        meta["states"][key] = {"frames": n, "fps": fps, "file": f"{key}.png"}
        print(f"{key:10s} {n:2d}帧 {sheet.width}x{sheet.height} {path.stat().st_size/1024:.0f}KB")

    (OUT / "sprites.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    print(f"\n统一帧画布 {meta['frameWidth']}x{meta['frameHeight']}")


if __name__ == "__main__":
    main()
