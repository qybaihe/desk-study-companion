# 交接提示词 — TiDB AI Hardware Hackathon / ESP32-S3 书桌学习伴侣

> 把这整份内容贴给新会话即可接手。所有结论都标注了是「实测验证过」还是「未验证」。

## 0. 你接手的是什么

一块 ESP32-S3 传感器套件板，目标产品是**书桌学习伴侣（儿童护眼 + 专注力管理）**，参加 TiDB AI Hardware Hackathon。
评分 = 创新性 10 + 向善价值 10 + 落地完成度 10。

硬件侧已打通到「能读传感器、能驱动 OLED、能远程注入 Python 代码执行」。
**TiDB Agent Stack 的接入完全没开始，那是最大的未知数和交付硬要求。**

---

## 1. 硬件事实（全部实测）

**芯片**：ESP32-S3 (QFN56) rev v0.2，8MB Octal PSRAM，16MB Flash，MAC `28:84:85:27:48:9c`
**板型**：丝印 `ESP32 S3 AIoT`，一整块拼板：中间是 ESP32-S3 核心板 + 排针底板，四周是可掰开的传感器模块

**两个 USB-C 口**：
- `UART` 口 → CH340（VID `0x1A86` / PID `0x7523`）→ `/dev/cu.usbserial-*`。**目前唯一可用的通道**
- `USB` 口 → 原生 USB（IO19/IO20）。**实测从未枚举成功**，且只插这个口时板子不亮（线可能是只充电的）

**串口速率**：115200 和 230400 稳定；**460800 会丢字节**（`Corrupt data` / `Invalid head of packet`），921600 直接失败。烧录和大块读写一律用 230400 或更低。

**电源开关**：底板左上角有 `ON/OFF` 拨动开关。拨到 OFF 时模块断电，未供电的 I²C 器件会通过 ESD 二极管把 SDA 拽低，**表现为「引脚短路到地」，极具误导性**。排查任何异常前先确认它在 ON。

---

## 2. 固件状态

**原厂固件已完整备份**（可随时还原）：
- 文件：`flash_backup_4MB.bin`，4194304 字节，md5 `897076ff722fb75c4fac212bc2cb0294`
- 覆盖 `0x0`–`0x400000`。分区表只跨 4MB（app0/app1/spiffs 的 Arduino OTA 布局），后 12MB 是空的，所以 4MB 就是完整备份
- 原固件身份：`arduino-esp32` 编译的普通 sketch，无任何 Deotaland/ROROLEE/agent 字样，是出厂测试程序
- 还原命令：`esptool --port <PORT> --baud 230400 write_flash 0 flash_backup_4MB.bin`

**当前固件**：MicroPython v1.29.0（`ESP32_GENERIC_S3-SPIRAM_OCT`，2026-08-24），烧在 `0x0`
- 启动横幅实测：`MicroPython v1.29.0 on 2026-08-24; Generic ESP32S3 module with Octal-SPIRAM`
- 可用 RAM 实测 8.31 MB（PSRAM 正常）

---

## 3. 上位机工具链

位置：`/private/tmp/claude-501/-Users-bytedance-Documents-TIDB/8a8266f9-893f-4828-b980-db6868c8482d/scratchpad/`

| 文件 | 说明 |
|---|---|
| `venv/` | 装了 esptool 4.12.0、pyserial、Pillow |
| `mprepl.py` | **核心工具**。纯标准库写的 MicroPython raw REPL 驱动，自动探测串口，已修 EAGAIN 写阻塞。用法：`mprepl.run(code) -> (stdout, stderr)` |
| `main_board.py` | 板上 `/main.py` 的源码（OLED 实时显示） |
| `st7789.py` | ST7789 LCD 驱动，**已写完但从未测试过** |
| `sniff.py` | 复位板子并抓串口输出 |
| `flash_backup_4MB.bin` | 原厂固件备份 |
| `HANDOFF.md` | 本文件 |

**两个坑**：
1. **串口名字会变**。用户换 Mac 上的物理 USB 口后从 `usbserial-110` 变成 `usbserial-210`。`mprepl.py` 已做自动探测，别再写死路径。
2. **每次连板子都会打断 `main.py`**。`mprepl` 进 raw REPL 必须发 Ctrl-C，这会杀掉主循环，OLED 随之冻结。读到的 `/state.txt` 是冻结快照不是实时值。要恢复显示必须复位：`mprepl.Port().reset()`。

---

## 4. 引脚地图（从丝印实读）

底板排针是**三列结构**：`G`（黑）/ `3V3`（红）/ `S`（黄，信号），行按 GPIO 标号。
- 上排：IO14, 13, 12, 11, 10, 9, 46, 3, 8, 18, 17, 16, 15, 7, 6, 5, 4, RST, 3V3
- 下排：IO19, 20, 21, 47, 48, 45, 0, 35, 36, 37, 38, 39, 40, 41, 42, 2, 1, 44, 43

**JST 座规则**：3 针座 = `G V <单个GPIO>`；4 针座 = `V G <GPIO> <GPIO>`

**厂商在丝印上定死的功能分配**：

| 外设 | 引脚 |
|---|---|
| LCD (ST7789) | IO21=SCL, IO47=SDA, **IO44=CS, IO43=DC** |
| 板载 RGB LED (WS2812) | IO48 |
| 扬声器 I²S | IO38=DIN, IO39=BCK, IO40=LRCK |
| 麦克风 I²S | IO41=SCK, IO42=WS, IO2=SD |
| SD 卡 | IO3=CLK, IO14=MOSI, IO35=MISO, IO46=CS |
| I²C 总线 | IO4=SDA, IO5=SCL（丝印写作 CAM-SDA/CAM-SCL） |
| 保留 | IO19/20=USB, IO0=BOOT, IO35/36/37 也被八线 PSRAM 占用 |

---

## 5. 已接线 + 验证状态

| 模块 | 引脚 | 状态 |
|---|---|---|
| OLED SSD1306 128×64 @ `0x3C` | SDA=IO4, SCL=IO5 | ✅ **实测工作**，能显示文字图形 |
| PIR 人体红外 | IO16 | ✅ **实测工作**，有人动输出 1，静止后衰减回 0 |
| 光敏 1 | IO6 (ADC1) | ⚠️ 接通但**饱和**，见第 6 节 |
| 光敏 2 | IO7 (ADC1) | ⚠️ 接通但**饱和**，见第 6 节 |
| 音频功放+扬声器 | IO38/39/40 | ❓ 用户称已接，**我从未测试** |
| 1.3" IPS LCD | IO21/47/43/44 | ❌ **被硬件冲突阻塞**，见第 7 节 |
| 数字麦克风 | — | ❌ 未接。模块**只有排针孔没有 JST 座**，用户的线（一头 JST 一头杜邦）插不上 |
| VL53L0X 激光测距 | — | ❌ 未接。**这是方案二最关键的传感器，优先接它** |

板上 `/main.py` 当前功能：OLED 实时显示两路光敏值 + 最小/最大值 + PIR 状态，并把状态写到 `/state.txt`。开机有 3 秒宽限窗口（`time.sleep(3)`），期间 Ctrl-C 可掉回 REPL。

---

## 6. 光敏饱和问题（未解决，需物理处理）

**实测数据**，同一路在不同 ADC 量程下：

| 量程 | 读数 | 换算 |
|---|---|---|
| 0–1.1V | 4095 顶格 | — |
| 0–1.5V | 4095 顶格 | — |
| 0–2.2V | 4095 顶格 | — |
| **0–3.1V** | **3935**（未顶格） | **2.98 V** |

**关键结论：ADC 没有削顶**（最宽量程下是 3935 而非 4095），是传感器输出本身就在 2.98V。常态光照吃掉约 90% 摆幅，往上只剩约 160 个 ADC 计数。

**软件无法修复**。把 3935 映射成 2000 只是换标签，强光下也只能涨到相当于 2080，压缩发生在模拟域。

**待办**：给两路光敏各贴同样厚度的减光片（纸/胶带），盯 OLED 把常态读数调到 2000 左右。需要约 50% 透光率。**两路必须一致**，否则差分失去可比性。

**遮挡测试始终没做**。这是判断传感器是模拟输出还是数字比较器输出的唯一方法——如果捂住时数值平滑下降就是模拟量（方案可行），如果直接跳到 0 就是数字输出（光照差分方案要重新设计）。

---

## 7. LCD 死结（最重要的未解决问题）

**问题**：LCD 硬连在 IO43(DC)/IO44(CS)，而这两个脚就是 UART0 的 TX/RX，是目前唯一的控制通道。主办方确认 LCD 已固定连接，不能改线。

两重后果：
1. 驱动 LCD 就失去串口控制台，而且爬不回来
2. IO44 上 CH340 的 TX 输出和 ESP32 的 GPIO 输出会**推挽对顶**，估算对冲电流 20–40mA

**已排除的路**：这版 MicroPython **不提供原生 USB 控制台**。实测证据：`IO19`/`IO20` 能当普通 GPIO 用并读到电平（19=0, 20=1），说明 USB 外设没被初始化；`machine.USBDevice` 存在但 `usb` / `usb.device` 模块缺失。

**两条候选路**：
- **甲**：找/编译一个把控制台放在 USB-Serial-JTAG 上的固件。**这条路的调研做到一半被中止，没有结论。** 需要查 micropython.org 各 ESP32-S3 board variant 的 `sdkconfig.board` 里有没有 `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG`，注意必须兼容 Octal PSRAM + 16MB flash。
- **乙**：开机宽限窗口 + 用非 UART 方式供电。`main.py` 开机先 `time.sleep(N)` 不碰 IO43/44，这期间串口正常可 Ctrl-C 打断；N 秒后才接管 LCD。演示时拔掉 UART 线用充电宝供电，就没有对顶。**卡在用户那根 USB-C 线可能是只充电不传数据的，甚至供电也没成功。**

**未验证的前提**：用户那根 USB-C 线插充电头板子会不会亮，一直没确认。这是走乙方案的前置条件。

---

## 8. 踩过的坑（避免重复）

1. **另一个 Claude Code 会话在并发抢同一个串口**。现象是 `Resource temporarily unavailable`。用 `lsof /dev/cu.*` 能看到占用进程。串口是独占设备，多会话必冲突。
2. **两根杜邦线插错，把 IO2 和 IO4 短到地**。诊断方法：遍历所有 GPIO 开内部上拉后读值，仍为 0 的就是被拉死。这个方法非常有效，值得复用。
3. **I²C 扫描返回全部 112 个地址 = SDA 被拉死，不是接了 112 个设备**。SDA 恒低时 ACK 判定永远成立。真设备只应答 1–2 个地址。过滤规则：`len(found) > 8` 直接判定总线故障。
4. **ADB 完全不适用**，ESP32 不是 Android 设备。走串口。
5. **模块引脚数不要从照片数**，反光会导致误判（我把麦克风数成 6 针，实际用户说是 7 针）。以实物为准。

---

## 9. 产品方案（已定）

**方案二：书桌学习伴侣（儿童护眼 + 专注力）**
一句话：放在书桌上，知道孩子什么时候在学、光线够不够、坐了多久，该休息时提醒，每天给家长一份报告。

**传感器分工（已根据实测修正）**：
- **VL53L0X = 真正的在座检测 + 用眼距离**。低头凑太近是最强的近视风险信号。**优先接这个。**
- **PIR = 粗粒度进出房间事件**。⚠️ **重要修正：PIR 检测的是热源移动，不是在不在。孩子安静看书不动，保持时间到期后会翻回 0，被误判成「离座」。**绝不能拿 PIR 当在座检测。
- **双光敏差分** = 台灯够不够亮 / 是否背光 / 是否只开台灯没开顶灯。**这个设计不需要绝对 lux 标定，靠比值和差值就成立**，是它能落地的原因。
- 麦克风 = 环境噪音；DHT11 = 温湿度舒适度；IMU = 抖腿等分心信号
- OLED/LCD/蜂鸣器/LED = 番茄钟与提醒

**合规红线**：没有校准就**不能声称在测 lux**。国标读写作业面要求 ≥300 lux（推荐 500），要报绝对值必须拿照度计做两点校准。

---

## 10. 下一步优先级

1. **接 VL53L0X 到 I²C 总线**（IO4/IO5，地址 `0x29`）——方案二的核心传感器，目前完全缺失。它和 OLED 可以共用总线，地址不冲突。
2. **光敏贴减光片调到 2000**，并完成遮挡测试定性。
3. **TiDB Agent Stack 接入**——**完全没开始，交付硬要求，最大风险**。需要打通：Workspace API Key → User API Key → 查 Project/Agent → 建 Session → `POST /api/sessions/{id}/turns` 流式收 NDJSON。资料在 `https://tidb-agent-stack-intro-avsk9wk.gamma.site/`、`https://github.com/mem9-ai/agent-stack-dev-guide`、`https://github.com/DeotalandDev/Agent_link`。
4. **定死三个 Skill 的名字和职责**，交付物要交「Agent Stack 使用说明」，架构图会顺着 Skill 边界长出来。建议：`作息基线更新` / `用眼风险研判` / `家长日报周报`。
5. LCD 二选一（甲/乙）。**注意：这不是及格线**。OLED 已经能显示在座状态、光照、番茄钟，方案二不会因为 LCD 卡住。
6. 麦克风接口问题（无 JST 座）。

---

## 11. 快速验证片段

```python
import sys; sys.path.insert(0, '/private/tmp/claude-501/-Users-bytedance-Documents-TIDB/8a8266f9-893f-4828-b980-db6868c8482d/scratchpad')
import mprepl
out, err = mprepl.run('''
from machine import Pin, SoftI2C, ADC
i2c = SoftI2C(scl=Pin(5), sda=Pin(4), freq=400000)
f = i2c.scan()
print("I2C:", [hex(a) for a in f] if len(f) <= 8 else "STUCK(%d) = SDA拉死" % len(f))
for p in (6, 7):
    a = ADC(Pin(p)); a.atten(ADC.ATTN_11DB)
    print("IO%d light:" % p, sum(a.read_u16() >> 4 for _ in range(8)) // 8)
print("PIR:", Pin(16, Pin.IN).value())
''')
print(out, err)
```

全引脚短路检测：

```python
mprepl.run('''
from machine import Pin
import time
stuck = []
for p in [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,21,38,39,40,41,42,45,46,47,48]:
    u = Pin(p, Pin.IN, Pin.PULL_UP); time.sleep_ms(3)
    if sum(u.value() for _ in range(5)) < 4: stuck.append(p)
print("被拉死:", stuck if stuck else "无")
''')
```
