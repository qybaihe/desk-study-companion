# 开发板源码读取审计

审计日期：2026-08-28

通过CH340 raw REPL读取了开发板根目录中的全部Python文件，并对每个文件计算
长度与CRC32。私密的 `/voice_qa_config.py` 只记录元数据，没有把Wi-Fi密码或设备
Token写入仓库。

## 结论

开发板上除私密配置外的全部15个Python文件都已归档并与本仓库
逐字节一致。其中当前生产文件包括：

- `/main.py` → `firmware/main.py`
- `/audio_manager.py`
- `/fusion_tracker.py`
- `/pet_animation.py`
- `/pet_growth.py`
- `/presence_tracker.py`
- `/speaker_prompt.py`
- `/st7789.py`
- `/study_reminder.py`
- `/vl53l0x.py`
- `/voice_qa_client.py`
- `/mic_capture_io10.py`

板上历史/诊断源码已归档：

- `/boot.py` → `firmware/boot.py`
- `/voice_qa_mic_once.py` → `firmware/diagnostics/voice_qa_mic_once.py`
- 板上旧版 `/mic_button_test.py` → `firmware/diagnostics/deployed/mic_button_test.py`

本地较新的 `mic_button_test.py` 保留在 `firmware/diagnostics/`。完整尺寸与CRC位于
`board-python-manifest.json`。
