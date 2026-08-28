# Banxue API · HTTP 中转层

一个后端服务两端，设备和 App 互不知道对方存在：

```
ESP32   ──POST /ingest───▶  写 TiDB，响应回带配置
iOS App ──GET  /api/*───▶  读 TiDB
```

**数据库凭据只存在这里。** ESP32 和 iOS 都不直连 TiDB —— MicroPython 没有 MySQL 驱动，
iOS 也没有，更重要的是把凭据放在客户端是安全事故。

## 运行

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

不配 TiDB 环境变量时自动返回演示数据（`mockdata.py`），端点结构完全一致，
所以 App 侧从 Mock 切到真实后端不需要改任何代码。

接库：

```bash
export TIDB_HOST=gateway01.<区域>.prod.aws.tidbcloud.com
export TIDB_PORT=4000
export TIDB_USER=xxxxx.root
export TIDB_PASSWORD=xxxxx
export TIDB_DATABASE=study_buddy
export TIDB_SSL_CA=/etc/ssl/cert.pem      # TLS 必须开
```

启动时自动执行 `schema.sql`（`AUTO_MIGRATE=0` 可关掉）。

## 端点

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/ingest` | 设备批量上报；响应带 `config` |
| GET | `/config` | 单独取配置 |
| GET | `/api/snapshot` | 此刻 |
| GET | `/api/eye` | 护眼 |
| GET | `/api/study` | 学习 |
| GET | `/api/diary` | 小羊日记 |
| GET | `/api/milestones` | 成长里程碑 |
| GET | `/api/weekly` | 周报 |
| GET | `/api/reminders` | 提醒与响应 |
| GET | `/api/settings` | 设置 |
| GET | `/health` | 健康检查，含 `db` 是否已接 |

## 三个设计决定

**批量上报，不要每秒一次 HTTP。** 攒 30–60 秒一批。ESP32 的 TLS 握手开销
远大于传输本身，减少连接次数比压缩数据重要得多。

**配置下行走上报响应。** 设备比对 `config.rev`，变了就落盘生效。
零额外连接、零额外协议，配置变更在一个上报周期内到位，比上 MQTT 简单一个数量级。

**云端只存 60 秒聚合。** 10 秒原始数据留在设备 SD 卡（丝印已定：IO3=CLK,
IO14=MOSI, IO35=MISO, IO46=CS）。行数降到 1/6，家长端时间轴用 60 秒粒度完全够，
排查问题时 SD 卡上有全量数据。

## 关于特征向量

`features.py` 生成 16 维手工特征，不用文本 embedding —— 零模型成本、维度低、
每维可解释。相对最初方案改了三处，理由写在文件头部：

- 星期改 sin/cos（原来是唯一没归一化的维度，影响力是别人的 6 倍，且周日和周一数值最远）
- 移出护眼分和体力（派生量，会把同样信号计入两次）
- 检索用 `VEC_L2_DISTANCE` 而非 cosine（余弦忽略模长，但这里模长就是信号）
