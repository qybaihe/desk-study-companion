# TiDB Cloud 数据接入

本项目把GitHub作为完整代码与二进制素材的版本库，把TiDB Cloud作为设备行为、
学习会话、问答记录、代码快照和素材清单的数据层。

## 表结构

迁移文件：`services/voice_ai/migrations/001_project_observability.sql`

| 表 | 内容 |
| --- | --- |
| `project_event` | 在座切换、PIR动作、每分钟心跳、提醒、语音问答和仓库同步事件 |
| `project_code_snapshot` | 每次Git提交对应的全部文本源码、配置样例和文档 |
| `project_asset_manifest` | 宠物图片、RGB565动画、PCM语音等二进制素材的SHA-256与GitHub链接 |

## 配置

在TiDB Cloud Starter实例的 **Connect** 对话框选择PyMySQL，生成数据库密码，
然后把连接参数写入被Git忽略的 `services/voice_ai/.env`：

```dotenv
TIDB_HOST=HOST
TIDB_PORT=4000
TIDB_USER=USERNAME
TIDB_PASSWORD=PASSWORD
TIDB_DATABASE=desk_companion
TIDB_SSL_CA=/etc/ssl/cert.pem
```

Starter公共端点强制TLS。macOS系统根证书路径为 `/etc/ssl/cert.pem`。

## 初始化与同步

```bash
make PYTHON=.venv/bin/python tidb-schema
make PYTHON=.venv/bin/python tidb-sync
```

`tidb-sync`读取当前提交的全部Git跟踪文件：文本源码完整写入
`project_code_snapshot`，二进制素材写入不可变哈希、尺寸、MIME类型和GitHub固定
提交链接。重复执行通过主键幂等更新。

## 板端行为链路

ESP32在以下时刻发送带Device Token的 `EVT1` 事件：

- 开机首个传感器快照；
- `AWAY -> PRESENT` 与 `PRESENT -> AWAY`；
- 学习会话开始；
- PIR新动作；
- 休息喝水提醒与低光提醒；
- 每60秒完整传感器心跳。

Mac服务始终先追加到本地JSONL队列，再写TiDB；网络或TiDB暂时不可用时，本地
记录仍保留。语音问答完成后也写入同一事件表。
