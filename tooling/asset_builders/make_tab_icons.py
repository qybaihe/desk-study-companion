#!/usr/bin/env python3
"""生成 Tab Bar 四个图标的最终资源。

要点：
  1. **先裁到内容边界再压格**。生图模型给的四张周围留了一大圈空白，
     直接用会显得图标很小；裁掉之后按 96% 填满 25pt 的方框。
  2. 压回像素网格。四张原图的等效格数是 27/25/10/36，各画各的，
     不统一就不像一家人。
  3. 清理对齐后暴露的毛边：台灯不对称、柱子底边参差、滑钮宽窄不一。
  4. **小羊直接用母版原图**，按它自己的两色转写：
     白 → 填充，黑 → 挖空。这样耳朵、脸、眼睛、腿一个不少 ——
     母版里这些全是同一块白色轮廓内部的黑色区域，走"轮廓填充"
     只会得到一个纯色团块。
"""
import json, os, sys
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from snap_tab_icons import render, ascii_art

PT = 25                 # Tab 图标是 25 x 25 pt
FILL = 0.96             # 图形占画面的比例
SRC = "docs/design/tabbar-icons-generated"
DST = "apps/ios/Resources/Assets.xcassets"
SHEEP = "apps/ios/Resources/Assets.xcassets/sheepNormal.imageset/sheepNormal.png"


def bbox(px, W, H, step=2):
    xs = [x for y in range(0, H, step) for x in range(0, W, step) if px[x, y][3] > 127]
    ys = [y for y in range(0, H, step) if any(px[x, y][3] > 127 for x in range(0, W, step))]
    return min(xs), min(ys), max(xs), max(ys)


def snap_cropped(path, long_cells):
    """裁到内容边界，再把长边压成 long_cells 格。"""
    im = Image.open(path).convert("RGBA"); W, H = im.size; px = im.load()
    x0, y0, x1, y1 = bbox(px, W, H)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    if bw >= bh:
        gw = long_cells; gh = max(1, round(long_cells * bh / bw))
    else:
        gh = long_cells; gw = max(1, round(long_cells * bw / bh))
    cw, ch = bw / gw, bh / gh
    cells = []
    for gy in range(gh):
        row = []
        for gx in range(gw):
            sx0, sx1 = int(x0 + gx * cw), int(x0 + (gx + 1) * cw)
            sy0, sy1 = int(y0 + gy * ch), int(y0 + (gy + 1) * ch)
            on = tot = 0
            for y in range(sy0, sy1, 2):
                for x in range(sx0, sx1, 2):
                    if x >= W or y >= H:
                        continue
                    tot += 1
                    if px[x, y][3] > 127:
                        on += 1
            row.append(on / max(1, tot) >= 0.35)
        cells.append(row)
    return cells


def sheep_cells(long_cells):
    """母版转写：白 = 填充，黑 = 挖空。"""
    im = Image.open(SHEEP).convert("RGBA"); W, H = im.size; px = im.load()
    x0, y0, x1, y1 = bbox(px, W, H, 4)
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    gw = long_cells; gh = max(1, round(long_cells * bh / bw))
    cw, ch = bw / gw, bh / gh
    cells = []
    for gy in range(gh):
        row = []
        for gx in range(gw):
            sx0, sx1 = int(x0 + gx * cw), int(x0 + (gx + 1) * cw)
            sy0, sy1 = int(y0 + gy * ch), int(y0 + (gy + 1) * ch)
            wht = tot = 0
            for y in range(sy0, sy1, 2):
                for x in range(sx0, sx1, 2):
                    if x >= W or y >= H:
                        continue
                    tot += 1
                    r, g, b, a = px[x, y]
                    if a > 127 and r > 200:
                        wht += 1
            row.append(wht / max(1, tot) >= 0.40)
        cells.append(row)
    return cells


# ── 对齐后的毛边清理 ────────────────────────────────────────

def mirror(cells):
    """台灯本来就该左右对称，模型画歪了一格。"""
    w = len(cells[0])
    for row in cells:
        for x in range(w // 2):
            v = row[x] or row[w - 1 - x]
            row[x] = row[w - 1 - x] = v
    return cells


def flatten_bars(cells):
    """柱状图：每根柱补成规整矩形，统一坐在同一条基线上。"""
    h, w = len(cells), len(cells[0])
    cols = [x for x in range(w) if any(cells[y][x] for y in range(h))]
    if not cols:
        return cells
    bars, cur = [], [cols[0]]
    for x in cols[1:]:
        if x == cur[-1] + 1:
            cur.append(x)
        else:
            bars.append(cur)
            cur = [x]          # 新建列表，不能 clear ——
            #                    那会把已经存进 bars 的同一个列表也清空
    bars.append(cur)
    base = max(y for y in range(h) for x in cols if cells[y][x])
    for bar in bars:
        # 只补规整、对齐基线；不强行统一宽度 —— 最右那根贴着画面边缘，
        # 强行拉宽会被裁掉反而更窄
        top = min(y for y in range(h) for x in bar if cells[y][x])
        for y in range(h):
            for x in bar:
                cells[y][x] = (top <= y <= base)
    return cells


def normalize_knobs(cells):
    """滑块：滑钮统一成 3x3，竖直压在滑杆上。"""
    h, w = len(cells), len(cells[0])
    for y in [y for y in range(h) if sum(cells[y]) > w * 0.5]:
        knob = [x for x in range(w)
                if (y > 0 and cells[y-1][x]) or (y+1 < h and cells[y+1][x])]
        if not knob:
            continue
        cx = (min(knob) + max(knob)) // 2
        for dy in (-2, -1, 1, 2):
            yy = y + dy
            if 0 <= yy < h:
                for x in range(w):
                    cells[yy][x] = False
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                yy, xx = y + dy, cx + dx
                if 0 <= yy < h and 0 <= xx < w:
                    cells[yy][xx] = True
    return cells


def draw(cells, size):
    """把不一定是方形的格阵按 FILL 比例居中画进方形画布。"""
    gh, gw = len(cells), len(cells[0])
    span = size * FILL
    cell = span / max(gw, gh)
    ox = (size - cell * gw) / 2
    oy = (size - cell * gh) / 2
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = out.load()
    for gy, row in enumerate(cells):
        for gx, on in enumerate(row):
            if not on:
                continue
            for y in range(int(oy + gy * cell), int(oy + (gy + 1) * cell)):
                for x in range(int(ox + gx * cell), int(ox + (gx + 1) * cell)):
                    if 0 <= x < size and 0 <= y < size:
                        d[x, y] = (0, 0, 0, 255)
    return out


CONTENTS = {
    "images": [
        {"idiom": "universal", "scale": "1x"},
        {"idiom": "universal", "filename": "img@2x.png", "scale": "2x"},
        {"idiom": "universal", "filename": "img@3x.png", "scale": "3x"},
    ],
    "info": {"author": "xcode", "version": 1},
    # 模板渲染：只保留 alpha，选中时系统填主题绿，未选中填灰
    "properties": {"template-rendering-intent": "template"},
}


def main():
    icons = {
        "tabNow":      mirror(snap_cropped(f"{SRC}/tabNow.png", 22)),
        "tabPet":      sheep_cells(30),
        "tabWeekly":   flatten_bars(snap_cropped(f"{SRC}/tabWeekly.png", 22)),
        "tabSettings": normalize_knobs(snap_cropped(f"{SRC}/tabSettings.png", 17)),
    }
    for name, cells in icons.items():
        gh, gw = len(cells), len(cells[0])
        ink = sum(sum(r) for r in cells) * 100 / (gw * gh)
        print("=== %-12s %2dx%-2d 格  墨量 %.0f%% ===" % (name, gw, gh, ink))
        print(ascii_art(cells))
        d = f"{DST}/{name}.imageset"
        os.makedirs(d, exist_ok=True)
        for scale in (2, 3):
            draw(cells, PT * scale).save(f"{d}/img@{scale}x.png")
        with open(f"{d}/Contents.json", "w") as f:
            json.dump(CONTENTS, f, indent=2)
        draw(cells, 1024).save(f"{SRC}/{name}_final.png")
        print()


if __name__ == "__main__":
    main()
