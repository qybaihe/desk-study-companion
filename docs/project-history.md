# 项目行为与交付历史

本文档保留可复现的工程行为；实时学习行为由 `project_event` 表记录。

## 2026-08-27：硬件打通

- 备份原厂Flash，识别ESP32-S3、8 MB Octal PSRAM和16 MB Flash。
- 将主控固件切换为MicroPython，实测可用RAM约8.31 MB。
- 验证CH340 UART在115200/230400稳定，固化raw REPL工具链。
- 验证SSD1306 OLED、PIR、双路光敏和ST7789 LCD基础驱动。
- 识别光敏模块在常态光照下输出约2.98 V，确认属于模拟前端饱和。
- 确认VL53L0X地址 `0x29`，使用IO17/IO18独立SoftI2C。
- 实现PIR + VL53L0X融合状态机，将原始MOTION/CLEAR映射为稳定
  PRESENT/AWAY。
- 实现北京时间、环境、学习时长和距离显示。
- 实现休息喝水提醒、低光提醒、扬声器PCM播放和宠物动画。

## 2026-08-28：语音AI与联网

- IO10长按录音，松开后生成16 kHz/16-bit/单声道WAV。
- 打通ESP32 → Wi-Fi → Mac → MiMo ASR/Agent/TTS → ESP32扬声器链路。
- 实测10次真实开发板局域网问答，首段语音4.4–15.3秒。
- 增加Device Token、UDP自动发现、Wi-Fi重连和北京RTC同步。
- 将TTS从24 kHz流式降采样为16 kHz，板端增加2秒预缓冲，降低卡顿。
- 读取开发板全部16个Python文件，归档非私密源码并校验CRC32。
- 建立统一monorepo，整合固件、Mac服务、家长端、测试、素材、部署工具和历史快照。
- 将完整项目推送至 `qybaihe/desk-study-companion`。
- 增加TiDB Cloud行为事件、源码快照和素材清单数据模型，板端每分钟
  上报传感器心跳与关键状态转换。

## 保密与可复现性

- Wi-Fi密码、MiMo API Key、Device Token和TiDB数据库密码只存在Git忽略的
  `.env`/生成配置中。
- GitHub保存代码与素材原件；TiDB保存行为、文本源码快照和二进制素材哈希。
- `make test` 、`make compile`、`make deploy`、`make audit` 形成本地闭环，
  GitHub Actions在每次推送时重复编译和测试。
