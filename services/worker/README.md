# 伴学 API · Cloudflare Worker

**线上地址：`https://sheepy.timoz.me`**

一个 Worker 服务两端，设备和 App 互不知道对方存在：

```
ESP32  ──POST /ingest──▶  Worker  ──HTTP──▶  TiDB Serverless
手机   ──GET  /api/*───▶    │
                           └──fetch──▶  Agent Stack（周报 AI，待接）
```

数据库凭据只存在 Worker 的 secret 里，**设备和 App 都拿不到**。

---

## 为什么是 Worker 而不是自建后端

- 不依赖任何一台常开的机器（原方案后端跑在笔记本上，合盖就断）
- Workers 跑在 V8 上开不了原生 TCP，所以用 `@tidbcloud/serverless`（**HTTP 驱动**）连库
- ESP32 不需要 MySQL 驱动，也不需要 Digest 认证，发普通 HTTP JSON 即可

## 为什么必须用自定义域名

**`*.workers.dev` 在国内被 DNS 污染**，实测：

| 解析器 | 返回 IP | 实际归属 |
|---|---|---|
| 本地 | 199.16.158.104 | Twitter |
| 1.1.1.1 | 128.242.240.61 | Verizon |
| 8.8.8.8 | 162.125.80.6 | Dropbox |

每次都不同、全是无关站点。对照组 `cloudflare.com` / `github.com` 解析全部正常，
所以是这个域被专门针对。绑到 `sheepy.timoz.me` 后解析到 `172.67.209.123`，
是 Cloudflare 真实 IP，恢复正常。

**结论：不要用 workers.dev 地址，一律用 `sheepy.timoz.me`。**

---

## 接口

鉴权：设了 `API_TOKEN` 后所有接口（除 `/health`）需要
`Authorization: Bearer <token>`；没设则放行。

### 设备上报

```http
POST /ingest
Content-Type: application/json

{
  "device_id": "desk-01",
  "child_id":  "xiaoman",
  "firmware":  "1.4.2",
  "hp": 78, "grow": 62, "form": "normal",
  "samples": [
    { "ts": "2026-08-28 18:00:00", "present": true, "distance_mm": 520,
      "light_left": 3900, "light_right": 3700,
      "temperature": 26.4, "humidity": 54, "pir_hits": 3, "abnormal": false }
  ]
}
```

响应 **回带配置**，设备比对 `rev`，变了就落盘生效：

```json
{ "ok": true, "accepted": 1,
  "config": { "rev": 1, "goal_hours": 4, "distance_min": 400, "distance_max": 850,
              "light_min": 3600, "cooldown_s": 1800,
              "voice_on": 1, "anim_on": 1, "push_on": 1, "child_visible": 1 } }
```

`form` 取值：`normal` / `evolved` / `sick` / `lowLight` / `restBreak` / `fed`

### App 读取

`GET /api/{snapshot,eye,study,diary,milestones,weekly,reminders,settings}?child_id=xiaoman`

`GET /config?child_id=xiaoman` · `GET /health`

> 未接库或表里没数据时回落到演示数据，**结构完全一致**，客户端无感。

---

## 部署与配置

```bash
cd services/worker
npm install
npm run deploy
```

设置机密（值不会进代码库，也不会进聊天记录）：

```bash
npx wrangler secret put DATABASE_URL
# 粘贴：mysql://<用户名>.root:<密码>@gateway01.<区域>.prod.aws.tidbcloud.com:4000/study_buddy

npx wrangler secret put API_TOKEN
# 自己定一个随机串，设备和 App 都用它
```

建表：把 `services/api/schema.sql` 在 TiDB 控制台的 SQL Editor 里跑一遍。

看日志：`npx wrangler tail`

---

## 当前状态

- ✅ 已部署，`sheepy.timoz.me` 可访问，八个端点全部 200
- ✅ iOS 的 `Codable` 模型能直接解码线上响应（已实测）
- ⬜ `DATABASE_URL` 未设 → 现在返回演示数据，不碰 TiDB
- ⬜ `API_TOKEN` 未设 → 当前无鉴权，任何人可调
