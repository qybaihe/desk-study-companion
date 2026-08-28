import Foundation

/// 全部取自设计稿 Banxue Parent App.dc.html 的真实文案与数值。
enum Mock {
    static let snapshot = Snapshot(
        form: .normal, link: .online, hp: 78, grow: 62, growTarget: 80,
        streakMinutes: 23, todayMinutes: 52, goalHours: 4,
        eyeScore: 92, eyeDeducted: 8,
        temperature: 26.4, humidity: 54, lightLeft: 72, lightRight: 58,
        askCount: 4, askNote: "多是数学应用题",
        reminderCount: 3, reminderImproved: 2,
        lastSync: "16:02",
        todayComment: "今天开局不错——19 点后这一轮连续了 23 分钟，比平时同一时段长。灯光偏暗过 8 分钟，小羊打了个哈欠。"
    )

    static let eye = EyeReport(
        score: 92, delta: 3,
        deductions: [
            .init(title: "距离偏近 12 次", detail: "累计 14 分钟", points: -4),
            .init(title: "单次用眼超 20 分钟 2 次", detail: "未中途远眺", points: -2),
            .init(title: "光线偏暗", detail: "累计 8 分钟", points: -2),
        ],
        buckets: [
            .init(label: "推荐区间", percent: 76, minutes: 70),
            .init(label: "偏近", percent: 15, minutes: 14),
            .init(label: "偏远", percent: 9, minutes: 8),
        ],
        closeEvents: 12,
        closeNote: "集中在 18:47–18:55 和 19:22 之后两段，两段都出现在光线偏暗之后。",
        last7: [86, 91, 88, 92, 87, 90, 92], last7Avg: 89
    )

    static let study = StudyReport(
        todayMinutes: 52,
        segments: [
            .init(kind: .present, minutes: 18),
            .init(kind: .abnormal, minutes: 8),
            .init(kind: .present, minutes: 11),
            .init(kind: .away, minutes: 21),
            .init(kind: .present, minutes: 23),
        ],
        axis: ["18:10", "19:00", "19:42"],
        longestMinutes: 23, averageMinutes: 17, awayCount: 2,
        week: [
            .init(label: "六", minutes: 64, isToday: false),
            .init(label: "日", minutes: 71, isToday: false),
            .init(label: "一", minutes: 46, isToday: false),
            .init(label: "二", minutes: 58, isToday: false),
            .init(label: "三", minutes: 39, isToday: false),
            .init(label: "四", minutes: 44, isToday: false),
            .init(label: "五", minutes: 52, isToday: true),
        ],
        weekTotal: "共 5 小时 48 分",
        hourly: [.init(hour: 15, value: 22), .init(hour: 16, value: 38),
                 .init(hour: 17, value: 45), .init(hour: 18, value: 68),
                 .init(hour: 19, value: 100), .init(hour: 20, value: 74),
                 .init(hour: 21, value: 30)],
        hourlyNote: "近两周里，19:00–20:00 这一小时的平均段长最长。"
    )

    static let diary: [DiaryLine] = [
        .init(time: "18:10", text: "小满坐下了。我睁开眼。"),
        .init(time: "18:50", text: "他凑得有点近。我叫了一声。"),
        .init(time: "18:58", text: "桌前空了 21 分钟。我打了个盹。"),
        .init(time: "19:19", text: "他又回来了。这一轮已经 23 分钟。"),
        .init(time: "现在", text: "体力 78，成长 62。还差 18 点开花。"),
    ]

    static let milestones: [Milestone] = [
        .init(title: "第一次连续 30 分钟", date: "8月12日", reached: true),
        .init(title: "成长值破 50", date: "8月19日", reached: true),
        .init(title: "连续 7 天达成目标", date: "8月26日", reached: true),
        .init(title: "成长值 80 · 开花形态", date: "还差 18 点", reached: false),
    ]

    static let weekly = WeeklyReport(
        weekKey: "2026-W35",
        days: [
            .init(label: "一", minutes: 46, isToday: false),
            .init(label: "二", minutes: 71, isToday: false),
            .init(label: "三", minutes: 39, isToday: false),
            .init(label: "四", minutes: 64, isToday: false),
            .init(label: "五", minutes: 52, isToday: true),
            .init(label: "六", minutes: 0, isToday: false),
            .init(label: "日", minutes: 0, isToday: false),
        ],
        weekLabel: "第 35 周 · 8月22–28日",
        headline: "这一周，他把晚饭后那段时间坐住了",
        paragraphs: [
            "小满这周专注 5 小时 48 分，比上周多 36 分钟。多出来的时间几乎都在周二和周四晚上——这两天他连续坐满 40 分钟以上，中间没有离开桌子。",
            "护眼分从 87 升到 90。距离偏近的次数在减少，但仍然集中在每天 19 点以后，那是灯光最容易不够的时段。",
            "提醒响应率从 62% 升到 75%。台灯类的提醒他基本都会照做；「休息喝水」这一类有两次没有反应，下周可以留意。",
        ],
        deltas: [
            .init(label: "专注时长", value: "5:48", delta: "+36 分"),
            .init(label: "护眼分均值", value: "90", delta: "+3"),
            .init(label: "提醒响应率", value: "75%", delta: "+13pt"),
        ],
        topics: [
            .init(name: "数学应用题", count: 9),
            .init(name: "生字读音", count: 6),
            .init(name: "英语单词", count: 4),
        ],
        topicTotal: 19
    )

    static let reminders = ReminderReport(
        total: 8, improved: 6, rate: 75, lastWeekRate: 62,
        items: [
            .init(when: "周一 19:12", kind: "台灯偏暗", detail: "6 分钟内光照回到适中", improved: true),
            .init(when: "周一 20:03", kind: "距离偏近", detail: "2 分钟内退回推荐区间", improved: true),
            .init(when: "周二 19:40", kind: "休息喝水", detail: "之后又连续坐了 18 分钟", improved: false),
            .init(when: "周三 18:55", kind: "台灯偏暗", detail: "开了顶灯，差值收到 4pt", improved: true),
            .init(when: "周四 19:28", kind: "距离偏近", detail: "3 分钟内退回推荐区间", improved: true),
            .init(when: "周四 20:15", kind: "休息喝水", detail: "没有离座", improved: false),
            .init(when: "周五 19:05", kind: "距离偏近", detail: "1 分钟内退回推荐区间", improved: true),
            .init(when: "周五 19:33", kind: "距离偏近", detail: "4 分钟内退回推荐区间", improved: true),
        ],
        weekly: [58, 61, 55, 64, 60, 62, 75],
        weekLabels: ["29", "30", "31", "32", "33", "34", "35"],
        note: "「休息喝水」的响应率连续两周在降。同一句提示听多了会失效，可以换个说法或调冷却时间。"
    )

    static let settings = Settings(
        goalHours: 4, distanceMin: 400, distanceMax: 850,
        lowLightHint: "按相对百分比判定，冷却 30 分钟",
        channels: [
            .init(label: "设备语音提示", hint: "小羊出声，孩子端能听到", on: true),
            .init(label: "设备动画提示", hint: "屏幕上小羊做动作，不出声", on: true),
            .init(label: "推送", hint: "仅每日总结与周报，不做实时告警", on: true),
        ],
        childVisible: true,
        deviceName: "书桌设备 · 小满的桌子",
        firmware: "1.4.2",
        calibrated: false
    )
}
