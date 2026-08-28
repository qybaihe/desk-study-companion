# ESP32-S3 硬件与引脚

## 主控

- ESP32-S3 QFN56 rev v0.2
- 8 MB Octal PSRAM
- 16 MB Flash
- CH340 UART，稳定速率 115200/230400
- MicroPython `ESP32_GENERIC_S3-SPIRAM_OCT`

## 当前功能分配

| 部件 | 引脚/总线 | 用途 |
| --- | --- | --- |
| OLED SSD1306 | SDA IO4，SCL IO5，地址 0x3C | 北京时间、光照、温湿度 |
| LCD ST7789 | SCK IO21，MOSI IO47，DC IO43，CS IO44 | 宠物、在座状态、学习时长、距离 |
| PIR | IO16 | 人体运动事件 |
| VL53L0X | SDA IO17，SCL IO18，地址 0x29 | 桌前距离/在座保持 |
| 光敏1/2 | ADC IO6 / IO7 | 环境光照 |
| DHT11 | IO15 | 温度、湿度 |
| 下拉按钮1 | IO10 | 长按录音、松开提问 |
| LED2 | IO9 | 镜像IO10按键状态 |
| 麦克风 I2S RX | SCK IO41，WS IO42，SD IO2 | 16 kHz、32 bit采集 |
| 扬声器 I2S TX | DIN IO38，BCK IO39，LRCK IO40 | 提醒和24 kHz AI回答 |
| 板载RGB | IO48 | WS2812 |

## 重要约束

- 麦克风与扬声器共用 I2S0，由 `firmware/audio_manager.py` 独占管理。
- IO43/IO44同时是UART0引脚；主程序启动前保留3秒串口恢复窗口。
- IO35/36/37与八线PSRAM冲突，不作为普通外设引脚使用。
- VL53L0X 的8190/8191表示超量程，并非真实距离。
- 底板电源开关处于OFF时，未供电I2C模块可能经ESD二极管拉低总线。
