#!/usr/bin/env python3
"""从小羊母版转写「小羊」这一栏的 Tab 图标 —— 整只羊，含腿，按原生格数。

母版实测：格宽 ≈ 97px，整只羊是 18 x 15 格。按这个格数 1:1 转写，
形体和原画完全一致，不做任何简化。

映射（Tab 图标是模板图，只有 alpha 会留下，双色必须用负形表达）：
    填充 = 整只羊的轮廓（云朵身体 + 黑耳朵 + 黑腿）
    挖空 = 脸（母版里最大的那块黑色连通域）
    填充 = 挖空里的两只白眼睛
轮廓负责"这是只羊"，挖空负责"这是张脸"。
"""
import sys
from PIL import Image

SRC = "apps/ios/Resources/Assets.xcassets/sheepNormal.imageset/sheepNormal.png"
NATIVE_W, NATIVE_H = 18, 15          # 母版的原生格数


def largest_dark_component(px, W, H, step):
    """脸和耳朵都是黑的。脸是最大的那块。"""
    dark = set()
    for y in range(0, H, step):
        for x in range(0, W, step):
            r, g, b, a = px[x, y]
            if a > 127 and r < 100:
                dark.add((x, y))
    seen, best = set(), set()
    for seed in dark:
        if seed in seen:
            continue
        stack, comp = [seed], set()
        while stack:
            p = stack.pop()
            if p in seen or p not in dark:
                continue
            seen.add(p); comp.add(p)
            x, y = p
            stack += [(x + step, y), (x - step, y), (x, y + step), (x, y - step)]
        if len(comp) > len(best):
            best = comp
    return best


def build(gw=NATIVE_W, gh=NATIVE_H, src=SRC):
    im = Image.open(src).convert("RGBA")
    W, H = im.size
    px = im.load()

    face = largest_dark_component(px, W, H, 4)
    fx0 = min(p[0] for p in face); fx1 = max(p[0] for p in face)
    fy0 = min(p[1] for p in face); fy1 = max(p[1] for p in face)

    xs = [x for y in range(0, H, 4) for x in range(0, W, 4) if px[x, y][3] > 127]
    ys = [y for y in range(0, H, 4) if any(px[x, y][3] > 127 for x in range(0, W, 4))]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    cw, ch = (x1 - x0 + 1) / gw, (y1 - y0 + 1) / gh

    cells = []
    for gy in range(gh):
        row = []
        for gx in range(gw):
            sx0, sx1 = int(x0 + gx * cw), int(x0 + (gx + 1) * cw)
            sy0, sy1 = int(y0 + gy * ch), int(y0 + (gy + 1) * ch)
            solid = eye = hole = 0
            for y in range(sy0, sy1, 2):
                for x in range(sx0, sx1, 2):
                    if x >= W or y >= H:
                        continue
                    r, g, b, a = px[x, y]
                    if a < 128:
                        continue
                    solid += 1
                    if fx0 <= x <= fx1 and fy0 <= y <= fy1:
                        (eye if r > 200 else hole).__class__     # noqa - 见下
                        if r > 200:
                            eye += 1
                        else:
                            hole += 1
            total = max(1, len(range(sy0, sy1, 2)) * len(range(sx0, sx1, 2)))
            on = solid / total >= 0.35 and not (hole > eye and hole / total >= 0.35)
            row.append(on)
        cells.append(row)
    return cells


if __name__ == "__main__":
    sys.path.insert(0, "tooling/asset_builders")
    from snap_tab_icons import ascii_art
    for row in build():
        print("".join("█" if c else "·" for c in row))
