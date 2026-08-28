# 系统架构

```text
PIR + VL53L0X + 光敏 + DHT11
             │
             ▼
       ESP32-S3 main.py
       ├─ OLED 环境信息
       ├─ LCD 宠物/在座/距离/学习时长
       ├─ 本地喝水与低光提醒
       └─ IO10语音状态机
             │  VQW1/TCP + Device Token
             ▼
       Mac voice_ai service
       ├─ MiMo ASR
       ├─ MiMo Agent
       ├─ MiMo流式TTS
       └─ 学习事件JSONL / TiDB Agent Stack HTTP接口
             │  VA01 + PCM16流
             ▼
       ESP32-S3 I2S扬声器
```

## 固件状态机

```text
IDLE → RECORDING → PROCESSING → UPLOADING
     → THINKING → PLAYING → IDLE
```

`AudioManager`在本地提醒、麦克风RX和扬声器TX之间仲裁I2S0。录音期间优先消费
64 ms DMA块；其他语音阶段仍以10 Hz更新显示和传感器。

## 在座融合

- PIR提供进入/离开动作事件。
- VL53L0X提供稳定距离和静坐保持。
- 进入距离与离开距离使用滞回。
- 最终只向显示/App输出PRESENT或AWAY。
- 学习会话从AWAY→PRESENT开始，在PRESENT→AWAY时保存。
