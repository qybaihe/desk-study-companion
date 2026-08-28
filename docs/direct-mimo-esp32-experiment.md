# ESP32 直连 MiMo 实验分支

本分支保存 ESP32-S3 直接通过 HTTPS 调用 MiMo ASR、Agent 与流式 TTS 的实验实现，
用于评估移除 Mac 局域网语音服务后的延迟、稳定性和内存占用。

## 分支状态

- 已完成：MicroPython 非阻塞 HTTPS 请求、WAV Base64 流式请求体、JSON 响应解析、
  SSE 音频解码、24 kHz PCM 播放、TLS CA 证书部署与配置生成。
- 已通过：仓库离线测试、Python 语法编译和密钥泄漏扫描。
- 尚未完成：真实开发板端到端验证、设备指令 Tool Router、TiDB 遥测链路恢复。
- 默认稳定方案仍在 `main`：ESP32 → 局域网 Mac 服务 → MiMo → ESP32。

## 安全边界

`services/voice_ai/generated/voice_qa_config.py` 仍被 Git 忽略。构建工具会从本机
`.env` 读取 MiMo API Key 并生成板端配置；仓库只包含占位符和公开 CA 证书。
在正式硬件版本中，长期 API Key 不应直接固化到可接触的设备，应改用短期凭证或
受控网关签发令牌。

## 当前已知差异

直连模式不经过 Mac 服务，因此当前版本暂停 `EVT1/EV01` 遥测，也未执行
`set_daily_goal_seconds` 设备动作。它保留为独立实验分支，避免替换主分支中已经
实机验证的学习目标、TiDB 事件和局域网问答闭环。
