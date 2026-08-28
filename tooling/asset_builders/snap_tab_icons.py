#!/usr/bin/env python3
"""把生成的 Tab 图标压回统一的像素网格，并导出 @2x/@3x。

生图模型不会真的落在指定的格子上 —— 实测四张的等效格数是
27 / 25 / 10 / 36，各画各的。四个图标不在同一套网格上就不像一家人。

覆盖率阈值取 0.35 而不是 0.5：设置图标的滑杆只有 28px 粗（不到半格），
按半数判定会整条消失。
"""
import argparse, os
from PIL import Image

GRID = 16
CANVAS = 1024


def snap(path, grid=GRID, coverage=0.35):
    im = Image.open(path).convert("RGBA")
    W, H = im.size
    px = im.load()
    cw, ch = W / grid, H / grid
    cells = []
    for gy in range(grid):
        row = []
        for gx in range(grid):
            x0, x1 = int(gx * cw), int((gx + 1) * cw)
            y0, y1 = int(gy * ch), int((gy + 1) * ch)
            on = 0
            for y in range(y0, y1, 2):
                for x in range(x0, x1, 2):
                    if px[x, y][3] > 127:
                        on += 1
            total = max(1, len(range(y0, y1, 2)) * len(range(x0, x1, 2)))
            row.append(on / total >= coverage)
        cells.append(row)
    return cells


def render(cells, size=CANVAS):
    grid = len(cells)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = out.load()
    cell = size / grid
    for gy, row in enumerate(cells):
        for gx, on in enumerate(row):
            if not on:
                continue
            for y in range(int(gy * cell), int((gy + 1) * cell)):
                for x in range(int(gx * cell), int((gx + 1) * cell)):
                    d[x, y] = (0, 0, 0, 255)
    return out


def ascii_art(cells):
    return "\n".join("".join("█" if c else "·" for c in row) for row in cells)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out")
    ap.add_argument("--grid", type=int, default=GRID)
    ap.add_argument("--coverage", type=float, default=0.35)
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    cells = snap(a.src, a.grid, a.coverage)
    if a.show:
        print(os.path.basename(a.src))
        print(ascii_art(cells))
    if a.out:
        render(cells).save(a.out)
