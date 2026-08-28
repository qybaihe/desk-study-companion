# Mac局域网语音服务

## 链路

```text
ESP32 WAV → TCP 8766 → MiMo ASR → 单次Agent → 流式TTS → PCM16回传
```

UDP 8767负责带Device Token的Mac地址发现，并向断电重启后的开发板下发北京
RTC时间。TCP请求同样校验Token。

## 配置

```bash
cp .env.example .env
chmod 600 .env
python build_device_voice_config.py
```

生成的 `generated/voice_qa_config.py` 由部署工具上传成板上的
`/voice_qa_config.py`，不会进入Git。

## 启动

从仓库根目录执行：

```bash
make PYTHON=.venv/bin/python server
```

## 协议

```text
ESP32 → VQW1 + JSON长度 + JSON + WAV
Mac   → VA01 + JSON长度 + 答案JSON
Mac   → 多个PCM长度 + PCM16数据
Mac   → 长度0
ESP32 → EVT1 + JSON长度 + 带Token的行为/传感器JSON
Mac   → EV01 + JSON长度 + 持久化结果
```

回答最多100个汉字、两句话。完成事件始终落入忽略目录
`event_spool/learning_events.jsonl`；配置 `TIDB_HOST` 等参数后直接写入
TiDB Cloud，配置 `TIDB_AGENT_STACK_URL` 后还会同时HTTP投递。

## 测试

```bash
PYTHONPATH=services/voice_ai python3 services/voice_ai/test_fast_voice_server.py
```

测试不调用MiMo API，覆盖回答裁剪、错误Token拒绝、认证发现和事件本地回退。
