"""把设备端 LCD 帧（136x112 RGB 黑底）还原成透明 PNG。

设备只画白色和配件色，黑色既是 LCD 背景，也是羊的五官和腿。
区分办法：
  1) 被白色完全包围的黑（从边缘泛洪够不到）→ 五官
  2) 同一行里左右都有白色的黑 → 切进身体的缺口，也就是腿
其余的黑才是背景，置透明。
"""
from PIL import Image
from collections import deque, Counter
import os


def rebuild(stem):
    rgb = Image.open(f'{stem}.png').convert('RGB')
    w, h = rgb.size
    P = rgb.load()
    wm, am = f'{stem}_white.png', f'{stem}_accent.png'
    if os.path.exists(wm) and os.path.exists(am):
        Wm = Image.open(wm).convert('L').load()
        Am = Image.open(am).convert('L').load()
        is_white = lambda x, y: Wm[x, y] >= 128
        is_acc   = lambda x, y: Am[x, y] >= 128
    else:
        is_white = lambda x, y: P[x, y] == (255, 255, 255)
        is_acc   = lambda x, y: P[x, y] not in ((0, 0, 0), (255, 255, 255))
    cols = Counter(c for c in rgb.getdata() if c not in ((0, 0, 0), (255, 255, 255)))
    accent = cols.most_common(1)[0][0] if cols else (0, 0, 0)
    black = lambda x, y: not is_white(x, y) and not is_acc(x, y)

    # ① 从边缘泛洪：够得到的黑是候选背景
    isbg = [[False] * w for _ in range(h)]
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if black(x, y) and not isbg[y][x]: isbg[y][x] = True; q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if black(x, y) and not isbg[y][x]: isbg[y][x] = True; q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not isbg[ny][nx] and black(nx, ny):
                isbg[ny][nx] = True; q.append((nx, ny))

    # ② 腿：黑段左右紧贴白色、且足够窄。
    #    母版里腿宽约占身宽 9%（33 逻辑像素里占 3），这里放宽到 14/136。
    #    宽度上限是必需的：跳跃帧中间的白色分隔会消失，若不限宽会把
    #    两腿之间的整片背景填成黑杠。左右必须是"白"而不是"配件色"，
    #    否则羊身和三叶草/红花之间的空隙也会被误填。
    MAXW = max(6, round(w * 14 / 136))
    for y in range(h):
        x = 0
        while x < w:
            if black(x, y):
                x0 = x
                while x < w and black(x, y): x += 1
                run = x - x0
                left_white  = x0 - 1 >= 0 and is_white(x0 - 1, y)
                right_white = x < w and is_white(x, y)
                if left_white and right_white and run <= MAXW:
                    for xx in range(x0, x): isbg[y][xx] = False
            else:
                x += 1

    out = Image.new('RGBA', (w, h), (0, 0, 0, 0)); O = out.load()
    for y in range(h):
        for x in range(w):
            if is_acc(x, y):     O[x, y] = accent + (255,)
            elif is_white(x, y): O[x, y] = (255, 255, 255, 255)
            elif not isbg[y][x]: O[x, y] = (0, 0, 0, 255)
    return out, accent
