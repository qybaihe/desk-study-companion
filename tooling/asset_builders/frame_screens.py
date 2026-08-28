#!/usr/bin/env python3
"""给模拟器截图套上手机外框。

模拟器 `simctl io screenshot` 出来的是裸的方形帧缓冲，没有圆角也没有机身。
套一层框之后才能直接贴进 README 和演示稿。
"""
import os
from PIL import Image, ImageDraw

RAW = "docs/design/screens/raw"
OUT = "docs/design/screens"
TITLES = {
    "00-onboarding": "初次引导",
    "01-now": "此刻",
    "02-pet": "小羊",
    "03-weekly": "周报",
    "04-settings": "设置",
    "05-eye": "护眼",
    "06-env": "环境详情",
    "07-ask": "提问",
    "08-reminders": "提醒与响应",
    "09-study": "学习详情",
}

BEZEL = 26          # 机身边框厚度
R_OUT = 108         # 机身圆角
R_IN = 84           # 屏幕圆角
BODY = (58, 56, 52, 255)      # 机身：暖灰，和奶油卡片同族，不用纯黑
EDGE = (96, 93, 87, 255)      # 高光边
SHADOW = (0, 0, 0, 40)


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1],
                                        radius=radius, fill=255)
    return m


def frame(path, scale=0.5):
    shot = Image.open(path).convert("RGBA")
    w, h = shot.size
    shot.putalpha(rounded_mask((w, h), R_IN))

    W, H = w + BEZEL * 2, h + BEZEL * 2
    pad = 30
    out = Image.new("RGBA", (W + pad * 2, H + pad * 2), (0, 0, 0, 0))

    # 投影：往下偏一点，柔一点
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([0, 0, W - 1, H - 1], radius=R_OUT, fill=SHADOW)
    for dy in range(0, 14, 2):
        out.alpha_composite(sh, (pad, pad + dy))

    body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(body)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R_OUT, fill=BODY)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=R_OUT, outline=EDGE, width=3)
    out.alpha_composite(body, (pad, pad))
    out.alpha_composite(shot, (pad + BEZEL, pad + BEZEL))

    if scale != 1:
        out = out.resize((int(out.width * scale), int(out.height * scale)),
                         Image.LANCZOS)
    return out


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    made = []
    for f in sorted(os.listdir(RAW)):
        if not f.endswith(".png"):
            continue
        stem = f[:-4]
        im = frame(f"{RAW}/{f}")
        im.save(f"{OUT}/{stem}.png")
        made.append((stem, im.size))
        print("%-16s %s  %s" % (stem, TITLES.get(stem, ""), im.size))

    # 一张总览图，四个主页面横排
    main = ["01-now", "02-pet", "03-weekly", "04-settings"]
    ims = [Image.open(f"{OUT}/{n}.png") for n in main]
    gap = 20
    W = sum(i.width for i in ims) + gap * (len(ims) - 1)
    H = max(i.height for i in ims)
    board = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x = 0
    for i in ims:
        board.alpha_composite(i, (x, 0))
        x += i.width + gap
    board.save(f"{OUT}/overview.png")
    print("overview       ", board.size)
