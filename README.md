# 书桌学习伴侣（ESP32-S3 × MiMo × TiDB）

面向儿童护眼、专注管理和学习问答的软硬件单仓库。当前开发板固件、Mac语音
服务、家长端原型、部署工具、素材生成器、测试和历史源码均已集中到本仓库。

## 仓库结构

```text
firmware/                 ESP32-S3 MicroPython生产固件
  main.py                 自动启动主程序（板上路径 /main.py）
  audio_manager.py        统一I2S麦克风/扬声器管理
  voice_qa_client.py      Wi-Fi语音问答协作式状态机
  diagnostics/            独立硬件诊断与板上历史脚本
  tests/                  纯Python算法测试
  assets/                 PCM提示音、宠物和LCD动画素材
services/voice_ai/        Mac端MiMo ASR/Agent/流式TTS服务
apps/parent_dashboard/    家长端静态Web原型
apps/landing/             产品落地页（动效，纯静态）
tooling/                  部署、raw REPL、录音和素材构建工具
docs/                     架构、引脚、板上源码审计
 archive/                 历史迭代源码与回滚快照
 runtime/                 本地运行数据（Git忽略）
```

## 已实现功能

- PIR + VL53L0X融合判断PRESENT/AWAY和连续学习时间。
- LCD显示宠物、学习状态、单次时长、距离和环境质量。
- OLED显示自动校准的北京时间、光照、温度和湿度。
- 连续学习30秒播放休息喝水语音和动画。
- 低光照提醒半小时最多一次，并播放对应动画。
- IO10长按录音、松开后完成MiMo识别、Agent答题和流式语音回答。
- Wi-Fi自动重连、认证UDP发现、Device Token校验和Mac时间同步。
- 学习状态、传感器心跳、提醒和问答先写本地队列，再通过TLS写入TiDB Cloud。
- 当前Git提交的全部文本源码和二进制素材清单可幂等同步到TiDB。

## 环境准备

```bash
cd /path/to/desk-study-companion
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp services/voice_ai/.env.example services/voice_ai/.env
chmod 600 services/voice_ai/.env
```

填写 `.env` 后生成板端私密配置：

```bash
make PYTHON=.venv/bin/python config
```

`.env`、生成的板端配置、录音、回答和事件数据全部被Git忽略。

## 常用命令

```bash
make PYTHON=.venv/bin/python test       # 固件算法 + 语音服务测试
make PYTHON=.venv/bin/python compile    # Python编译检查
make PYTHON=.venv/bin/python deploy     # 烧写/更新开发板文件
make PYTHON=.venv/bin/python audit      # 重读板上源码并检查一致性
make PYTHON=.venv/bin/python server     # 启动Mac语音服务
make PYTHON=.venv/bin/python dashboard  # 家长端 http://127.0.0.1:4173
make PYTHON=.venv/bin/python landing    # 落地页 http://127.0.0.1:4174
make PYTHON=.venv/bin/python tidb-schema # 初始化TiDB数据表
make PYTHON=.venv/bin/python tidb-sync   # 同步源码快照和素材清单
```

本机现有环境也可直接使用上级目录的虚拟环境：

```bash
make PYTHON=../.venv/bin/python test
```

## 硬件关键引脚

| 功能 | 引脚 |
| --- | --- |
| OLED | SDA IO4 / SCL IO5 |
| LCD | SCK IO21 / MOSI IO47 / DC IO43 / CS IO44 |
| PIR | IO16 |
| VL53L0X | SDA IO17 / SCL IO18 |
| 光敏 | ADC IO6 / IO7 |
| DHT11 | IO15 |
| IO10按钮 / LED2 | IO10 / IO9 |
| 麦克风 | IO41 / IO42 / IO2 |
| 扬声器 | IO38 / IO39 / IO40 |

完整说明见 `docs/hardware/pinout.md`。

TiDB Cloud连接、表结构和行为上报说明见 `docs/tidb-cloud.md`。

## 开发板源码一致性

2026-08-28已通过raw REPL读取开发板全部Python文件。生产主程序、驱动、融合
算法、音频管理和Wi-Fi客户端均与 `firmware/` 中的规范源码逐字节一致。板上
独有诊断脚本已归档，私密配置仅保存尺寸与CRC，不进入Git。详见：

- `docs/hardware/board-audit.md`
- `docs/hardware/board-python-manifest.json`

## 运行边界

拔掉USB数据线后，固件、显示、传感器、学习计时和本地提醒仍由 `/main.py`
自动运行。AI问答还需要ESP32与Mac处于同一Wi-Fi，并保持
`services/voice_ai/local_fast_voice_server.py`运行。
