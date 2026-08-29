/**
 * 伴学 API · Cloudflare Worker
 *
 * 一个 Worker 服务两端，设备和 App 互不知道对方存在：
 *   ESP32  --POST /ingest--▶  写 TiDB，响应回带配置（配置下行通道）
 *   手机   --GET  /api/*--▶   读 TiDB
 *
 * 用 @tidbcloud/serverless 走 HTTP 连库 —— Workers 跑在 V8 上开不了原生 TCP，
 * 传统 MySQL 驱动在这里用不了。数据库凭据只存在 Worker 的 secret 里，
 * 设备和 App 都拿不到。
 *
 * 接口契约与 services/api（FastAPI）完全一致，两边可以并存：
 * 本地开发用 FastAPI，线上用 Worker，客户端只换 URL。
 */
import { connect } from '@tidbcloud/serverless';
import { MOCK, DEFAULT_CONFIG } from './mock';

export interface Env {
  DATABASE_URL?: string;   // mysql://user:pass@host/db   （wrangler secret put）
  API_TOKEN?: string;      // 设了就要求 Bearer 鉴权      （wrangler secret put）
}

const JSON_HEADERS = {
  'content-type': 'application/json; charset=utf-8',
  'access-control-allow-origin': '*',
  'access-control-allow-headers': 'authorization, content-type',
  'access-control-allow-methods': 'GET, POST, OPTIONS',
};

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: JSON_HEADERS });

const db = (env: Env) =>
  env.DATABASE_URL ? connect({ url: env.DATABASE_URL }) : null;

/** 设了 API_TOKEN 就校验，没设则放行（方便先跑通链路） */
function authed(req: Request, env: Env): boolean {
  if (!env.API_TOKEN) return true;
  const h = req.headers.get('authorization') ?? '';
  return h === `Bearer ${env.API_TOKEN}`;
}

// ───────────────────────────────── 配置下行

async function configFor(env: Env, childId: string) {
  const conn = db(env);
  if (!conn) return DEFAULT_CONFIG;
  try {
    const rows = await conn.execute(
      'SELECT * FROM device_config WHERE child_id = ?', [childId],
    ) as Record<string, unknown>[];
    if (!rows?.length) return DEFAULT_CONFIG;
    const { child_id, updated_at, ...cfg } = rows[0];
    return cfg;
  } catch {
    return DEFAULT_CONFIG;
  }
}

// ───────────────────────────────── 时间

// 库里一律存 UTC（NOW() 就是 UTC），只在给人看的地方 +8 转北京时间。
// 之前 lastSync 直接把 UTC 打出去，显示成了 12:21 而不是 20:21。
const CST = (col: string) => `DATE_ADD(${col}, INTERVAL 8 HOUR)`;
/** 北京时间的"今天"，同时保留 ts 的范围下界让索引还能剪枝 */
const TODAY_CST = `ts >= DATE_SUB(NOW(), INTERVAL 2 DAY) AND ts <= NOW()
   AND DATE(${CST('ts')}) = DATE(${CST('NOW()')})`;
const hhmm = (v: unknown) => String(v ?? '').slice(11, 16);
/** "YYYY-MM-DD HH:MM:SS" UTC —— 板子直接喂给 RTC */
/** 板子发的是 12 位 ADC 原始值（0~4095），App 的 lightWord 按 0~100 判读。
 *  库里和 device_config 里一律保持 ADC —— 阈值是给板子用的，不能换算；
 *  只在发给 App 的那一层转成百分比。 */
const pct12 = (v: unknown) =>
  v == null ? 0 : Math.min(100, Math.round(Number(v) * 100 / 4095));
const utcNow = () => new Date().toISOString().slice(0, 19).replace('T', ' ');

/** 把逐分钟的样本压成连续段 */
function runs<T>(rows: T[], kind: (r: T) => string) {
  const out: { kind: string; minutes: number }[] = [];
  for (const r of rows) {
    const k = kind(r);
    const last = out[out.length - 1];
    if (last && last.kind === k) last.minutes++;
    else out.push({ kind: k, minutes: 1 });
  }
  return out;
}

// ───────────────────────────────── 设备上报

interface Sample {
  ts: string; present?: boolean; distance_mm?: number | null;
  light_left?: number | null; light_right?: number | null;
  temperature?: number | null; humidity?: number | null;
  pir_hits?: number; abnormal?: boolean;
}

async function ingest(req: Request, env: Env): Promise<Response> {
  const body = await req.json() as {
    device_id: string; child_id: string; firmware?: string;
    samples?: Sample[]; hp?: number; grow?: number; form?: string;
    simulated?: boolean;
  };
  const conn = db(env);
  let accepted = 0;

  // 时钟没对好的板子会发出两种垃圾时间戳：RTC 未设时是 2000 年之前，
  // 把北京时间当 UTC 发则是未来 8 小时。后者更阴险 —— 它会永远排在
  // ORDER BY ts DESC 的第一位，把真实数据挡在后面。两种都在入口挡掉。
  const floor = '2020-01-01';
  const ceil = new Date(Date.now() + 5 * 60_000).toISOString().slice(0, 19).replace('T', ' ');
  const okTs = (t?: string) => !!t && t >= floor && t <= ceil;
  const bad = body.samples?.filter(s => !okTs(s.ts)) ?? [];
  if (bad.length) body.samples = body.samples!.filter(s => okTs(s.ts));

  if (conn && body.samples?.length) {
    // 一次一条 INSERT 就是一次 HTTP 往返。补传时一批可能有几十条，
    // 拼成单条多值 upsert 后往返次数从 N 降到 ceil(N/200)。
    const CHUNK = 200;
    for (let off = 0; off < body.samples.length; off += CHUNK) {
      const part = body.samples.slice(off, off + CHUNK);
      const args: unknown[] = [];
      for (const s of part) {
        args.push(body.child_id, body.device_id, s.ts, s.present ? 1 : 0,
          s.distance_mm ?? null, s.light_left ?? null, s.light_right ?? null,
          s.temperature ?? null, s.humidity ?? null, s.pir_hits ?? 0,
          s.abnormal ? 1 : 0);
      }
      await conn.execute(
        `INSERT INTO sensor_minute
           (child_id, device_id, ts, present, distance_mm, light_left, light_right,
            temperature, humidity, pir_hits, abnormal)
         VALUES ${part.map(() => '(?,?,?,?,?,?,?,?,?,?,?)').join(',')}
         ON DUPLICATE KEY UPDATE present=VALUES(present),
           distance_mm=VALUES(distance_mm), light_left=VALUES(light_left),
           light_right=VALUES(light_right), temperature=VALUES(temperature),
           humidity=VALUES(humidity), pir_hits=VALUES(pir_hits),
           abnormal=VALUES(abnormal)`, args);
      accepted += part.length;
    }
  }

  // 灌演示数据的工具走的是同一个 /ingest，但它不是设备 —— 不能让它
  // 刷新 last_seen，否则板子明明拔了，App 上还显示「在线」。
  if (conn && !body.simulated) {
    await conn.execute(
      `INSERT INTO device (device_id, child_id, firmware, last_seen)
       VALUES (?,?,?,NOW())
       ON DUPLICATE KEY UPDATE firmware=VALUES(firmware), last_seen=NOW()`,
      [body.device_id, body.child_id, body.firmware ?? null],
    );
    if (body.hp !== undefined) {
      await conn.execute(
        `INSERT INTO pet_state (child_id, hp, grow, form, updated_at)
         VALUES (?,?,?,?,NOW())
         ON DUPLICATE KEY UPDATE hp=VALUES(hp), grow=VALUES(grow),
           form=VALUES(form), updated_at=NOW()`,
        [body.child_id, body.hp, body.grow ?? 0, body.form ?? 'normal'],
      );
    }
  }
  // 把服务器时间带回去。国内网络 UDP 123 常被挡，NTP 未必通，
  // 而这条 HTTPS 已经证明能走通 —— 用它对表比 NTP 可靠。
  return json({ ok: true, accepted, rejected: bad.length, now: utcNow(),
                config: await configFor(env, body.child_id),
                actions: await takeActions(env, body.child_id) });
}

// ───────────────────────────────── App 读取

/** 未接库或表里还没数据时回落到演示数据，结构完全一致，App 侧无感 */
async function snapshot(env: Env, childId: string) {
  const conn = db(env);
  if (!conn) return MOCK.snapshot;
  const base = { ...(MOCK.snapshot as Record<string, unknown>) };
  const todayCST = new Date(Date.now() + 8 * 3600_000).toISOString().slice(0, 10);
  try {
    // 这些查询之间没有依赖，串行发九次的话一个请求要两秒多。
    // TiDB serverless 走 HTTP，每次往返 200~400ms —— 并发是唯一的解。
    const [last, today, pet, dev, tail, cfg, ask] = await Promise.all([
      conn.execute(
        `SELECT * FROM sensor_minute WHERE child_id=? AND ts <= NOW()
           ORDER BY ts DESC LIMIT 1`, [childId]) as Promise<Record<string, any>[]>,
      conn.execute(
        `SELECT COALESCE(SUM(present),0) AS mins FROM sensor_minute
           WHERE child_id=? AND ${TODAY_CST}`, [childId]) as Promise<Record<string, any>[]>,
      conn.execute(
        'SELECT * FROM pet_state WHERE child_id=?', [childId]) as Promise<Record<string, any>[]>,
      conn.execute(
        `SELECT ${CST('last_seen')} AS seen_cst,
                TIMESTAMPDIFF(SECOND, last_seen, NOW()) AS age
           FROM device WHERE child_id=? ORDER BY last_seen DESC LIMIT 1`,
        [childId]) as Promise<Record<string, any>[]>,
      // 本轮连续 = 末尾这段没有断过的在座分钟数
      conn.execute(
        `SELECT present FROM sensor_minute
          WHERE child_id=? AND ${TODAY_CST} ORDER BY ts DESC LIMIT 240`,
        [childId]) as Promise<Record<string, any>[]>,
      configFor(env, childId) as Promise<Record<string, any>>,
      askTopics(env, childId, todayCST, addDays(todayCST, 1)),
    ]);

    if (!last?.length && !dev?.length) return base;   // 一条数据都没有，先给演示值

    let streak = 0;
    for (const r of tail ?? []) { if (!r.present) break; streak++; }
    // 把已经拿到的配置传进去，别让 eye() 再查一次
    const ey = await eye(env, childId, cfg) as Record<string, any>;

    const l = last?.[0] ?? {};
    const p = pet?.[0] ?? {};
    const d = dev?.[0];
    Object.assign(base, {
      form: p.form ?? 'normal',
      link: d && d.age !== null && d.age < 90 ? 'online' : 'offline',
      hp: p.hp ?? 100,
      grow: p.grow ?? 0,
      todayMinutes: Number(today?.[0]?.mins ?? 0),
      goalHours: cfg.goal_hours ?? 4,
      streakMinutes: streak,
      eyeScore: ey.score, eyeDeducted: 100 - ey.score,
      askCount: ask.total,
      askNote: ask.topics.length ? `多是${ask.topics[0].name}` : '今天还没有提问',
      lightLeft: pct12(l.light_left),
      lightRight: pct12(l.light_right),
      temperature: Number(l.temperature ?? 0),
      humidity: Number(l.humidity ?? 0),
      lastSync: d?.seen_cst ? hhmm(d.seen_cst) : '—',
    });
    return base;
  } catch (e) {
    return base;
  }
}

async function reminders(env: Env, childId: string) {
  const conn = db(env);
  if (!conn) return MOCK.reminders;
  try {
    const rows = await conn.execute(
      `SELECT ${CST('fired_at')} AS fired_cst, kind, detail, improved
       FROM reminder_event
       WHERE child_id=? AND fired_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
       ORDER BY fired_at`, [childId]) as Record<string, any>[];
    if (!rows?.length) return MOCK.reminders;
    const items = rows.map(r => ({
      when: String(r.fired_cst).slice(5, 16),
      kind: r.kind, detail: r.detail ?? '', improved: !!r.improved,
    }));
    const improved = items.filter(i => i.improved).length;
    return {
      ...(MOCK.reminders as Record<string, unknown>),
      total: items.length, improved,
      rate: items.length ? Math.round(improved * 100 / items.length) : 0,
      items,
    };
  } catch {
    return MOCK.reminders;
  }
}

// ───────────────────────────────── 孩子档案

/** App 首次引导时写一次。child_id 是设备侧固定的，这里只存展示信息。 */
async function putChild(req: Request, env: Env): Promise<Response> {
  const b = await req.json() as { child_id?: string; name?: string; grade?: string };
  const id = (b.child_id ?? '').trim();
  const name = (b.name ?? '').trim();
  if (!id || !name) return json({ error: 'child_id 和 name 都不能为空' }, 400);
  const conn = db(env);
  if (!conn) return json({ ok: true, child_id: id, name, grade: b.grade ?? null });
  await conn.execute(
    `INSERT INTO child (child_id, display_name, grade)
     VALUES (?,?,?)
     ON DUPLICATE KEY UPDATE display_name=VALUES(display_name), grade=VALUES(grade)`,
    [id, name, b.grade ?? null],
  );
  // 建档时顺手补一行默认配置，设备第一次上报就能拿到阈值
  await conn.execute(
    'INSERT IGNORE INTO device_config (child_id, updated_at) VALUES (?, NOW())', [id],
  );
  return json({ ok: true, child_id: id, name, grade: b.grade ?? null });
}

async function getChild(env: Env, childId: string) {
  const conn = db(env);
  if (!conn) return { child_id: childId, name: '小满', grade: null };
  const rows = await conn.execute(
    'SELECT child_id, display_name, grade FROM child WHERE child_id=?', [childId],
  ) as Record<string, any>[];
  if (!rows?.length) return { child_id: childId, name: null, grade: null };
  return { child_id: childId, name: rows[0].display_name, grade: rows[0].grade ?? null };
}

// ───────────────────────────────── 学习（实时）

const WEEK_CN = ['日', '一', '二', '三', '四', '五', '六'];

async function study(env: Env, childId: string) {
  const conn = db(env);
  if (!conn) return MOCK.study;
  const today = await conn.execute(
    `SELECT ${CST('ts')} AS t, present, abnormal
       FROM sensor_minute WHERE child_id=? AND ${TODAY_CST} ORDER BY ts`,
    [childId]) as Record<string, any>[];
  if (!today?.length) return MOCK.study;

  const segs = runs(today, r =>
    !r.present ? 'away' : (r.abnormal ? 'abnormal' : 'present'));
  const present = segs.filter(s => s.kind === 'present' || s.kind === 'abnormal');
  const minutes = today.reduce((n, r) => n + (r.present ? 1 : 0), 0);

  // 近 7 天（北京日）。分组键直接在 SQL 里转好，省得在 JS 里再算一次时区。
  const wk = await conn.execute(
    `SELECT DATE(${CST('ts')}) AS d, COALESCE(SUM(present),0) AS mins
       FROM sensor_minute
      WHERE child_id=? AND ts >= DATE_SUB(NOW(), INTERVAL 9 DAY)
      GROUP BY d ORDER BY d`, [childId]) as Record<string, any>[];
  const byDay = new Map(wk.map(r => [String(r.d).slice(0, 10), Number(r.mins)]));
  const todayKey = String(today[today.length - 1].t).slice(0, 10);
  const week: { label: string; minutes: number; isToday: boolean }[] = [];
  const base = new Date(todayKey + 'T00:00:00Z');
  for (let i = 6; i >= 0; i--) {
    const d = new Date(base.getTime() - i * 86400000);
    const key = d.toISOString().slice(0, 10);
    week.push({ label: WEEK_CN[d.getUTCDay()], minutes: byDay.get(key) ?? 0, isToday: i === 0 });
  }

  const hourMap = new Map<number, number>();
  for (const r of today) {
    if (!r.present) continue;
    const h = Number(String(r.t).slice(11, 13));
    hourMap.set(h, (hourMap.get(h) ?? 0) + 1);
  }
  const hourly = [...hourMap.entries()].sort((a, b) => a[0] - b[0])
    .map(([hour, m]) => ({ hour, value: Math.min(100, Math.round(m * 100 / 60)) }));

  const total = week.reduce((n, d) => n + d.minutes, 0);
  const first = hhmm(today[0].t);
  const last = hhmm(today[today.length - 1].t);
  const mid = hhmm(today[Math.floor(today.length / 2)].t);
  const peak = hourly.slice().sort((a, b) => b.value - a.value)[0];

  return {
    todayMinutes: minutes,
    segments: segs,
    axis: [first, mid, last],
    longestMinutes: present.reduce((m, s) => Math.max(m, s.minutes), 0),
    averageMinutes: present.length ? Math.round(minutes / present.length) : 0,
    awayCount: segs.filter(s => s.kind === 'away').length,
    week,
    weekTotal: `共 ${Math.floor(total / 60)} 小时 ${total % 60} 分`,
    hourly,
    hourlyNote: peak ? `最集中的时段是 ${peak.hour} 点前后。` : '今天的数据还不够画出规律。',
  };
}

// ───────────────────────────────── 护眼（实时）

async function eye(env: Env, childId: string, preloaded?: Record<string, any>) {
  const conn = db(env);
  if (!conn) return MOCK.eye;
  // snapshot 已经查过配置了，传进来就别再查一次
  const cfg = preloaded ?? await configFor(env, childId) as Record<string, any>;
  const near = cfg.distance_min ?? 400;
  const far = cfg.distance_max ?? 850;
  const dark = cfg.light_min ?? 3600;

  // 今日明细和近 7 天历史互不依赖，一起发
  const [rows, hist] = await Promise.all([
    conn.execute(
      `SELECT ${CST('ts')} AS t, distance_mm, light_left, light_right
         FROM sensor_minute
        WHERE child_id=? AND present=1 AND ${TODAY_CST} ORDER BY ts`,
      [childId]) as Promise<Record<string, any>[]>,
    conn.execute(
      `SELECT DATE(${CST('ts')}) AS d,
              SUM(distance_mm IS NOT NULL AND distance_mm < ?) AS close_m,
              SUM((COALESCE(light_left,0)+COALESCE(light_right,0))/2 < ?) AS dark_m
         FROM sensor_minute
        WHERE child_id=? AND present=1 AND ts >= DATE_SUB(NOW(), INTERVAL 9 DAY)
        GROUP BY d ORDER BY d`, [near, dark, childId]) as Promise<Record<string, any>[]>,
  ]);
  if (!rows?.length) return MOCK.eye;

  const measured = rows.filter(r => r.distance_mm != null);
  const closeMin = measured.filter(r => r.distance_mm < near).length;
  const farMin = measured.filter(r => r.distance_mm > far).length;
  const okMin = measured.length - closeMin - farMin;
  const darkMin = rows.filter(r =>
    ((Number(r.light_left ?? 0) + Number(r.light_right ?? 0)) / 2) < dark).length;

  // 偏近"次数"按连续段算，不按分钟 —— 连着近 10 分钟是一次，不是十次。
  const closeEvents = runs(measured, r => r.distance_mm < near ? 'close' : 'ok')
    .filter(s => s.kind === 'close').length;
  // 单次用眼超 20 分钟：连续在座段里超过 20 分钟的段数
  const longRuns = Math.floor(rows.length / 20);

  const pct = (n: number) => measured.length ? Math.round(n * 100 / measured.length) : 0;
  const deductions = [
    { title: `距离偏近 ${closeEvents} 次`, detail: `累计 ${closeMin} 分钟`,
      points: -Math.min(20, Math.round(closeMin / 3)) },
    { title: `单次用眼超 20 分钟 ${longRuns} 次`, detail: longRuns ? '未中途远眺' : '无',
      points: -Math.min(10, longRuns * 2) },
    { title: '光线偏暗', detail: `累计 ${darkMin} 分钟`,
      points: -Math.min(15, Math.round(darkMin / 4)) },
  ].filter(d => d.points < 0);
  const score = Math.max(0, 100 + deductions.reduce((n, d) => n + d.points, 0));

  // 近 7 天分数：同一套扣分规则按天重算一遍（hist 已在上面并发取到）
  const last7 = hist.slice(-7).map(r => Math.max(0, 100
    - Math.min(20, Math.round(Number(r.close_m) / 3))
    - Math.min(15, Math.round(Number(r.dark_m) / 4))));
  const last7Avg = last7.length
    ? Math.round(last7.reduce((a, b) => a + b, 0) / last7.length) : score;

  return {
    score, delta: score - last7Avg,
    deductions,
    buckets: [
      { label: '推荐区间', percent: pct(okMin), minutes: okMin },
      { label: '偏近', percent: pct(closeMin), minutes: closeMin },
      { label: '偏远', percent: pct(farMin), minutes: farMin },
    ],
    closeEvents,
    closeNote: closeMin
      ? `今天偏近累计 ${closeMin} 分钟，分成 ${closeEvents} 段。`
      : '今天没有出现明显的偏近。',
    last7: last7.length ? last7 : [score], last7Avg,
  };
}

// ───────────────────────────────── 家长端写回

const DDL_ACTION = `CREATE TABLE IF NOT EXISTS device_action (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  child_id     VARCHAR(64) NOT NULL,
  kind         VARCHAR(32) NOT NULL,
  created_at   DATETIME    NOT NULL,
  delivered_at DATETIME    NULL,
  KEY idx_pending (child_id, delivered_at, id)
)`;

/** 家长在 App 上按的一次性动作（喂草、奖励）。板子取走就算送到。 */
async function pushAction(req: Request, env: Env): Promise<Response> {
  const b = await req.json() as { child_id?: string; kind?: string };
  const id = (b.child_id ?? '').trim();
  const kind = (b.kind ?? '').trim();
  if (!id || !['feed', 'reward'].includes(kind)) {
    return json({ error: 'kind 只能是 feed 或 reward' }, 400);
  }
  const conn = db(env);
  if (!conn) return json({ ok: true, queued: 0 });
  await conn.execute(DDL_ACTION);
  await conn.execute(
    'INSERT INTO device_action (child_id, kind, created_at) VALUES (?,?,NOW())',
    [id, kind]);
  return json({ ok: true, queued: 1, kind });
}

/** 板子每次联系服务器时取一次。取走即标记已送达 —— 丢了家长再按一次就是了，
 *  为一次喂草做确认协议不值得。 */
async function takeActions(env: Env, childId: string) {
  const conn = db(env);
  if (!conn) return [];
  try {
    const rows = await conn.execute(
      `SELECT id, kind FROM device_action
        WHERE child_id=? AND delivered_at IS NULL
        ORDER BY id LIMIT 8`, [childId]) as Record<string, any>[];
    if (!rows?.length) return [];
    await conn.execute(
      `UPDATE device_action SET delivered_at=NOW()
        WHERE id IN (${rows.map(() => '?').join(',')})`,
      rows.map(r => r.id));
    return rows.map(r => ({ id: Number(r.id), kind: String(r.kind) }));
  } catch {
    return [];      // 表还没建出来时不该拖垮上报
  }
}

/** App 改设置 → 写 device_config 并把 rev +1。板子比对 rev 变了就生效。 */
async function putSettings(req: Request, env: Env): Promise<Response> {
  const b = await req.json() as Record<string, any>;
  const id = (b.child_id ?? '').trim();
  if (!id) return json({ error: 'child_id 不能为空' }, 400);
  const conn = db(env);
  if (!conn) return json({ ok: true });

  // 只接受认识的字段，且都夹到合理范围 —— 客户端传什么都不能把板子搞坏
  const clamp = (v: any, lo: number, hi: number, dflt: number) => {
    const n = Number(v);
    return Number.isFinite(n) ? Math.max(lo, Math.min(hi, Math.round(n))) : dflt;
  };
  const bit = (v: any) => (v ? 1 : 0);
  const cfg = {
    goal_hours:    clamp(b.goalHours, 1, 12, 4),
    distance_min:  clamp(b.distanceMin, 200, 800, 400),
    distance_max:  clamp(b.distanceMax, 400, 1500, 850),
    light_min:     clamp(b.lightMin, 500, 4095, 3600),
    voice_on:      bit(b.voiceOn ?? true),
    anim_on:       bit(b.animOn ?? true),
    push_on:       bit(b.pushOn ?? true),
    child_visible: bit(b.childVisible ?? true),
  };
  if (cfg.distance_max <= cfg.distance_min) cfg.distance_max = cfg.distance_min + 200;

  await conn.execute(
    `INSERT INTO device_config
       (child_id, rev, goal_hours, distance_min, distance_max, light_min,
        voice_on, anim_on, push_on, child_visible, updated_at)
     VALUES (?,1,?,?,?,?,?,?,?,?,NOW())
     ON DUPLICATE KEY UPDATE
       rev = rev + 1,                       -- 板子就是靠这个数变了才知道要重读
       goal_hours=VALUES(goal_hours), distance_min=VALUES(distance_min),
       distance_max=VALUES(distance_max), light_min=VALUES(light_min),
       voice_on=VALUES(voice_on), anim_on=VALUES(anim_on),
       push_on=VALUES(push_on), child_visible=VALUES(child_visible),
       updated_at=NOW()`,
    [id, cfg.goal_hours, cfg.distance_min, cfg.distance_max, cfg.light_min,
     cfg.voice_on, cfg.anim_on, cfg.push_on, cfg.child_visible]);

  return json({ ok: true, config: await configFor(env, id) });
}

/** 设置页读的是 device_config，不再是写死的演示值。 */
async function settings(env: Env, childId: string) {
  const conn = db(env);
  if (!conn) return MOCK.settings;
  const [c, dev, name] = await Promise.all([
    configFor(env, childId) as Promise<Record<string, any>>,
    conn.execute(
      'SELECT device_id, firmware FROM device WHERE child_id=? ORDER BY last_seen DESC LIMIT 1',
      [childId]) as Promise<Record<string, any>[]>,
    getChild(env, childId),
  ]);
  const base = MOCK.settings as Record<string, any>;
  return {
    ...base,
    goalHours: c.goal_hours ?? 4,
    distanceMin: c.distance_min ?? 400,
    distanceMax: c.distance_max ?? 850,
    lowLightHint: `低于 ${Math.round((c.light_min ?? 3600) * 100 / 4095)}% 判定偏暗，冷却 ${Math.round((c.cooldown_s ?? 1800) / 60)} 分钟`,
    channels: [
      { ...base.channels[0], on: !!c.voice_on },
      { ...base.channels[1], on: !!c.anim_on },
      { ...base.channels[2], on: !!c.push_on },
    ],
    childVisible: !!c.child_visible,
    deviceName: `书桌设备 · ${name.name ?? '未命名'}的桌子`,
    firmware: dev?.[0]?.firmware ?? base.firmware,
  };
}

// ───────────────────────────────── 提问

async function putAsk(req: Request, env: Env): Promise<Response> {
  const b = await req.json() as {
    child_id?: string; topic?: string; question?: string;
    answer?: string; asked_at?: string;
  };
  const id = (b.child_id ?? '').trim();
  if (!id) return json({ error: 'child_id 不能为空' }, 400);
  const conn = db(env);
  if (!conn) return json({ ok: true });
  // 和样本一样的时间戳门槛：时钟没对好的板子会发出 2000 年或未来的时间
  const ts = b.asked_at && b.asked_at >= '2020-01-01' && b.asked_at <= utcNow()
    ? b.asked_at : utcNow();
  await conn.execute(
    'INSERT INTO ask_log (child_id, asked_at, topic, question, answer) VALUES (?,?,?,?,?)',
    [id, ts, b.topic ?? null, b.question ?? null, b.answer ?? null]);
  return json({ ok: true });
}

/** 某段时间里的问题类型排行 */
async function askTopics(env: Env, childId: string, from: string, to: string) {
  const conn = db(env);
  if (!conn) return { topics: [], total: 0 };
  try {
    const rows = await conn.execute(
      `SELECT COALESCE(topic,'其他') AS name, COUNT(*) AS n
         FROM ask_log
        WHERE child_id=? AND ${CST('asked_at')} >= ? AND ${CST('asked_at')} < ?
        GROUP BY name ORDER BY n DESC`, [childId, from, to]) as Record<string, any>[];
    const total = rows.reduce((a, r) => a + Number(r.n), 0);
    return { topics: rows.slice(0, 3).map(r => ({ name: String(r.name), count: Number(r.n) })), total };
  } catch {
    return { topics: [], total: 0 };
  }
}

// ───────────────────────────────── 周报（实时）

/** ISO 周号。周一为周始 —— 和国内习惯一致。 */
function isoWeek(dateStr: string) {
  const t = new Date(dateStr + 'T00:00:00Z');
  const day = t.getUTCDay() || 7;
  t.setUTCDate(t.getUTCDate() + 4 - day);          // 挪到本周四
  const y0 = Date.UTC(t.getUTCFullYear(), 0, 1);
  const week = Math.ceil(((t.getTime() - y0) / 86400000 + 1) / 7);
  return { year: t.getUTCFullYear(), week };
}
const weekKeyOf = (d: string) => {
  const { year, week } = isoWeek(d);
  return `${year}-W${String(week).padStart(2, '0')}`;
};
/** 该日期所在周的周一 */
function mondayOf(dateStr: string) {
  const t = new Date(dateStr + 'T00:00:00Z');
  t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7));
  return t.toISOString().slice(0, 10);
}
const addDays = (d: string, n: number) => {
  const t = new Date(d + 'T00:00:00Z');
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
};
const md = (d: string) => `${Number(d.slice(5, 7))}月${Number(d.slice(8, 10))}`;
/** 跨月的那一周要写成「7月27–8月2日」，不能是「7月27–2日」 */
const range = (a: string, b: string) =>
  a.slice(5, 7) === b.slice(5, 7)
    ? `${md(a)}–${Number(b.slice(8, 10))}日`
    : `${md(a)}日–${md(b)}日`;

/** 按北京日聚合一次，后面所有周的计算都从这份结果切。 */
async function dailyRollup(env: Env, childId: string, days = 84) {
  const conn = db(env);
  if (!conn) return [];
  const cfg = await configFor(env, childId) as Record<string, any>;
  const near = cfg.distance_min ?? 400;
  const dark = cfg.light_min ?? 3600;
  return await conn.execute(
    `SELECT DATE(${CST('ts')}) AS d,
            COALESCE(SUM(present),0) AS mins,
            SUM(present=1 AND distance_mm IS NOT NULL AND distance_mm < ?) AS close_m,
            SUM(present=1 AND (COALESCE(light_left,0)+COALESCE(light_right,0))/2 < ?) AS dark_m
       FROM sensor_minute
      WHERE child_id=? AND ts >= DATE_SUB(NOW(), INTERVAL ? DAY) AND ts <= NOW()
      GROUP BY d ORDER BY d`,
    [near, dark, childId, days]) as Record<string, any>[];
}

/** 和 /api/eye 同一套扣分规则，保证两个页面说的是同一件事 */
const dayScore = (closeM: number, darkM: number) => Math.max(0, 100
  - Math.min(20, Math.round(closeM / 3))
  - Math.min(15, Math.round(darkM / 4)));

const WEEK_LETTERS = ['一', '二', '三', '四', '五', '六', '日'];

function summarize(rows: Record<string, any>[], monday: string) {
  const byDay = new Map(rows.map(r => [String(r.d).slice(0, 10), r]));
  const days: { label: string; minutes: number; isToday: boolean }[] = [];
  let mins = 0, closeM = 0, darkM = 0, active = 0;
  const scores: number[] = [];
  for (let i = 0; i < 7; i++) {
    const key = addDays(monday, i);
    const r = byDay.get(key);
    const m = Number(r?.mins ?? 0);
    days.push({ label: WEEK_LETTERS[i], minutes: m, isToday: false });
    if (r) {
      mins += m; closeM += Number(r.close_m ?? 0); darkM += Number(r.dark_m ?? 0);
      if (m > 0) { active++; scores.push(dayScore(Number(r.close_m ?? 0), Number(r.dark_m ?? 0))); }
    }
  }
  const score = scores.length
    ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;
  const best = days.reduce((a, b) => (b.minutes > a.minutes ? b : a), days[0]);
  return { days, mins, closeM, darkM, active, score, best };
}

/** 有数据的周，最近的在前 */
async function weeklyList(env: Env, childId: string) {
  const rows = await dailyRollup(env, childId);
  if (!rows?.length) return [];
  const seen = new Map<string, { minutes: number; monday: string }>();
  for (const r of rows) {
    const d = String(r.d).slice(0, 10);
    const k = weekKeyOf(d);
    const cur = seen.get(k) ?? { minutes: 0, monday: mondayOf(d) };
    cur.minutes += Number(r.mins ?? 0);
    seen.set(k, cur);
  }
  return [...seen.entries()]
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([key, v]) => ({
      key,
      label: `第 ${Number(key.slice(6))} 周`,
      range: range(v.monday, addDays(v.monday, 6)),
      minutes: v.minutes,
    }));
}

const hm = (m: number) => `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`;
const signed = (n: number, unit = '') =>
  n === 0 ? '持平' : `${n > 0 ? '+' : '−'}${Math.abs(n)}${unit}`;

async function weekly(env: Env, childId: string, weekKey?: string) {
  const rows = await dailyRollup(env, childId);
  if (!rows?.length) return { ...(MOCK.weekly as object), weekKey: '', days: [] };

  const dates = rows.map(r => String(r.d).slice(0, 10));
  const target = weekKey && dates.some(d => weekKeyOf(d) === weekKey)
    ? weekKey : weekKeyOf(dates[dates.length - 1]);
  const monday = mondayOf(dates.find(d => weekKeyOf(d) === target)!);
  const prevMonday = addDays(monday, -7);

  const cur = summarize(rows, monday);
  const prev = summarize(rows, prevMonday);
  const sunday = addDays(monday, 6);

  // 叙事段落用真实数字拼。这是"由本周传感器数据自动生成"承诺的东西 ——
  // 写死一段漂亮话就成了假的。
  const dMin = cur.mins - prev.mins;
  const dScore = cur.score - (prev.score || cur.score);
  const active = cur.days.filter(d => d.minutes > 0).map(d => d.minutes);
  const low = active.length ? Math.min(...active) : 0;
  const paragraphs: string[] = [];

  // 「比上周多 0 分钟」是句废话，差值为零就换个说法
  const cmp = (n: number, unit: string) =>
    n === 0 ? '和上周持平' : `比上周${n > 0 ? '多' : '少'} ${Math.abs(n)}${unit}`;

  paragraphs.push(
    prev.mins > 0
      ? `这一周累计专注 ${Math.floor(cur.mins / 60)} 小时 ${cur.mins % 60} 分，${cmp(dMin, ' 分钟')}。七天里有 ${cur.active} 天坐到了桌前，最长的一天是周${cur.best.label}，${cur.best.minutes} 分钟。`
      : `这一周累计专注 ${Math.floor(cur.mins / 60)} 小时 ${cur.mins % 60} 分，分布在 ${cur.active} 天里。最长的一天是周${cur.best.label}，${cur.best.minutes} 分钟。这是第一周记录，还没有上周可比。`);

  const scoreCmp = !prev.score ? ''
    : dScore === 0 ? '，和上周持平'
    : `，${dScore > 0 ? '比上周高' : '比上周低'} ${Math.abs(dScore)} 分`;
  paragraphs.push(
    cur.closeM || cur.darkM
      ? `护眼分 ${cur.score}${scoreCmp}。这周有 ${cur.closeM} 分钟距离偏近、${cur.darkM} 分钟光线不够——扣分几乎都来自这两项。`
      : `护眼分 ${cur.score}${scoreCmp}。这周距离和光线都没有明显问题。`);

  // 只有一天有记录时，「最多的一天」和「最少的一天」是同一天，那句话就不能说
  paragraphs.push(
    active.length >= 2
      ? `每天的时长差得不小：最多的一天 ${cur.best.minutes} 分钟，最少的有记录的一天 ${low} 分钟。规律比总量更值得看——固定的时段比偶尔的长时间更容易坚持。`
      : `这一周只有 ${cur.active} 天留下了记录。样本太少，还看不出规律——规律比总量更值得看。`);

  // 没有上周可比时 dMin 就等于本周总量，不能拿它说"更久了"
  const headline = cur.mins === 0 ? '这一周没有记录到桌前时间'
    : prev.mins === 0 ? '这是有记录以来的第一周'
    : dMin > 20 ? '这一周他在桌前待得更久了'
    : dMin < -20 ? '这一周桌前时间少了一些'
    : cur.darkM > cur.mins * 0.2 ? '时长稳住了，但灯光该管一管'
    : '这一周的节奏和上周差不多';

  const ask = await askTopics(env, childId, monday, addDays(sunday, 1));
  return {
    weekKey: target,
    weekLabel: `第 ${Number(target.slice(6))} 周 · ${range(monday, sunday)}`,
    headline,
    paragraphs,
    days: cur.days,
    // 第一周没有可比的上周，差值留空 —— 拿本周总量当"涨幅"是假的
    deltas: prev.mins === 0 ? [
      { label: '专注时长', value: hm(cur.mins), delta: '首周' },
      { label: '护眼分均值', value: String(cur.score), delta: '首周' },
      { label: '有记录天数', value: `${cur.active} 天`, delta: '首周' },
    ] : [
      { label: '专注时长', value: hm(cur.mins), delta: signed(dMin, ' 分') },
      { label: '护眼分均值', value: String(cur.score), delta: signed(dScore) },
      { label: '有记录天数', value: `${cur.active} 天`, delta: signed(cur.active - prev.active, ' 天') },
    ],
    topics: ask.topics, topicTotal: ask.total,
  };
}

// ───────────────────────────────── 路由

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method === 'OPTIONS') return new Response(null, { headers: JSON_HEADERS });

    const url = new URL(req.url);
    const path = url.pathname.replace(/\/+$/, '') || '/';
    const childId = url.searchParams.get('child_id') ?? 'xiaoman';

    if (path === '/time') return json({ now: utcNow() });
    if (path === '/health') {
      return json({ ok: true, db: !!env.DATABASE_URL, auth: !!env.API_TOKEN });
    }
    if (!authed(req, env)) return json({ error: 'unauthorized' }, 401);

    try {
      if (path === '/ingest' && req.method === 'POST') return await ingest(req, env);
      if (path === '/config') return json(await configFor(env, childId));
      if (path === '/api/child' && req.method === 'POST') return await putChild(req, env);
      if (path === '/api/settings' && req.method === 'POST') return await putSettings(req, env);
      if (path === '/api/action' && req.method === 'POST') return await pushAction(req, env);
      if (path === '/api/ask' && req.method === 'POST') return await putAsk(req, env);
      // 板子空闲时的轻量轮询：只拿配置和待办动作，不带样本。
      // 家长按下喂草到小羊有反应，靠的就是这一条。
      if (path === '/pull') {
        return json({ now: utcNow(), config: await configFor(env, childId),
                      actions: await takeActions(env, childId) });
      }

      switch (path) {
        case '/api/snapshot':   return json(await snapshot(env, childId));
        case '/api/reminders':  return json(await reminders(env, childId));
        case '/api/child':      return json(await getChild(env, childId));
        case '/api/eye':        return json(await eye(env, childId));
        case '/api/study':      return json(await study(env, childId));
        case '/api/diary':      return json(MOCK.diary);
        case '/api/milestones': return json(MOCK.milestones);
        case '/api/weekly':     return json(await weekly(env, childId, url.searchParams.get('week') ?? undefined));
        case '/api/weekly/list': return json(await weeklyList(env, childId));
        case '/api/settings':   return json(await settings(env, childId));
      }
      return json({ error: 'not found', path }, 404);
    } catch (e: any) {
      // 查询失败时明确报错，不假装有数据
      return json({ error: String(e?.message ?? e) }, 500);
    }
  },
};
