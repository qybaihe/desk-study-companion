# 交接 · Sheepy 底部导航四个图标

只做一件事：把 App 底部 Tab Bar 的四个图标从系统 SF Symbols 换成定制的像素图标。
不涉及别的页面、别的图标。

---

## 一、现状

`apps/ios/Sources/Views/RootView.swift` 现在用的是系统符号：

| 顺序 | 标签 | 现用 SF Symbol | 要替换成 |
| --- | --- | --- | --- |
| 1 | 此刻 | `square.grid.2x2` | `tabNow` |
| 2 | 小羊 | `pawprint` | `tabPet` |
| 3 | 周报 | `doc.text` | `tabWeekly` |
| 4 | 设置 | `gearshape` | `tabSettings` |

系统符号能用，但和产品没关系——尤其"小羊"这一栏用的是爪印，而我们的主角是一只
像素小羊，它自己的形象一次都没出现在导航里。

---

## 二、必须先理解的一条技术约束

**Tab Bar 图标是 template image（模板图），只有 alpha 通道会被保留，颜色会被系统丢掉。**

选中时系统用主题色 `#6B8F71`（鼠尾草绿）填充，未选中时用灰色填充。所以：

- 图标必须是**单色**（纯黑 `#000000`）+ 透明底。
- 不能有渐变、描边、阴影、高光、第二个颜色。
- 小羊原画是「白身体 + 黑脸 + 白眼睛」的双色，**这个双色在模板图里活不下来**。
  解决办法是改用负形：身体填充成实心，脸挖空成透明，眼睛在挖空区里再填两个实心小块。
  轮廓负责"这是只羊"，挖空负责"这是张脸"。

---

## 三、视觉语言

参考图（**请把这两张一起附给生图模型**）：

```
apps/ios/Resources/Assets.xcassets/sheepNormal.imageset/sheepNormal.png   ← 小羊母版
apps/ios/Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png         ← App 图标，看整体气质
```

小羊母版的关键度量（已实测）：

- 画布 1735 × 1432 px，RGBA 透明底
- **一个逻辑像素格 ≈ 100 px**，也就是整只羊画在约 **17 × 14 格**上
- 硬边，无抗锯齿，无描边

四个图标要落在**同一套网格**上才像一家人。

> **已修正：最终用的是 25 × 25 格，不是 16 × 16。**
> 16 格太粗，实测会把台灯的三道光线和设置的中间那条滑杆整个吃掉。
> 25 格的好处是 **1 格正好 1pt**：Tab 图标是 25 × 25 pt，@2x = 50px、
> @3x = 75px 都是整数倍，缩放不会糊边。下面的英文提示词仍写 16，
> 是因为生图模型本来就不会严格遵守格数，对齐是后期脚本做的。

---

## 四、四个图标画什么

### 1. `tabNow` — 此刻

一盏台灯。这一屏讲"现在书桌上正在发生什么"，而台灯是这个产品的核心物件
（护眼、光线判定都围着它）。

形态：上方一个梯形灯罩（下宽上窄），下面一根竖杆，最下是一条横的底座。
灯罩正下方三道短竖线，表示落在桌面上的光。左右对称。

### 2. `tabPet` — 小羊

小羊正面头像，从参考图转写。

形态：一整块实心的蓬松圆形团块（顶边呈云朵状的方块起伏）。团块的中下部挖掉一块
横向的矩形（完全透明）——那是脸。在这个透明的脸区里，并排放两个实心小方块当眼睛。
团块左右两侧各伸出一个小方块耳朵。

**不要**画身体、腿、五官线条。只要头部这一团。

### 3. `tabWeekly` — 周报

一个四根柱的小柱状图。周报页的封面签名图形就是七天柱状图，图标和它同构。

形态：四根等宽竖柱，站在同一条基线上，柱间空一格。从左到右高度是
矮 → 中 → 最高 → 中。柱顶是平的，不要圆角、不要坐标轴。

### 4. `tabSettings` — 设置

三条横滑块。齿轮在 16 格的单色小尺寸下齿会糊成一团；滑块在小尺寸下更清晰，
也更准确地说明"这里的东西能调"。

形态：三行横向排列。每行是一条贯穿大部分宽度的细横条，横条上坐着一个小方块滑钮。
三个滑钮的位置各不相同：第一行偏右、第二行偏左、第三行靠右端。

---

## 五、可直接粘贴的英文提示词

生图模型对英文的几何指令更稳。下面第一段是四张共用的风格前缀，每次把它和某一个
图标的描述拼在一起用。

### 共用风格前缀

```
Pixel-art icon glyph. Single flat color: pure black #000000 on a fully transparent
background. The entire design must read as a grid of 16 x 16 square cells; every cell
is either 100% filled black or 100% transparent — never partially filled, never grey.
Hard square edges only. No anti-aliasing, no gradients, no outlines, no strokes,
no shadows, no highlights, no second color. No text, no letters, no numbers.
Horizontally centered, with at least one empty cell of margin on all four sides.
Flat vector-like pixel art, in the style of an 8-bit sprite.
Output a 1024 x 1024 px PNG with an alpha channel.
```

### 1. tabNow

```
Subject: a front-facing desk lamp.
A wide trapezoid lampshade at the top (wider at the bottom edge, narrower at the top).
Below its center, a short vertical post two cells wide. At the bottom, a flat horizontal
base bar wider than the post. Directly beneath the lampshade, three short vertical
strokes of equal length, evenly spaced, representing light falling on the desk.
Left-right symmetrical.
```

### 2. tabPet

```
Subject: the front-facing head of a blocky pixel sheep. Match the attached reference
image's character.
One solid black rounded blob fills most of the canvas — the fluffy head. Its top and
side edges are made of stepped square bumps, like a cloud drawn on a pixel grid.
In the lower-middle of this blob, cut out a wide horizontal rectangular region so it
becomes fully transparent — this is the face. Inside that transparent face region,
place two small solid black squares side by side, evenly spaced, as the eyes.
On the left and right outer edges of the blob, one small square ear block sticks out
on each side.
Only the head. Do not draw a body, legs, nose, mouth, or any line work.
```

### 3. tabWeekly

```
Subject: a small bar chart of four vertical bars.
Four bars of equal width stand on a common baseline with exactly one empty cell of gap
between neighbours. From left to right their heights are: short, medium, tallest,
medium. All bar tops are flat. No axis lines, no baseline rule, no rounded corners,
no labels.
```

### 4. tabSettings

```
Subject: three horizontal slider controls stacked vertically.
Three evenly spaced rows. Each row is one thin horizontal bar, one cell tall, spanning
most of the canvas width. On each bar sits a small square knob, two cells wide and
taller than the bar. The three knobs are at different horizontal positions: the top
row's knob right of center, the middle row's knob left of center, the bottom row's
knob near the right end. No circles, no gear, no text.
```

---

## 六、输出规格

四张，PNG，带 alpha：

```
tabNow.png        1024 × 1024
tabPet.png        1024 × 1024
tabWeekly.png     1024 × 1024
tabSettings.png   1024 × 1024
```

生成完给我，我来做后续三件事：

1. **对齐网格**：生图模型不会真的落在 16 格上，边缘会有半格和灰边。要按 64px 一格
   重采样并做二值化（alpha > 50% 算填充），把它们真正压回像素网格。
2. **缩到 Tab Bar 尺寸**：25 × 25 pt，导出 @2x 50px / @3x 75px。
3. **进工程**：写进 `Assets.xcassets`，每个 imageset 的 `Contents.json` 设
   `"template-rendering-intent": "template"`，然后改 `RootView.swift`：

```swift
.tabItem { Label("此刻", image: "tabNow") }
```

---

## 七、验收标准

生成的图满足这几条才算能用：

- [ ] 背景**完全透明**，不是白色。白底会在 Tab Bar 上变成一个方块。
- [ ] 除了黑色没有第二个颜色。任何彩色都会被模板渲染丢掉，等于白画。
- [ ] 边缘是**直角方块**，看得出格子。斜线、圆弧、羽化边都不行。
- [ ] 缩到 25pt 看仍能分辨。四个图标**互相之间**要一眼能区分，
  这比每一个单独好看更重要。
- [ ] 四个图标的视觉重量差不多——不能有一个明显比另外三个黑一大块。
- [ ] 小羊那个：眯着眼看只剩轮廓时，仍然像一只羊，而不是一团东西。

最后一条是最容易失败的。如果模型给出的小羊头在缩小后糊成一坨，
就把脸的挖空区改大、眼睛改大，宁可牺牲写实度。


---

## 八、实际执行记录（2026-08-28）

四张图已生成并接入。过程中偏离原计划的地方：

### 网格从 16 改成"每张按自己的原生格数"

16 格太粗，实测会把台灯的三道光线和设置的中间那条滑杆整个吃掉。
四张原图的等效格数本来就是 27 / 25 / 10 / 36，各画各的。最终做法是
**先裁到内容边界，再按各自合适的格数压格，最后统一填满 25pt 方框的 96%**：

| 图标 | 格数 | 墨量 |
| --- | --- | --- |
| tabNow | 17 × 22 | 52% |
| tabPet | 30 × 25 | 66% |
| tabWeekly | 22 × 17 | 45% |
| tabSettings | 17 × 13 | 31% |

"裁到内容边界"这一步是关键：生成图周围留了一大圈空白，不裁直接用，
图标会显得比系统符号小一圈。

### 小羊直接用母版原图

模型给的那版是个光滑圆形加一条横缝，读起来像忍者面罩不像羊。改成从
`sheepNormal.png` 转写整只羊 —— 云朵身体、耳朵、脸、眼睛、腿一个不少。

关键是搞清楚母版的构造：**耳朵、脸、腿全是同一块白色轮廓内部的黑色区域**，
不是独立的形状。所以走"轮廓填充"（`alpha > 0`）只会得到一个纯色团块，
什么细节都没有。正确的映射是按母版自己的两色来：

```
白 → 填充      （云朵身体、眼睛）
黑 → 挖空      （脸、耳朵、腿）
```

这样模板渲染出来就是：绿色的羊身，脸和腿是镂空的。

工具：`tooling/asset_builders/build_pet_tab_icon.py` 的 `sheep_cells()`。

### 对齐暴露了原图的毛边，做了三处清理

都在 `make_tab_icons.py`：

- 台灯左右差一格 → 镜像对称
- 柱状图底边参差，几根柱看起来像浮着 → 补成规整矩形、统一基线
- 滑钮宽窄不一（4/5 格）、有一条滑杆是 2 格粗另两条 1 格 → 统一成 3×3 滑钮

### 遗留

小羊的墨量 66%，比另外三个（31–52%）重。这是它本身的形体决定的 ——
一只实心的动物旁边站着三个线条图形。吉祥物那一栏稍重是合理的，
真觉得跳可以把画面占比从 96% 调到 88%。

### 产物

```
apps/ios/Resources/Assets.xcassets/tab{Now,Pet,Weekly,Settings}.imageset/
    img@2x.png   50 × 50
    img@3x.png   75 × 75
    Contents.json   （已设 template-rendering-intent: template）
```

`RootView.swift` 已改成 `Label("此刻", image: "tabNow")`。模拟器上验过：
选中填主题绿、未选中填灰，模板渲染正常。

重新生成全部资源：

```bash
python3 tooling/asset_builders/make_tab_icons.py
```
