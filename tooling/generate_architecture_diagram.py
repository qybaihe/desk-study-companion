#!/usr/bin/env python3
"""Generate the editable Chinese Excalidraw system-architecture source."""

import json
import sys
from pathlib import Path


OUT = Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else "/tmp/desk-study-companion-architecture.excalidraw"
)
elements = []
seed = 100

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


def text(
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
    size=20,
    shape="rectangle",
    dashed=False,
):
    if shape == "diamond":
        diamond(element_id, x, y, width, height, fill, stroke)
    elif shape == "ellipse":
        ellipse(element_id, x, y, width, height, fill, stroke)
    else:
        rect(
            element_id,
            x,
            y,
            width,
            height,
            fill,
            stroke,
            dashed=dashed,
        )
    text(
        element_id + "_text",
        x + 10,
        y + 7,
        width - 20,
        height - 14,
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


def label(element_id, x, y, width, value, color=GRAY, size=15, align="center"):
    text(element_id, x, y, width, 28, value, size, color, align, "top")


# Background and title.
rect(
    "canvas_frame",
    30,
    25,
    2380,
    1430,
    "#ffffff",
    "#adb5bd",
    rough=1,
    stroke_width=2,
    fill_style="solid",
)
text(
    "title",
    90,
    55,
    2260,
    58,
    "ESP32-S3 书桌学习伴侣 · 实机系统架构",
    40,
    DARK,
    "center",
)
text(
    "subtitle",
    90,
    115,
    2260,
    32,
    "真实输入 → 边缘计算 → SDK / Agent / Tool → 数据与实际输出",
    21,
    GRAY,
    "center",
)

# Legend.
legend_y = 165
legend = [
    (530, TEAM_FILL, BLUE, "团队开发"),
    (830, EXT_FILL, PURPLE, "第三方 SDK / 模型"),
    (1190, INPUT_FILL, ORANGE, "真实输入"),
    (1450, OUTPUT_FILL, GREEN, "实际输出"),
    (1735, OPTIONAL_FILL, RED, "预留未启用"),
]
for index, (x, fill, stroke, name) in enumerate(legend):
    rect(
        "legend_%d" % index,
        x,
        legend_y,
        42,
        26,
        fill,
        stroke,
        stroke_width=2,
        dashed=index == 4,
    )
    text("legend_text_%d" % index, x + 55, legend_y - 1, 220, 28, name, 17)

# Section containers.
containers = [
    ("group_input", 60, 230, 310, 1160, CREAM, ORANGE, "① 真实输入"),
    ("group_esp", 410, 230, 590, 1160, "#e7f5ff", BLUE, "② ESP32-S3 边缘端"),
    ("group_lan", 1040, 230, 250, 1160, "#f8f0fc", PURPLE, "③ 数据通道"),
    (
        "group_ai",
        1330,
        230,
        660,
        1160,
        "#f8f0fc",
        PURPLE,
        "④ Mac + SDK / Agent / Tool",
    ),
    ("group_out", 2030, 230, 330, 1160, "#ebfbee", GREEN, "⑤ 实际输出"),
]
for element_id, x, y, width, height, fill, stroke, name in containers:
    rect(
        element_id,
        x,
        y,
        width,
        height,
        fill,
        stroke,
        stroke_width=2,
        opacity=52,
    )
    text(
        element_id + "_title",
        x + 18,
        y + 14,
        width - 36,
        35,
        name,
        23,
        stroke,
        "center",
    )

# Input nodes.
node(
    "input_presence",
    95,
    330,
    240,
    135,
    "儿童行为\n在座 · 移动 · 离开",
    INPUT_FILL,
    ORANGE,
    21,
    "ellipse",
)
node(
    "input_environment",
    95,
    540,
    240,
    135,
    "桌面环境\n光照 · 温度 · 湿度",
    INPUT_FILL,
    ORANGE,
    21,
    "ellipse",
)
node(
    "input_voice",
    95,
    750,
    240,
    155,
    "长按 IO10\n儿童真实语音",
    INPUT_FILL,
    ORANGE,
    22,
    "ellipse",
)
node(
    "input_repo",
    95,
    1110,
    240,
    135,
    "Git 提交\n代码 · 文档 · 素材",
    INPUT_FILL,
    ORANGE,
    21,
    "ellipse",
)

# ESP32 nodes.
node(
    "esp_sdk",
    455,
    315,
    225,
    120,
    "SDK / HAL\nGPIO · ADC · I²C\nSPI · I2S · Wi-Fi",
    EXT_FILL,
    PURPLE,
    18,
)
node(
    "esp_main",
    735,
    315,
    225,
    120,
    "main.py（团队）\n协作主循环\n看门狗 · 显示调度",
    TEAM_FILL,
    BLUE,
    18,
)
node(
    "esp_fusion",
    455,
    500,
    225,
    125,
    "Tool：传感器融合\nPIR + VL53L0X\nPRESENT / AWAY",
    TEAM_FILL,
    BLUE,
    18,
)
node(
    "esp_study",
    735,
    500,
    225,
    125,
    "Tool：学习系统\n计时 · 目标 · 成长\n体力 · 持久化",
    TEAM_FILL,
    BLUE,
    18,
)
node(
    "esp_audio",
    455,
    745,
    225,
    125,
    "Tool：AudioManager\n麦克风 RX\n扬声器 TX 仲裁",
    TEAM_FILL,
    BLUE,
    18,
)
node(
    "esp_voice",
    735,
    745,
    225,
    125,
    "Tool：VoiceQAClient\n录音 · Wi-Fi\n协议状态机",
    TEAM_FILL,
    BLUE,
    18,
)
node(
    "esp_reminder",
    455,
    955,
    225,
    125,
    "Tool：本地提醒\n喝水休息\n低光照 + 动画",
    TEAM_FILL,
    BLUE,
    18,
)
node(
    "esp_action",
    735,
    955,
    225,
    125,
    "Tool：设备动作\n白名单校验 · 去重\n写入每日目标",
    TEAM_FILL,
    BLUE,
    18,
)

# Network nodes.
node(
    "lan_discovery",
    1070,
    330,
    190,
    120,
    "UDP 8767\n服务发现\n北京时间",
    TEAM_FILL,
    BLUE,
    18,
)
node(
    "lan_voice",
    1070,
    690,
    190,
    155,
    "TCP 8766\nVQW1 / VA01\nWAV · JSON · PCM16\nDevice Token",
    TEAM_FILL,
    BLUE,
    17,
)
node(
    "lan_event",
    1070,
    1040,
    190,
    135,
    "TCP 8766\nEVT1 / EV01\n行为与传感器 JSON",
    TEAM_FILL,
    BLUE,
    17,
)

# Mac, SDK, Agent and Tool nodes.
node(
    "mac_server",
    1380,
    315,
    225,
    110,
    "Tool：Voice Server\n鉴权 · 并发 · 编排",
    TEAM_FILL,
    BLUE,
    18,
)
node(
    "mimo_asr",
    1710,
    315,
    225,
    110,
    "MiMo v2.5 ASR\nWAV → transcript",
    EXT_FILL,
    PURPLE,
    19,
)
node(
    "tool_router",
    1510,
    500,
    280,
    150,
    "Tool Router\n普通学习问题？\n还是设备设置？",
    TEAM_FILL,
    BLUE,
    20,
    "diamond",
)
node(
    "mimo_agent",
    1380,
    730,
    225,
    120,
    "MiMo v2.5 Pro Agent\n团队 Prompt\n结构化 answer JSON",
    EXT_FILL,
    PURPLE,
    18,
)
node(
    "mimo_tts",
    1710,
    730,
    225,
    120,
    "MiMo v2.5 TTS\n文本 → PCM24\n团队重采样 PCM16",
    EXT_FILL,
    PURPLE,
    18,
)
node(
    "command_tool",
    1510,
    930,
    280,
    120,
    "Tool：目标指令解析\nset_daily_goal_seconds\n5 分钟～24 小时",
    TEAM_FILL,
    BLUE,
    18,
)
node(
    "event_sink",
    1380,
    1120,
    225,
    120,
    "Tool：Event Sink\n本地 JSONL 优先\nPyMySQL + TLS",
    TEAM_FILL,
    BLUE,
    18,
)
node(
    "repo_sync",
    1710,
    1120,
    225,
    120,
    "Tool：Repository Sync\n源码快照\n素材 SHA-256 清单",
    TEAM_FILL,
    BLUE,
    18,
)

# Outputs.
node(
    "output_display",
    2075,
    320,
    245,
    150,
    "OLED + LCD\n北京时间 · 环境\n宠物 · 距离 · 时长\n成长值",
    OUTPUT_FILL,
    GREEN,
    19,
)
node(
    "output_speaker",
    2075,
    680,
    245,
    150,
    "I2S 扬声器\n本地提醒\nAI 回答\n设置确认",
    OUTPUT_FILL,
    GREEN,
    20,
)
node(
    "output_flash",
    2075,
    910,
    245,
    150,
    "ESP32 Flash\npet_state.json\npet_config.json\nstate.txt",
    OUTPUT_FILL,
    GREEN,
    18,
)
node(
    "output_tidb",
    2075,
    1090,
    245,
    110,
    "TiDB Cloud\n行为 · 问答\n代码快照 · 素材清单",
    OUTPUT_FILL,
    GREEN,
    18,
)
node(
    "output_github",
    2075,
    1215,
    245,
    75,
    "GitHub\n源码 · 文档 · 素材",
    OUTPUT_FILL,
    GREEN,
    18,
)
node(
    "output_stack",
    2075,
    1310,
    245,
    55,
    "TiDB Agent Stack：接口预留，当前未配置",
    OPTIONAL_FILL,
    RED,
    16,
    dashed=True,
)

# Sensing and local pipeline.
arrow("a_presence_sdk", "input_presence", "esp_sdk", ORANGE, 2.5)
arrow(
    "a_env_sdk",
    "input_environment",
    "esp_sdk",
    ORANGE,
    2.5,
    points=[[335, 608], [390, 608], [390, 405], [455, 405]],
)
arrow("a_sdk_main", "esp_sdk", "esp_main", BLUE, 2.5)
arrow(
    "a_main_fusion",
    "esp_main",
    "esp_fusion",
    BLUE,
    2.5,
    points=[[735, 390], [705, 390], [705, 560], [680, 560]],
)
arrow("a_fusion_study", "esp_fusion", "esp_study", BLUE, 2.5)
arrow(
    "a_study_display",
    "esp_study",
    "output_display",
    GREEN,
    2.5,
    points=[
        [960, 555],
        [1015, 555],
        [1015, 215],
        [2015, 215],
        [2015, 395],
        [2075, 395],
    ],
)
label("l_sensor", 365, 345, 100, "GPIO / I²C", ORANGE, 14)
label("l_state", 660, 535, 115, "融合状态", BLUE, 14)
label("l_ui", 1550, 198, 260, "板端实时显示（不依赖云端）", GREEN, 15)

# Voice path.
arrow("a_voice_audio", "input_voice", "esp_audio", PURPLE, 2.5)
arrow("a_audio_voice", "esp_audio", "esp_voice", BLUE, 2.5)
arrow("a_voice_lan", "esp_voice", "lan_voice", PURPLE, 2.5)
arrow(
    "a_lan_server",
    "lan_voice",
    "mac_server",
    PURPLE,
    2.5,
    points=[[1260, 765], [1300, 765], [1300, 370], [1380, 370]],
)
arrow("a_server_asr", "mac_server", "mimo_asr", PURPLE, 2.5)
arrow("a_asr_router", "mimo_asr", "tool_router", PURPLE, 2.5)
arrow("a_router_agent", "tool_router", "mimo_agent", PURPLE, 2.5)
arrow("a_agent_tts", "mimo_agent", "mimo_tts", PURPLE, 2.5)
arrow("a_tts_speaker", "mimo_tts", "output_speaker", GREEN, 2.5)
label("l_mic", 350, 770, 115, "I2S PCM", PURPLE, 14)
label("l_wav", 965, 715, 105, "WAV + JSON", PURPLE, 14)
label("l_asr", 1610, 342, 100, "HTTPS", PURPLE, 14)
label("l_question", 1340, 665, 155, "普通学习问题", PURPLE, 14)
label("l_answer", 1605, 762, 105, "answer JSON", PURPLE, 14)
label("l_pcm", 1935, 750, 140, "VA01 / PCM16", GREEN, 14)

# Voice command branch.
arrow("a_router_command", "tool_router", "command_tool", BLUE, 2.5)
arrow(
    "a_command_action",
    "command_tool",
    "esp_action",
    BLUE,
    2.5,
    points=[
        [1510, 990],
        [1310, 990],
        [1310, 900],
        [1015, 900],
        [1015, 1015],
        [960, 1015],
    ],
)
arrow(
    "a_action_flash",
    "esp_action",
    "output_flash",
    GREEN,
    2.5,
    points=[
        [960, 1015],
        [1018, 1015],
        [1018, 895],
        [2015, 895],
        [2015, 985],
        [2075, 985],
    ],
)
label("l_command", 1500, 870, 300, "“把每日目标改为两小时”", BLUE, 15)
label("l_action", 1100, 865, 190, "device_action JSON", BLUE, 14)
label("l_config", 1640, 867, 250, "校验后写入 Flash", GREEN, 14)

# Local reminder to speaker.
arrow(
    "a_main_reminder",
    "esp_main",
    "esp_reminder",
    BLUE,
    2.5,
    points=[[850, 435], [850, 670], [710, 670], [710, 1015], [680, 1015]],
)
arrow(
    "a_reminder_speaker",
    "esp_reminder",
    "output_speaker",
    GREEN,
    2.5,
    points=[[680, 1015], [700, 1015], [700, 660], [2015, 660], [2015, 755], [2075, 755]],
)
label("l_local_audio", 1460, 632, 230, "本地 PCM + LCD 动画", GREEN, 15)

# Discovery and telemetry/storage.
arrow(
    "a_voice_discovery",
    "esp_voice",
    "lan_discovery",
    BLUE,
    2,
    points=[[960, 790], [1020, 790], [1020, 390], [1070, 390]],
)
arrow("a_discovery_server", "lan_discovery", "mac_server", BLUE, 2)
arrow(
    "a_main_event",
    "esp_main",
    "lan_event",
    GREEN,
    2.5,
    points=[[850, 435], [1005, 435], [1005, 1105], [1070, 1105]],
)
arrow("a_event_sink", "lan_event", "event_sink", GREEN, 2.5)
arrow(
    "a_server_sink",
    "mac_server",
    "event_sink",
    GREEN,
    2,
    points=[[1490, 425], [1490, 1080], [1490, 1120]],
)
arrow(
    "a_sink_tidb",
    "event_sink",
    "output_tidb",
    GREEN,
    2.5,
    points=[[1605, 1180], [1645, 1180], [1645, 1065], [2000, 1065], [2000, 1145], [2075, 1145]],
)
arrow(
    "a_sink_stack",
    "event_sink",
    "output_stack",
    RED,
    2,
    dashed=True,
    points=[[1492, 1240], [1492, 1375], [1995, 1375], [1995, 1337], [2075, 1337]],
)
label("l_discovery", 995, 455, 160, "发现 / 北京时间", BLUE, 14)
label("l_telemetry", 1000, 1115, 135, "telemetry", GREEN, 14)
label("l_tls", 1880, 1160, 150, "PyMySQL + TLS", GREEN, 14)
label("l_optional", 1750, 1342, 180, "可选 HTTP", RED, 14)

# Repository synchronization.
arrow(
    "a_repo_sync",
    "input_repo",
    "repo_sync",
    BLUE,
    2.5,
    points=[[335, 1175], [400, 1175], [400, 1270], [1660, 1270], [1660, 1180], [1710, 1180]],
)
arrow("a_sync_tidb", "repo_sync", "output_tidb", GREEN, 2.5)
arrow(
    "a_sync_github",
    "repo_sync",
    "output_github",
    GREEN,
    2.5,
    points=[[1935, 1180], [2005, 1180], [2005, 1252], [2075, 1252]],
)
label("l_repo", 880, 1240, 300, "Git 历史 + SHA-256 清单", BLUE, 15)
label("l_github", 1940, 1220, 125, "git push", GREEN, 14)

# Ownership note.
text(
    "ownership_note",
    120,
    1402,
    2180,
    30,
    "团队开发：ESP32 固件、融合/成长/提醒算法、网络协议、Mac 编排、Prompt、Tool、TiDB 数据模型与部署测试。第三方：硬件、MicroPython、MiMo 模型、TiDB Cloud、GitHub。",
    17,
    DARK,
    "center",
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
