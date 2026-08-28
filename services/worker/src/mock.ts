/** 演示数据。字段名与 iOS 的 Codable 模型逐一对应 —— 未接库时 App 拿到的
 *  结构和接库后完全一致，切换不需要改客户端代码。 */
export const MOCK: Record<string, unknown> = {
  snapshot: {
    form: "normal", link: "online", hp: 78, grow: 62, growTarget: 80,
    streakMinutes: 23, todayMinutes: 52, goalHours: 4,
    eyeScore: 92, eyeDeducted: 8,
    temperature: 26.4, humidity: 54, lightLeft: 72, lightRight: 58,
    askCount: 4, askNote: "多是数学应用题",
    reminderCount: 3, reminderImproved: 2, lastSync: "16:02",
    todayComment: "今天开局不错——19 点后这一轮连续了 23 分钟，比平时同一时段长。灯光偏暗过 8 分钟，小羊打了个哈欠。",
  },
  eye: {
    score: 92, delta: 3,
    deductions: [
      { title: "距离偏近 12 次", detail: "累计 14 分钟", points: -4 },
      { title: "单次用眼超 20 分钟 2 次", detail: "未中途远眺", points: -2 },
      { title: "光线偏暗", detail: "累计 8 分钟", points: -2 },
    ],
    buckets: [
      { label: "推荐区间", percent: 76, minutes: 70 },
      { label: "偏近", percent: 15, minutes: 14 },
      { label: "偏远", percent: 9, minutes: 8 },
    ],
    closeEvents: 12,
    closeNote: "集中在 18:47–18:55 和 19:22 之后两段，两段都出现在光线偏暗之后。",
    last7: [86, 91, 88, 92, 87, 90, 92], last7Avg: 89,
  },
  study: {
    todayMinutes: 52,
    segments: [
      { kind: "present", minutes: 18 }, { kind: "abnormal", minutes: 8 },
      { kind: "present", minutes: 11 }, { kind: "away", minutes: 21 },
      { kind: "present", minutes: 23 },
    ],
    axis: ["18:10", "19:00", "19:42"],
    longestMinutes: 23, averageMinutes: 17, awayCount: 2,
    week: [
      { label: "六", minutes: 64, isToday: false }, { label: "日", minutes: 71, isToday: false },
      { label: "一", minutes: 46, isToday: false }, { label: "二", minutes: 58, isToday: false },
      { label: "三", minutes: 39, isToday: false }, { label: "四", minutes: 44, isToday: false },
      { label: "五", minutes: 52, isToday: true },
    ],
    weekTotal: "共 5 小时 48 分",
    hourly: [
      { hour: 15, value: 22 }, { hour: 16, value: 38 }, { hour: 17, value: 45 },
      { hour: 18, value: 68 }, { hour: 19, value: 100 }, { hour: 20, value: 74 },
      { hour: 21, value: 30 },
    ],
    hourlyNote: "近两周里，19:00–20:00 这一小时的平均段长最长。",
  },
  diary: [
    { time: "18:10", text: "小满坐下了。我睁开眼。" },
    { time: "18:50", text: "他凑得有点近。我叫了一声。" },
    { time: "18:58", text: "桌前空了 21 分钟。我打了个盹。" },
    { time: "19:19", text: "他又回来了。这一轮已经 23 分钟。" },
    { time: "现在", text: "体力 78，成长 62。还差 18 点开花。" },
  ],
  milestones: [
    { title: "第一次连续 30 分钟", date: "8月12日", reached: true },
    { title: "成长值破 50", date: "8月19日", reached: true },
    { title: "连续 7 天达成目标", date: "8月26日", reached: true },
    { title: "成长值 80 · 开花形态", date: "还差 18 点", reached: false },
  ],
  weekly: {
    weekLabel: "第 35 周 · 8月22–28日",
    headline: "这一周，他把晚饭后那段时间坐住了",
    paragraphs: [
      "小满这周专注 5 小时 48 分，比上周多 36 分钟。多出来的时间几乎都在周二和周四晚上——这两天他连续坐满 40 分钟以上，中间没有离开桌子。",
      "护眼分从 87 升到 90。距离偏近的次数在减少，但仍然集中在每天 19 点以后，那是灯光最容易不够的时段。",
      "提醒响应率从 62% 升到 75%。台灯类的提醒他基本都会照做；「休息喝水」这一类有两次没有反应，下周可以留意。",
    ],
    deltas: [
      { label: "专注时长", value: "5:48", delta: "+36 分" },
      { label: "护眼分均值", value: "90", delta: "+3" },
      { label: "提醒响应率", value: "75%", delta: "+13pt" },
    ],
    topics: [
      { name: "数学应用题", count: 9 }, { name: "生字读音", count: 6 },
      { name: "英语单词", count: 4 },
    ],
    topicTotal: 19,
  },
  reminders: {
    total: 8, improved: 6, rate: 75, lastWeekRate: 62,
    items: [
      { when: "周一 19:12", kind: "台灯偏暗", detail: "6 分钟内光照回到适中", improved: true },
      { when: "周一 20:03", kind: "距离偏近", detail: "2 分钟内退回推荐区间", improved: true },
      { when: "周二 19:40", kind: "休息喝水", detail: "之后又连续坐了 18 分钟", improved: false },
      { when: "周三 18:55", kind: "台灯偏暗", detail: "开了顶灯，差值收到 4pt", improved: true },
      { when: "周四 19:28", kind: "距离偏近", detail: "3 分钟内退回推荐区间", improved: true },
      { when: "周四 20:15", kind: "休息喝水", detail: "没有离座", improved: false },
      { when: "周五 19:05", kind: "距离偏近", detail: "1 分钟内退回推荐区间", improved: true },
      { when: "周五 19:33", kind: "距离偏近", detail: "4 分钟内退回推荐区间", improved: true },
    ],
    weekly: [58, 61, 55, 64, 60, 62, 75],
    weekLabels: ["29", "30", "31", "32", "33", "34", "35"],
    note: "「休息喝水」的响应率连续两周在降。同一句提示听多了会失效，可以换个说法或调冷却时间。",
  },
  settings: {
    goalHours: 4, distanceMin: 400, distanceMax: 850,
    lowLightHint: "按相对百分比判定，冷却 30 分钟",
    channels: [
      { label: "设备语音提示", hint: "小羊出声，孩子端能听到", on: true },
      { label: "设备动画提示", hint: "屏幕上小羊做动作，不出声", on: true },
      { label: "推送", hint: "仅每日总结与周报，不做实时告警", on: true },
    ],
    childVisible: true,
    deviceName: "书桌设备 · 小满的桌子",
    firmware: "1.4.2",
    calibrated: false,
  },
};

export const DEFAULT_CONFIG = {
  rev: 1, goal_hours: 4, distance_min: 400, distance_max: 850,
  // 实测常态室内光照 ADC 3935（12 位满量程 4095），原阈值 1500 几乎永不触发
  light_min: 3600,
  cooldown_s: 1800, voice_on: 1, anim_on: 1, push_on: 1, child_visible: 1,
};
