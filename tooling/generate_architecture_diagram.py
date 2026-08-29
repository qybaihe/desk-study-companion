#!/usr/bin/env python3
"""Generate the clear, editable Chinese Excalidraw system architecture."""

import json
import math
import sys
import unicodedata
from pathlib import Path


OUT = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/tmp/desk-study-companion-architecture.excalidraw"
)
elements = []
seed = 200

DARK = "#1e1e1e"
BLUE = "#1971c2"
GREEN = "#2f9e44"
ORANGE = "#e8590c"
PURPLE = "#862e9c"
RED = "#c92a2a"
GRAY = "#868e96"
TEAM_FILL = "#a5d8ff"
EXT_FILL = "#d0bfff"
INPUT_FILL = "#ffec99"
OUTPUT_FILL = "#b2f2bb"
OPTIONAL_FILL = "#ffc9c9"
CREAM = "#fff4e6"


def next_seed():
    global seed
    seed += 1
    return seed


def rect(
    element_id,
    x,
    y,
    width,
    height,
    fill,
    stroke=DARK,
    rough=1,
    stroke_width=2,
    fill_style="hachure",
    opacity=100,
    dashed=False,
):
    item = {
        "type": "rectangle",
        "id": element_id,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "strokeColor": stroke,
        "backgroundColor": fill,
        "fillStyle": fill_style,
        "strokeWidth": stroke_width,
        "roughness": rough,
        "seed": next_seed(),
        "opacity": opacity,
    }
    if dashed:
        item["strokeStyle"] = "dashed"
    elements.append(item)


def ellipse(element_id, x, y, width, height, fill, stroke=DARK):
    elements.append(
        {
            "type": "ellipse",
            "id": element_id,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "strokeColor": stroke,
            "backgroundColor": fill,
            "fillStyle": "hachure",
            "strokeWidth": 2,
            "roughness": 1,
            "seed": next_seed(),
        }
    )


def diamond(element_id, x, y, width, height, fill, stroke=DARK):
    elements.append(
        {
            "type": "diamond",
            "id": element_id,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "strokeColor": stroke,
            "backgroundColor": fill,
            "fillStyle": "hachure",
            "strokeWidth": 2,
            "roughness": 1,
            "seed": next_seed(),
        }
    )


def text_units(value):
    """Estimate rendered em width; used only to keep labels inside boxes."""
    total = 0.0
    for char in value:
        if char.isspace():
            total += 0.32
        elif unicodedata.east_asian_width(char) in ("W", "F", "A"):
            total += 1.0
        elif char.isupper() or char.isdigit():
            total += 0.67
        elif char in "._-/+→·：:()（）":
            total += 0.48
        else:
            total += 0.58
    return total


def fit_font(value, width, height, maximum, minimum=13):
    lines = value.splitlines() or [value]
    widest = max(text_units(line) for line in lines) or 1
    horizontal = width / (widest * 1.08)
    vertical = height / (len(lines) * 1.30)
    return max(minimum, min(maximum, int(math.floor(horizontal)), int(math.floor(vertical))))


def add_text(
    element_id,
    x,
    y,
    width,
    height,
    value,
    size=20,
    color=DARK,
    align="left",
    valign="top",
    family=1,
):
    elements.append(
        {
            "type": "text",
            "id": element_id,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "text": value,
            "fontSize": size,
            "fontFamily": family,
            "strokeColor": color,
            "textAlign": align,
            "verticalAlign": valign,
            "lineHeight": 1.25,
        }
    )


def node(
    element_id,
    x,
    y,
    width,
    height,
    value,
    fill=TEAM_FILL,
    stroke=BLUE,
    max_size=21,
    shape="rectangle",
    dashed=False,
):
    if shape == "ellipse":
        ellipse(element_id, x, y, width, height, fill, stroke)
        pad_x, pad_y = width * 0.15, height * 0.18
    elif shape == "diamond":
        diamond(element_id, x, y, width, height, fill, stroke)
        pad_x, pad_y = width * 0.23, height * 0.20
    else:
        rect(element_id, x, y, width, height, fill, stroke, dashed=dashed)
        pad_x, pad_y = 18, 16
    text_width = width - 2 * pad_x
    text_height = height - 2 * pad_y
    size = fit_font(value, text_width, text_height, max_size)
    add_text(
        element_id + "_text",
        x + pad_x,
        y + pad_y,
        text_width,
        text_height,
        value,
        size,
        DARK,
        "center",
        "middle",
    )


def arrow(
    element_id,
    source,
    target,
    color=DARK,
    stroke_width=2,
    dashed=False,
    points=None,
    start=False,
):
    item = {
        "type": "arrow",
        "id": element_id,
        "from": source,
        "to": target,
        "strokeColor": color,
        "strokeWidth": stroke_width,
        "roughness": 1,
        "seed": next_seed(),
    }
    if dashed:
        item["strokeStyle"] = "dashed"
    if start:
        item["startArrowhead"] = True
    if points:
        item["absolutePoints"] = True
        item["points"] = points
    elements.append(item)


def label(element_id, x, y, width, value, color=GRAY, max_size=16):
    size = fit_font(value, width, 28, max_size, 11)
    add_text(element_id, x, y, width, 28, value, size, color, "center", "middle")


# One-page judge-facing architecture: only the core experience and ownership.
rect(
    "canvas_frame", 30, 25, 3140, 1740, "#ffffff", "#adb5bd",
    rough=1, stroke_width=2, fill_style="solid",
)
add_text(
    "title", 100, 48, 3000, 58,
    "ESP32-S3 书桌学习伴侣 · 一页架构图",
    42, DARK, "center", "middle",
)
add_text(
    "subtitle", 100, 110, 3000, 38,
    "三条可追踪闭环：本地感知与提醒 ｜ 儿童语音问答 ｜ 家长云端查看与控制",
    23, GRAY, "center", "middle",
)

# Ownership legend required by the competition brief.
legend = [
    ("平台 / 主办方提供", EXT_FILL, PURPLE),
    ("团队配置 / 集成", INPUT_FILL, ORANGE),
    ("团队自主开发", TEAM_FILL, BLUE),
    ("实际输出 / 已接通", OUTPUT_FILL, GREEN),
    ("接口预留", OPTIONAL_FILL, RED),
]
lx = 420
for index, (name, fill, stroke) in enumerate(legend):
    x = lx + index * 470
    rect("legend_%d" % index, x, 170, 42, 28, fill, stroke, stroke_width=2)
    add_text("legend_text_%d" % index, x + 55, 168, 330, 32, name, 18, DARK, "left", "middle")

# Six required layers.
groups = [
    ("group_input", 50, 250, 390, 1390, "① 真实世界输入", ORANGE),
    ("group_device", 460, 250, 420, 1390, "② 实体设备", PURPLE),
    ("group_cap", 900, 250, 500, 1390, "③ 设备能力层", BLUE),
    ("group_conn", 1420, 250, 350, 1390, "④ 连接方式", ORANGE),
    ("group_smart", 1790, 250, 800, 1390, "⑤ 智能层 / 服务层", PURPLE),
    ("group_output", 2610, 250, 540, 1390, "⑥ 实际输出", GREEN),
]
for gid, x, y, w, h, title, color in groups:
    rect(gid, x, y, w, h, "#ffffff", color, rough=1, stroke_width=2,
         fill_style="solid", opacity=22)
    add_text(gid + "_title", x + 18, y + 16, w - 36, 42, title, 25, color, "center", "middle")

# Row 1: local sensing and reminder loop.
node(
    "input_sense", 90, 350, 310, 190,
    "儿童在座 / 移动 / 离开\n桌面光照 · 温度 · 湿度",
    INPUT_FILL, ORANGE, 23, "ellipse",
)
node(
    "device_sensors", 500, 335, 340, 230,
    "ESP32-S3 传感器套件\nPIR · VL53L0X\n双路光敏 · DHT11",
    EXT_FILL, PURPLE, 23,
)
node(
    "cap_sdk", 950, 325, 400, 150,
    "MicroPython SDK / HAL\nGPIO · ADC · I²C · SPI · I2S",
    INPUT_FILL, ORANGE, 22,
)
node(
    "cap_fusion", 950, 500, 400, 170,
    "传感器融合 + 学习 Tool\nPRESENT / AWAY\n距离 · 计时 · 成长 · 提醒",
    TEAM_FILL, BLUE, 22,
)
node(
    "conn_local", 1460, 370, 270, 170,
    "板内连接\nGPIO / I²C / ADC / I2S\n团队引脚配置",
    INPUT_FILL, ORANGE, 21,
)
node(
    "smart_local", 1840, 350, 700, 200,
    "本地规则 Tools（团队自主开发）\n融合状态机 · 阈值滞回 · 学习成长规则 · 提醒调度\n不依赖云端，断网仍工作",
    TEAM_FILL, BLUE, 23,
)
node(
    "output_local", 2660, 335, 440, 250,
    "OLED + LCD + 扬声器\n北京时间 · 光照温湿度\n在座 · 距离 · 连续学习时长\n低光 / 休息喝水提醒与动画",
    OUTPUT_FILL, GREEN, 22,
)

# Row 2: voice learning loop.
node(
    "input_voice", 90, 755, 310, 180,
    "长按 IO10\n儿童真实语音问题",
    INPUT_FILL, ORANGE, 24, "ellipse",
)
node(
    "device_audio", 500, 720, 340, 250,
    "ESP32-S3 音频硬件\nI2S 数字麦克风\nI2S 功放 + 扬声器\nIO10 按键",
    EXT_FILL, PURPLE, 22,
)
node(
    "cap_audio", 950, 720, 400, 250,
    "AudioManager + VoiceQAClient\n录音 / WAV / I2S 仲裁\n非阻塞状态机 · 鉴权 · 重连",
    TEAM_FILL, BLUE, 22,
)
node(
    "conn_lan", 1460, 760, 270, 180,
    "Wi-Fi 局域网\nUDP 发现 + TCP 双向\n语音 / JSON / PCM",
    INPUT_FILL, ORANGE, 21,
)
node(
    "smart_voice_team", 1840, 700, 290, 280,
    "Mac Custom Service\n团队 Prompt\nTool Router\n编排 · 鉴权 · 答案裁剪",
    TEAM_FILL, BLUE, 22,
)
node(
    "smart_mimo", 2190, 700, 350, 280,
    "MiMo 智能层\nASR → Agent → TTS\n语音识别 · 学习答疑\n流式语音生成",
    EXT_FILL, PURPLE, 23,
)
node(
    "output_voice", 2660, 730, 440, 230,
    "板载扬声器实际播报\n儿童问题的 AI 答案\n设置确认语音",
    OUTPUT_FILL, GREEN, 24,
)

# Row 3: cloud telemetry and parent control loop.
node(
    "input_parent", 90, 1160, 310, 220,
    "家长真实操作\n查看数据 · 修改目标/阈值\n喂草 · 奖励 · 给孩子捎话",
    INPUT_FILL, ORANGE, 22, "ellipse",
)
node(
    "device_cloud", 500, 1115, 340, 280,
    "ESP32-S3 网络与存储\nWi-Fi · Flash · SD\n60 秒样本与宠物状态\n离线 spool",
    EXT_FILL, PURPLE, 22,
)
node(
    "cap_net", 950, 1115, 400, 280,
    "Net 云同步 / 下行 Tool\n后台 HTTPS · NTP/Worker 对时\n补传 · 配置 rev · 动作/消息音频执行",
    TEAM_FILL, BLUE, 22,
)
node(
    "conn_cloud", 1460, 1160, 270, 210,
    "Wi-Fi + HTTPS 双向\nPOST /ingest\nGET /pull\nBearer Token",
    INPUT_FILL, ORANGE, 21,
)
node(
    "smart_worker", 1840, 1090, 310, 260,
    "Cloudflare Worker\n团队 Custom Service / API Tools\n鉴权 · 换算 · 聚合\n配置 / 动作 / 消息队列",
    TEAM_FILL, BLUE, 21,
)
node(
    "smart_tidb", 2200, 1090, 340, 260,
    "TiDB Cloud + Serverless SDK\n传感器 · 学习 · 宠物 · 配置\n实时查询与周报数据",
    EXT_FILL, PURPLE, 22,
)
node(
    "smart_skill", 1980, 1390, 420, 100,
    "TiDB Agent Stack / 家长问数 Skill：接口预留，未接通",
    OPTIONAL_FILL, RED, 18, dashed=True,
)
node(
    "output_ios", 2660, 1070, 440, 300,
    "原生 iOS 1.0 家长端（SwiftUI）\n实时专注 / 护眼 / 周报 / 设置\n喂草 · 奖励 · 给孩子捎话\n10 秒轮询 + 本地真实缓存",
    OUTPUT_FILL, GREEN, 22,
)
node(
    "output_action", 2660, 1420, 440, 150,
    "ESP32 实际动作\n落盘配置 · 改成长/体力\nOLED 捎话 + TTS 播报 · LCD 动画",
    OUTPUT_FILL, GREEN, 21,
)

# Main row arrows make the three experiences readable without source code.
arrow("a_sense_device", "input_sense", "device_sensors", ORANGE, 3)
arrow("a_device_sdk", "device_sensors", "cap_sdk", BLUE, 3)
arrow("a_sdk_fusion", "cap_sdk", "cap_fusion", BLUE, 3)
arrow("a_fusion_conn", "cap_fusion", "conn_local", BLUE, 3)
arrow("a_conn_local", "conn_local", "smart_local", BLUE, 3)
arrow("a_local_output", "smart_local", "output_local", GREEN, 3)
label("l_local", 1910, 320, 550, "闭环 1：感知 → 判断 → 板端显示 / 提醒", GREEN, 18)

arrow("a_voice_device", "input_voice", "device_audio", ORANGE, 3)
arrow("a_device_audio", "device_audio", "cap_audio", BLUE, 3)
arrow("a_audio_lan", "cap_audio", "conn_lan", BLUE, 3)
arrow("a_lan_mac", "conn_lan", "smart_voice_team", BLUE, 3)
arrow("a_mac_mimo", "smart_voice_team", "smart_mimo", PURPLE, 3, start=True)
arrow("a_mimo_voice", "smart_mimo", "output_voice", GREEN, 3)
label("l_voice", 1910, 670, 550, "闭环 2：语音 → Agent → 流式回答", PURPLE, 18)

# Cloud data flows left to right; control returns to Net Tool.
arrow("a_cloud_device", "device_cloud", "cap_net", GREEN, 3)
arrow("a_net_https", "cap_net", "conn_cloud", GREEN, 3, start=True)
arrow("a_https_worker", "conn_cloud", "smart_worker", GREEN, 3, start=True)
arrow("a_worker_tidb", "smart_worker", "smart_tidb", PURPLE, 3, start=True)
arrow("a_tidb_ios", "smart_tidb", "output_ios", GREEN, 3)
arrow(
    "a_parent_ios", "input_parent", "output_ios", ORANGE, 3,
    points=[[400, 1270], [430, 1270], [430, 1585], [2580, 1585], [2580, 1220], [2640, 1220]],
)
label("l_parent", 1100, 1550, 650, "家长真实操作", ORANGE, 18)
label("l_cloud", 1880, 1050, 620, "闭环 3：设备数据 ↔ TiDB ↔ iOS 家长端", GREEN, 18)

# Explicit hardware-capability mapping required by the brief:
# Tool/control -> connection -> SDK -> physical device action.
arrow(
    "a_control_back", "smart_worker", "cap_net", ORANGE, 3,
    points=[[1830, 1270], [1775, 1270], [1775, 1515], [1420, 1515], [1420, 1270], [1370, 1270]],
)
arrow(
    "a_cap_action", "cap_net", "output_action", ORANGE, 3,
    points=[[1150, 1410], [1150, 1600], [2580, 1600], [2580, 1495], [2640, 1495]],
)
label(
    "l_control", 1380, 1510, 1050,
    "硬件能力映射：家长 / Tool → HTTPS → Net SDK → ESP32 配置、显示、TTS 播报、动画与数值动作",
    ORANGE, 18,
)

add_text(
    "footer", 90, 1680, 3020, 42,
    "团队自主开发：ESP32 固件与算法、音频/网络协议、Mac 编排、Prompt、Tool、Worker API、iOS App、数据模型与产品体验。",
    21, DARK, "center", "middle",
)

payload = {
    "type": "excalidraw",
    "version": 2,
    "source": "desk-study-companion",
    "elements": elements,
    "appState": {"viewBackgroundColor": "#fffdf8"},
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(OUT)
print("elements", len(elements))
