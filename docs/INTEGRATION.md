# 联调说明 · 三端接线

一句话：**两端都只跟 Worker 说话，Worker 读写 TiDB。**
板子和 App 互相不知道对方存在，也都拿不到数据库凭据。

```
                    ┌── POST /ingest ─────▶ 上行：样本 + hp/grow/form
ESP32-S3 ───────────┤
                    └── GET  /pull ◀────── 下行：配置 + 家长动作（≤20 秒）

                    ┌── GET  /api/* ─────── 读快照 / 学习 / 护眼 / 设置
iOS App  ───────────┤
                    └── POST /api/settings  写 device_config（rev +1）
                        POST /api/action    排喂草 / 奖励
```

两个方向都是活的。家长在 App 上改一个阈值或按一次喂草，板子最多 20 秒后
生效；生效后的新数值立刻回推，App 大约 20 秒就能看到。

线上地址 `https://sheepy.timoz.me`，鉴权 `Authorization: Bearer <API_TOKEN>`。

---

## 零、五条必须记住的坑

全是实测踩出来的，不是理论风险。

1. **必须带 `User-Agent`。** Cloudflare 边缘会把没有 UA 的请求直接挡成
   `403`（连 Worker 都进不去），而 MicroPython 的 `urequests` 默认什么都不带。
   `net.py` 里已经写死了 `sheepy-esp32/1.0`。

2. **`ts` 一律发 UTC。** 库里存 UTC，Worker 只在给人看的字段上 `+8`
   转北京时间。板子的 RTC 是北京时，所以发之前要减 8 小时——
   `net.utc_stamp()` 已经处理好了。发成北京时间的话，晚上 8 点之后的数据
   会被算进第二天，"今日专注"永远是 0。

3. **`*.workers.dev` 在国内被 DNS 污染**，四个解析器返回四个不同的错误 IP。
   必须走自有域名。`sheepy.timoz.me` 是 Workers 的 Custom Domain，
   DNS 记录由 wrangler 部署时自动建，**不需要手动加任何记录**。

4. **上报必须跑在独立线程里。** 实测板子到 Cloudflare 一次 TLS 上报要
   **7~21 秒**（手机热点上偶尔 30 秒后 ETIMEDOUT），而主循环的看门狗只有
   8 秒。同步发请求 = 每次上报都重启板子。`Net.flush()` 现在只把批次交给
   `_thread` 起的后台线程，自己立刻返回；实测上报期间主循环仍空转 500 多次。

5. **NTP 未必通。** `pool.ntp.org` 在这个热点上直接 ETIMEDOUT。
   已经换成 `ntp.aliyun.com`，并且加了兜底：不通就 `GET /time` 问 Worker 要
   —— 那条 HTTPS 本来就得通，比 UDP 123 可靠。见 `Net.ensure_clock()`。

---

## 一、板子这边

固件已经接好了，改配置就能跑。

### 1. 配置

`firmware/sheepy_config.py`：

```python
WIFI_SSID = "..."          # 现场换网只改这两行
WIFI_PASSWORD = "..."
BASE_URL  = "https://sheepy.timoz.me"
API_TOKEN = "..."
CHILD_ID  = "sheepy"       # 必须和 App 的 Backend.childID 一致
DEVICE_ID = "esp32-s3-01"
BATCH_SECONDS = 60
```

`CHILD_ID` 两边对不上，App 会读到一个空的孩子——这是最容易犯的错。

### 2. 主循环已经接好的三处

`firmware/main.py`：

| 位置 | 做什么 |
| --- | --- |
| 循环开头 | `uplink.pump()` — 非阻塞维护 Wi-Fi，断线指数退避重连 |
| `pet_state` 算完之后 | `_uplink_tick(...)` — 按分钟聚合传感器值 |
| `Net` 内部 | 攒够 `BATCH_SECONDS` 发一批，失败落 SD 卡等补传 |

聚合规则：一分钟内过半时间在座就记 `present=1`；距离取有效读数的均值；
光敏取两路各自均值；`pir_hits` 是这一分钟检出运动的轮数。

### 3. 四个保护

- **后台线程**：上报和对表都跑在 `_thread` 里，主循环不阻塞（见坑 4）。
  同一时刻只允许一个后台任务；上一批还没发完，新样本就先攒着。
- **看门狗**：`Net` 收了 `feed=system_watchdog.feed`，在网络操作前后各喂一次。
- **重试**：热点上五次里会中一次 ECONNRESET，线程里直接重试一次
  （间隔 2 秒），还失败才落盘。
- **时钟门槛**：`clock_synced` 为假时不上传。RTC 没设时
  `time.localtime()` 是 2000 年，传上去的样本会落在查不到的日期里。

### 4. 上报格式

```json
POST /ingest
{
  "device_id": "esp32-s3-01",
  "child_id":  "sheepy",
  "firmware":  "sheepy-1.0",
  "hp": 91, "grow": 55, "form": "normal",
  "samples": [
    {"ts": "2026-08-28 12:26:00",     // UTC！
     "present": true, "distance_mm": 512,
     "light_left": 3880, "light_right": 3820,
     "temperature": 26.0, "humidity": 55,
     "pir_hits": 6, "abnormal": false}
  ]
}
```

响应里带回 `config`，`net.py` 比对 `rev` 变了就落盘生效——
不需要额外的连接或协议。

### 5. 板端自检

串口被 LCD 抢走了（`main.py` 启动 3 秒后把 GPIO43/44 改成 LCD 的 DC/CS），
所以每次连板都要先硬复位再抢窗口。`tooling/board.py` 已经封好：

```bash
python3 tooling/board_uplink_test.py
```

依次打印 Wi-Fi → DNS → NTP → 可用内存 → POST 结果 → 下行配置。
六步全绿就说明板子这条腿通了。

---

## 二、App 这边

**不需要任何连接配置。** 后端地址、令牌、`child_id` 全部编在
`apps/ios/Sources/Backend.swift` 里：

```swift
enum Backend {
    static let baseURL = URL(string: "https://sheepy.timoz.me")!
    static let token   = "..."
    static let childID = "sheepy"       // 和固件的 CHILD_ID 同一个值
}
```

引导页只问一件因人而异的事：孩子叫什么。填完 `POST /api/child` 建档，
之后每 10 秒轮询一次 `/api/*`。

设置页底部有「重设」，清掉本地档案回到引导页重新建。
云端数据不删——用同一个 `child_id` 重新建档就接得回去。

---

## 三、反向通道（App → 板子）

以前这半边是空的：设置页的开关只动本地 `@State`，喂草按钮 action 里一行没有，
板子把下行配置落了盘但一次都没读。现在三处都接上了。

### 改设置

App 每改一项就 `POST /api/settings`，Worker 写 `device_config` 并把
**`rev` 加一**。板子比对 `rev` 发现变了，就在 `_apply_downlink_config()` 里
真正落到各个阈值上：

| 字段 | 落到哪 |
| --- | --- |
| `goal_hours` | `pet_system.set_daily_goal_seconds()` → 写 `/pet_config.json` |
| `distance_min/max` | `PetGrowthSystem.DISTANCE_MIN_MM / MAX_MM` |
| `light_min` `cooldown_s` | `low_light_reminder` 的判定和冷却 |
| `voice_on` | 关掉就不再往 `voice_queue` 里排提示音 |
| `anim_on` | 关掉小羊就不自己跳了 |
| `child_visible` | 关掉 LCD 只留小羊，不显示专注时长和目标 |

实测：App 上把目标从 3 小时点到 4 小时 → `rev` 2→3 →
板子 `/pet_config.json` 变成 `14400`。

### 喂草 / 奖励

`POST /api/action` 进 `device_action` 队列，板子下次联系服务器时取走，
**取走即标记已送达**——为一次喂草做确认协议不值得，丢了家长再按一次。

动作既上屏也真的作用到小羊身上，不然家长会觉得按钮是假的：

| 动作 | LCD | 数值 |
| --- | --- | --- |
| `feed` | 48 帧跳跃动画 + `FED!`，6 秒 | 体力 +8 |
| `reward` | 4 帧开花动画 + `REWARD!`，6 秒 | 成长 +5 |

板子上没有专门的"被投喂"素材，所以复用了现成的跳跃帧和开花帧。

应用完立刻 `push_state()` 把新的 hp/grow 推回去，不等下一个 60 秒的批量周期
——否则家长按完要等一分半才看得到变化。实测端到端 **18 秒**。

---

## 四、小羊状态的六档映射

板子的 `visual_state()` 只有 `NORMAL / SICK / EVOLVED` 三档，而 App 认六档。
护眼产品看不到"光线偏暗"、专注产品分不出"人走了"，所以上报前按优先级细分：

```
动作生效中 → fed
不在座     → away          ← 新增。以前人走了首页还在说"在专注学习"
SICK       → sick
偏暗未恢复 → lowLight      ← 以前永远传不到手机
休息提醒响过 → restBreak    ← 同上
EVOLVED    → evolved
其余       → normal
```

App 侧 `PetForm` 加了 `away`，并且把解码改成宽容的——板子将来多一个状态
不该让整个 snapshot 解码失败：

```swift
init(from decoder: Decoder) throws {
    let raw = try decoder.singleValueContainer().decode(String.self)
    self = PetForm(rawValue: raw) ?? .normal
}
```

---

## 五、两条数据在哪里换算

板子和 App 对同一个量的理解不一样，换算只在 Worker 里做一次：

| 量 | 板子 / 库里 | App 看到的 | 在哪转 |
| --- | --- | --- | --- |
| 光敏 | 12 位 ADC 原始值 `0~4095` | 百分比 `0~100` | `snapshot()` 的 `pct12()` |
| 时间 | UTC | 北京时间字符串 | `CST()` / `hhmm()` |

**光敏的阈值 `light_min = 3600` 是 ADC，不能换算** —— 它是下行给板子用的。
之前 App 直接拿 ADC 当百分比读，985 被判成"明亮"，实际是偏暗。

Worker 的 `/ingest` 还会挡掉两类脏时间戳：早于 `2020-01-01`（RTC 没设，
落在 2000 年）和晚于当前 5 分钟（把北京时间当 UTC 发，落在未来 8 小时）。
后者尤其阴险——它会永远排在 `ORDER BY ts DESC` 第一位，把真实数据挡在后面。

---

## 六、接口一览

| 方法 | 路径 | 数据来源 |
| --- | --- | --- |
| GET | `/health` | 无需鉴权，返回 `{ok, db, auth}` |
| GET | `/time` | 服务器 UTC，板子 NTP 不通时拿它对表 |
| GET | `/pull` | 板子空闲时轻量拉：配置 + 待办动作，不带样本 |
| POST | `/ingest` | 写 `sensor_minute` / `device` / `pet_state`，回带配置和 `now` |
| GET | `/config` | `device_config` 表 |
| POST | `/api/child` | 写 `child` 表（建档/改名） |
| POST | `/api/settings` | 写 `device_config`，`rev` +1 |
| POST | `/api/action` | 排一个 `feed` / `reward` 进 `device_action` |
| GET | `/api/child` | 读 `child` 表 |
| GET | `/api/snapshot` | **实时** — 末条样本 + 今日在座分钟 + 本轮连续 + 护眼分 |
| GET | `/api/study` | **实时** — 分段、时段分布、近 7 天 |
| GET | `/api/eye` | **实时** — 距离分桶、扣分项、近 7 天分数 |
| GET | `/api/reminders` | **实时** — `reminder_event` 表 |
| GET | `/api/settings` | **实时** — `device_config` + `device` 表 |
| GET | `/api/weekly` | **实时** — 按周聚合，`?week=2026-W34` 看往期 |
| GET | `/api/weekly/list` | **实时** — 有数据的周，最近的在前 |
| GET | `/api/diary` `/api/milestones` | 仍是演示数据 |

表里没数据时实时接口会回落到演示数据，结构完全一致，App 侧无感。

---

## 七、周报是怎么算出来的

`/api/weekly` 不再返回写死的漂亮话。一次 `dailyRollup()` 把最近 84 天按
北京日聚合，之后所有周的计算都从这一份结果切 —— 翻往期不会多打一次库。

- **周界**：ISO 周，周一为周始。`isoWeek()` 把日期挪到本周四再算周号，
  这样跨年的那一周不会算错。
- **护眼分**：和 `/api/eye` 用同一个 `dayScore()`,两个页面说的必须是同一件事。
- **叙事段落**：用真实数字拼模板句。这是"由本周传感器数据自动生成"承诺的
  东西 —— 写死一段漂亮话就成了假的。

几个容易写错的边界，都已经处理：

| 情况 | 错误写法 | 现在 |
| --- | --- | --- |
| 差值为 0 | 「比上周多 0 分钟」 | 「和上周持平」 |
| 第一周（没有上周） | `dMin` 等于本周总量，标题变成"待得更久了" | 标题「这是有记录以来的第一周」，三个差值都显示「首周」 |
| 只有一天有记录 | 「最多的一天 65 分，最少的一天 65 分」 | 「样本太少，还看不出规律」 |
| 跨月的周 | 「7月27–2日」 | 「7月27日–8月2日」 |
| 空数组取 min | `Math.min()` 返回 `Infinity` | 先判空 |

**问题类型**现在读的是 `ask_log`，按周分组。板子的 `voice_qa_client`
将来直接打 `POST /api/ask` 就能接上：

```json
{"child_id":"sheepy","topic":"数学应用题",
 "question":"这道题为什么要先算括号里的？","asked_at":"2026-08-28 13:20:00"}
```

`asked_at` 是 UTC，和样本一样有 2020/未来两道门槛。那一周没有提问时，
`topics` 返回空数组，App 显示「这一周没有提问记录」—— 空着比编三条出来诚实。

---

## 八、还没做的

- `ask_log` / `reminder_event` 板子还没写，所以「今日提问」和
  「提醒与响应」两张卡仍是演示值。
- `todayComment`（首页那句话）是写死的。这里本来是 TiDB 向量检索
  + LLM 的位置：拿当天的行为向量去检索历史相似日，再生成点评。
- `anim_on` / `child_visible` 两个开关的代码路径和已验证的 `goal_hours`
  完全一样，但没有单独在屏幕上肉眼确认过。
- 今天的 `sensor_minute` 里混着 `tooling/seed_demo.py` 灌的演示数据和
  板子的真数据。演示时说得清就行；要彻底干净就换个 `child_id`。

**灌演示数据不会让设备看起来在线。** `seed_demo.py` 用 `device_id=sim-demo`
并在 body 里带 `"simulated": true`，Worker 收到就跳过 `device` 和 `pet_state`
的写入。之前它用的是板子的 device_id，结果板子拔了 App 上还显示「在线」——
数据假不要紧，设备状态不能撒谎。

---

## 九、快速自检

```bash
# 1. Worker 活着、库连上了、鉴权开着
curl -s https://sheepy.timoz.me/health
# 期望 {"ok":true,"db":true,"auth":true}

# 2. 模拟一条上报（注意 ts 是 UTC）
curl -s -X POST https://sheepy.timoz.me/ingest \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"device_id":"esp32-s3-01","child_id":"sheepy","hp":88,"grow":46,
       "samples":[{"ts":"2026-08-28 12:26:00","present":true,
                   "light_left":3880,"temperature":26.0}]}'
# 期望 {"ok":true,"accepted":1,"config":{...}}

# 3. 读回来
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://sheepy.timoz.me/api/snapshot?child_id=sheepy"
# lastSync 应该是北京时间的当前时刻，link 应该是 online

# 4. 灌一段可信历史，把 study / eye 两屏喂满
python3 tooling/seed_demo.py --token "$TOKEN"
```

`link` 判定是 `last_seen` 距今小于 90 秒。板子 60 秒发一批，
所以正常在线时不会跳成离线；超过 90 秒没上报就是真断了。
