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
    if points:
        item["absolutePoints"] = True
        item["points"] = points
    elements.append(item)


def label(element_id, x, y, width, value, color=GRAY, max_size=16):
    size = fit_font(value, width, 28, max_size, 11)
    add_text(element_id, x, y, width, 28, value, size, color, "center", "middle")


# Canvas and title.
rect(
    "canvas_frame",
    30,
    25,
    3240,
    1920,
    "#ffffff",
    "#adb5bd",
    rough=1,
    stroke_width=2,
    fill_style="solid",
)
add_text(
    "title",
    110,
    55,
    3080,
    58,
    "ESP32-S3 书桌学习伴侣 · 实机系统架构",
    42,
    DARK,
    "center",
    "middle",
)
add_text(
    "subtitle",
    110,
    118,
    3080,
    34,
    "真实输入 → ESP32 边缘计算 → SDK / Agent / Tool → 数据与实际输出",
    22,
    GRAY,
    "center",
    "middle",
)

# Legend.
legend_y = 174
legend = [
    (575, TEAM_FILL, BLUE, "团队开发"),
    (940, EXT_FILL, PURPLE, "第三方 SDK / 模型"),
    (1395, INPUT_FILL, ORANGE, "真实输入"),
    (1735, OUTPUT_FILL, GREEN, "实际输出"),
    (2070, OPTIONAL_FILL, RED, "预留未启用"),
]
for index, (x, fill, stroke, name) in enumerate(legend):
    rect(
        "legend_%d" % index,
        x,
        legend_y,
        46,
        28,
        fill,
        stroke,
        dashed=index == 4,
    )
    add_text(
        "legend_text_%d" % index,
        x + 58,
        legend_y - 2,
        250,
        32,
        name,
        18,
        DARK,
        "left",
        "middle",
    )

# Five large sections. More width and spacing prevents text/line collisions.
containers = [
    ("group_input", 60, 250, 380, 1630, CREAM, ORANGE, "① 真实输入"),
    ("group_edge", 480, 250, 760, 1630, "#e7f5ff", BLUE, "② ESP32-S3 边缘端"),
    ("group_channel", 1280, 250, 300, 1630, "#f8f0fc", PURPLE, "③ 数据通道"),
    ("group_ai", 1620, 250, 930, 1630, "#f8f0fc", PURPLE, "④ Mac + SDK / Agent / Tool"),
    ("group_output", 2590, 250, 650, 1630, "#ebfbee", GREEN, "⑤ 实际输出"),
]
for element_id, x, y, width, height, fill, stroke, title in containers:
    rect(element_id, x, y, width, height, fill, stroke, opacity=52)
    add_text(
        element_id + "_title",
        x + 18,
        y + 12,
        width - 36,
        42,
        title,
        25,
        stroke,
        "center",
        "middle",
    )

# ① Real inputs.
node(
    "input_presence",
    110,
    350,
    280,
    150,
    "儿童行为\n在座 / 移动 / 离开",
    INPUT_FILL,
    ORANGE,
    20,
    "ellipse",
)
node(
    "input_environment",
    110,
    630,
    280,
    150,
    "桌面环境\n光照 / 温度 / 湿度",
    INPUT_FILL,
    ORANGE,
    20,
    "ellipse",
)
node(
    "input_voice",
    110,
    930,
    280,
    150,
    "长按 IO10\n儿童真实语音",
    INPUT_FILL,
    ORANGE,
    20,
    "ellipse",
)
node(
    "input_repo",
    110,
    1510,
    280,
    140,
    "Git 提交\n代码 / 文档 / 素材",
    INPUT_FILL,
    ORANGE,
    20,
    "ellipse",
)

# ② ESP32 edge tools.
node(
    "esp_sdk",
    520,
    340,
    300,
    150,
    "MicroPython SDK / HAL\nGPIO · ADC · I²C\nSPI · I2S · Wi-Fi",
    EXT_FILL,
    PURPLE,
    20,
)
node(
    "esp_main",
    880,
    340,
    300,
    150,
    "main.py（团队）\n协作主循环\n显示调度 · 看门狗",
    TEAM_FILL,
    BLUE,
    20,
)
node(
    "esp_fusion",
    520,
    590,
    300,
    150,
    "传感器融合 Tool\nPIR + VL53L0X\nPRESENT / AWAY",
    TEAM_FILL,
    BLUE,
    20,
)
node(
    "esp_study",
    880,
    590,
    300,
    150,
    "学习系统 Tool\n计时 · 每日目标 · 成长\n体力 · Flash 持久化",
    TEAM_FILL,
    BLUE,
    20,
)
node(
    "esp_audio",
    520,
    930,
    300,
    150,
    "AudioManager Tool\n麦克风 RX / 扬声器 TX\n统一 I2S 仲裁",
    TEAM_FILL,
    BLUE,
    20,
)
node(
    "esp_voice",
    880,
    930,
    300,
    150,
    "VoiceQAClient Tool\n录音 · Wi-Fi · 重连\n协议状态机",
    TEAM_FILL,
    BLUE,
    20,
)
node(
    "esp_reminder",
    520,
    1210,
    300,
    150,
    "本地提醒 Tool\n喝水休息 / 低光照\nPCM 语音 + LCD 动画",
    TEAM_FILL,
    BLUE,
    20,
)
node(
    "esp_action",
    880,
    1210,
    300,
    150,
    "设备动作 Tool\n白名单校验 · 去重\n写入每日学习目标",
    TEAM_FILL,
    BLUE,
    20,
)

# ③ Network/data protocols.
node(
    "channel_discovery",
    1315,
    350,
    230,
    140,
    "UDP 8767\n发现 Mac 服务\n同步北京时间",
    TEAM_FILL,
    BLUE,
    19,
)
node(
    "channel_voice",
    1315,
    930,
    230,
    170,
    "TCP 8766\nVQW1 / VA01\nWAV · JSON · PCM16\nDevice Token",
    TEAM_FILL,
    BLUE,
    18,
)
node(
    "channel_event",
    1315,
    1450,
    230,
    145,
    "TCP 8766\nEVT1 / EV01\n行为与传感器 JSON",
    TEAM_FILL,
    BLUE,
    18,
)

# ④ Mac orchestration, SDK, Agent and tools.
node(
    "mac_server",
    1670,
    340,
    320,
    150,
    "Voice Server Tool\n鉴权 · 并发 · 编排\n事件接收",
    TEAM_FILL,
    BLUE,
    20,
)
node(
    "mimo_asr",
    2180,
    340,
    320,
    150,
    "MiMo v2.5 ASR\nWAV → 识别文字",
    EXT_FILL,
    PURPLE,
    21,
)
node(
    "tool_router",
    1860,
    590,
    440,
    190,
    "Tool Router\n学习问答\n或设备设置？",
    TEAM_FILL,
    BLUE,
    22,
    "diamond",
)
node(
    "mimo_agent",
    1670,
    920,
    320,
    160,
    "MiMo v2.5 Pro Agent\n团队 Prompt\n结构化答案 JSON",
    EXT_FILL,
    PURPLE,
    20,
)
node(
    "mimo_tts",
    2180,
    920,
    320,
    160,
    "MiMo v2.5 TTS\n文字 → PCM24\n团队重采样 PCM16",
    EXT_FILL,
    PURPLE,
    20,
)
node(
    "command_tool",
    1860,
    1190,
    440,
    160,
    "目标指令解析 Tool\n“每日目标改为 2 小时”\nset_daily_goal_seconds",
    TEAM_FILL,
    BLUE,
    20,
)
node(
    "event_sink",
    1670,
    1460,
    320,
    160,
    "Event Sink Tool\n本地 JSONL 优先\nPyMySQL + TLS",
    TEAM_FILL,
    BLUE,
    20,
)
node(
    "repo_sync",
    2180,
    1460,
    320,
    160,
    "Repository Sync Tool\n源码快照\n素材 SHA-256 清单",
    TEAM_FILL,
    BLUE,
    20,
)

# ⑤ Actual outputs.
node(
    "output_display",
    2670,
    340,
    490,
    180,
    "OLED + LCD\n北京时间 · 环境数据\n宠物 · 距离 · 学习时长\n成长值",
    OUTPUT_FILL,
    GREEN,
    22,
)
node(
    "output_speaker",
    2670,
    910,
    490,
    180,
    "I2S 扬声器\n本地提醒 · AI 回答\n设置确认语音",
    OUTPUT_FILL,
    GREEN,
    22,
)
node(
    "output_flash",
    2670,
    1180,
    490,
    180,
    "ESP32 Flash\npet_state.json · pet_config.json\nstate.txt",
    OUTPUT_FILL,
    GREEN,
    20,
)
node(
    "output_tidb",
    2670,
    1430,
    490,
    150,
    "TiDB Cloud\n行为 · 问答 · 代码快照\n素材清单",
    OUTPUT_FILL,
    GREEN,
    21,
)
node(
    "output_github",
    2670,
    1610,
    490,
    110,
    "GitHub\n源码 · 文档 · 素材",
    OUTPUT_FILL,
    GREEN,
    21,
)
node(
    "output_stack",
    2670,
    1750,
    490,
    70,
    "TiDB Agent Stack：接口预留，当前未配置",
    OPTIONAL_FILL,
    RED,
    17,
    dashed=True,
)

# Sensor and display path.
arrow("a_presence_sdk", "input_presence", "esp_sdk", ORANGE, 2.5)
arrow(
    "a_environment_sdk",
    "input_environment",
    "esp_sdk",
    ORANGE,
    2.5,
    points=[[390, 705], [455, 705], [455, 465], [520, 465]],
)
arrow("a_sdk_main", "esp_sdk", "esp_main", BLUE, 2.5)
arrow(
    "a_main_fusion",
    "esp_main",
    "esp_fusion",
    BLUE,
    2.5,
    points=[[880, 415], [850, 415], [850, 665], [820, 665]],
)
arrow("a_fusion_study", "esp_fusion", "esp_study", BLUE, 2.5)
arrow(
    "a_study_display",
    "esp_study",
    "output_display",
    GREEN,
    2.5,
    points=[[1180, 665], [1255, 665], [1255, 225], [2630, 225], [2630, 430], [2670, 430]],
)
label("label_gpio", 398, 395, 120, "GPIO / I²C", ORANGE, 15)
label("label_fusion", 815, 635, 95, "融合状态", BLUE, 14)
label("label_offline", 1880, 207, 310, "板端实时显示（离线可用）", GREEN, 16)

# Voice question path.
arrow("a_input_audio", "input_voice", "esp_audio", PURPLE, 2.5)
arrow("a_audio_voice", "esp_audio", "esp_voice", BLUE, 2.5)
arrow("a_voice_channel", "esp_voice", "channel_voice", PURPLE, 2.5)
arrow(
    "a_channel_server",
    "channel_voice",
    "mac_server",
    PURPLE,
    2.5,
    points=[[1545, 1015], [1600, 1015], [1600, 415], [1670, 415]],
)
arrow("a_server_asr", "mac_server", "mimo_asr", PURPLE, 2.5)
arrow("a_asr_router", "mimo_asr", "tool_router", PURPLE, 2.5)
arrow("a_router_agent", "tool_router", "mimo_agent", PURPLE, 2.5)
arrow("a_agent_tts", "mimo_agent", "mimo_tts", PURPLE, 2.5)
arrow("a_tts_speaker", "mimo_tts", "output_speaker", GREEN, 2.5)
label("label_i2s", 402, 965, 110, "I2S PCM", PURPLE, 14)
label("label_wav", 1190, 950, 125, "WAV + 上下文", PURPLE, 14)
label("label_https", 2030, 365, 100, "HTTPS", PURPLE, 14)
label("label_question", 1645, 845, 190, "普通学习问题", PURPLE, 14)
label("label_answer", 2000, 955, 160, "答案 JSON", PURPLE, 14)
label("label_pcm", 2505, 945, 160, "VA01 / PCM16", GREEN, 14)

# Voice command branch and Flash persistence.
arrow("a_router_command", "tool_router", "command_tool", BLUE, 2.5)
arrow(
    "a_command_action",
    "command_tool",
    "esp_action",
    BLUE,
    2.5,
    points=[[1860, 1270], [1600, 1270], [1600, 1165], [1260, 1165], [1260, 1285], [1180, 1285]],
)
arrow(
    "a_action_flash",
    "esp_action",
    "output_flash",
    GREEN,
    2.5,
    points=[[1180, 1285], [1260, 1285], [1260, 1390], [2600, 1390], [2600, 1270], [2670, 1270]],
)
label("label_action", 1320, 1137, 220, "device_action JSON", BLUE, 14)
label("label_flash", 2320, 1362, 220, "校验后写入 Flash", GREEN, 14)

# Local reminder path.
arrow(
    "a_main_reminder",
    "esp_main",
    "esp_reminder",
    BLUE,
    2.5,
    points=[[1030, 490], [1210, 490], [1210, 1140], [670, 1140], [670, 1210]],
)
arrow(
    "a_reminder_speaker",
    "esp_reminder",
    "output_speaker",
    GREEN,
    2.5,
    points=[[820, 1285], [850, 1285], [850, 1125], [2610, 1125], [2610, 1000], [2670, 1000]],
)
label("label_local_audio", 1850, 1097, 290, "本地 PCM + LCD 动画", GREEN, 15)

# Discovery and telemetry path.
arrow(
    "a_voice_discovery",
    "esp_voice",
    "channel_discovery",
    BLUE,
    2,
    points=[[1180, 1005], [1255, 1005], [1255, 420], [1315, 420]],
)
arrow("a_discovery_server", "channel_discovery", "mac_server", BLUE, 2)
arrow(
    "a_main_event",
    "esp_main",
    "channel_event",
    GREEN,
    2.5,
    points=[[1030, 490], [1260, 490], [1260, 1522], [1315, 1522]],
)
arrow("a_event_sink", "channel_event", "event_sink", GREEN, 2.5)
arrow(
    "a_server_sink",
    "mac_server",
    "event_sink",
    GREEN,
    2,
    points=[[1830, 490], [1640, 490], [1640, 1540], [1670, 1540]],
)
arrow(
    "a_sink_tidb",
    "event_sink",
    "output_tidb",
    GREEN,
    2.5,
    points=[[1990, 1540], [2040, 1540], [2040, 1400], [2600, 1400], [2600, 1505], [2670, 1505]],
)
arrow(
    "a_sink_stack",
    "event_sink",
    "output_stack",
    RED,
    2,
    dashed=True,
    points=[[1830, 1620], [1830, 1840], [2620, 1840], [2620, 1785], [2670, 1785]],
)
label("label_discovery", 1235, 500, 180, "发现 / 时间同步", BLUE, 14)
label("label_telemetry", 1245, 1490, 115, "telemetry", GREEN, 14)
label("label_tls", 2410, 1372, 140, "PyMySQL + TLS", GREEN, 14)
label("label_stack", 2260, 1812, 220, "可选 HTTP", RED, 14)

# Repository synchronization path.
arrow(
    "a_repo_sync",
    "input_repo",
    "repo_sync",
    BLUE,
    2.5,
    points=[[390, 1580], [455, 1580], [455, 1680], [2140, 1680], [2140, 1540], [2180, 1540]],
)
arrow(
    "a_sync_tidb",
    "repo_sync",
    "output_tidb",
    GREEN,
    2.5,
    points=[[2500, 1540], [2560, 1540], [2560, 1505], [2670, 1505]],
)
arrow(
    "a_sync_github",
    "repo_sync",
    "output_github",
    GREEN,
    2.5,
    points=[[2500, 1540], [2580, 1540], [2580, 1665], [2670, 1665]],
)
label("label_repo", 920, 1652, 330, "Git 历史 + SHA-256 清单", BLUE, 15)
label("label_git_push", 2510, 1635, 130, "git push", GREEN, 14)

# Ownership note.
add_text(
    "ownership_note",
    120,
    1900,
    3060,
    32,
    "团队开发：ESP32 固件、融合 / 成长 / 提醒算法、网络协议、Mac 编排、Prompt、Tool、TiDB 数据模型与部署测试。第三方：硬件、MicroPython、MiMo 模型、TiDB Cloud、GitHub。",
    18,
    DARK,
    "center",
    "middle",
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
