import Foundation

enum PetForm: String, Codable, CaseIterable {
    case normal, evolved, sick, lowLight, restBreak, fed
    case away          // 桌前没人。以前没有这一档，于是人走了首页还在说"在专注学习"

    /// 板子将来多加一个状态不该让整个 snapshot 解码失败，认不出就当 normal。
    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = PetForm(rawValue: raw) ?? .normal
    }

    var label: String {
        switch self {
        case .normal:    return "素体"
        case .evolved:   return "开花"
        case .sick:      return "不舒服"
        case .lowLight:  return "光线偏暗"
        case .restBreak: return "该休息了"
        case .fed:       return "刚被喂过"
        case .away:      return "桌前没人"
        }
    }

    /// 逐帧动画。帧取自设备端 LCD 素材，已还原成透明底
    /// （设备只画白色和配件色，黑色的脸是 LCD 黑底透出来的）。
    ///
    /// 素材名按画的内容取，不按谁用它 —— 原来那组绿对勾叫 animLowLight，
    /// 于是「光线偏暗」这个坏状态举着对勾，「达成目标」反而只有个爱心。
    var animation: (prefix: String, count: Int, fps: Double)? {
        switch self {
        case .normal:    return ("animNormal", 31, 14)
        case .evolved:   return ("animCheck", 8, 8)     // 达成目标 → ✓
        case .sick:      return ("animSick", 4, 3.5)
        case .lowLight:  return ("animCross", 8, 8)     // 光线偏暗 → ✗
        case .restBreak: return ("animCross", 8, 8)     // 该休息了 → ✗
        case .fed:       return ("animHeart", 4, 5)     // 被喂/奖励 → ♥
        case .away:      return nil
        }
    }

    /// 每个状态对应一张母版。sick 用蓝冰袋那张 —— 画师本来就没用红色。
    var asset: String {
        switch self {
        case .normal:    return "sheepNormal"
        case .evolved:   return "sheepCheck"
        case .sick:      return "sheepSick"
        case .lowLight:  return "sheepCross"
        case .restBreak: return "sheepCross"
        case .fed:       return "sheepHeart"
        case .away:      return "sheepNormal"
        }
    }
}

enum DeviceLink: String, Codable { case online, offline }

enum SegmentKind: String, Codable {
    case present     // 在座
    case away        // 离开
    case abnormal    // 环境异常 —— 用低饱和蓝，不用红
}

// MARK: - 此刻

struct Snapshot: Codable, Equatable {
    var form: PetForm
    var link: DeviceLink
    var hp: Int
    var grow: Int
    var growTarget: Int          // 80 开花
    var streakMinutes: Int       // 本轮连续
    var todayMinutes: Int
    var goalHours: Int
    var eyeScore: Int
    var eyeDeducted: Int
    var temperature: Double
    var humidity: Int
    var lightLeft: Int           // 相对百分比，未标定
    var lightRight: Int
    var askCount: Int
    var askNote: String
    var reminderCount: Int
    var reminderImproved: Int
    var lastSync: String
    var todayComment: String

    var goalPct: Int { min(100, todayMinutes * 100 / max(goalHours * 60, 1)) }
    var lightDiff: Int { abs(lightLeft - lightRight) }
    var lightWord: String {
        let avg = (lightLeft + lightRight) / 2
        return avg >= 70 ? "明亮" : (avg >= 40 ? "适中" : "偏暗")
    }
    var responseRate: Int {
        reminderCount == 0 ? 0
            : Int((Double(reminderImproved) / Double(reminderCount) * 100).rounded())
    }
    var comfortWord: String {
        (temperature >= 18 && temperature <= 28 && humidity >= 30 && humidity <= 70) ? "舒适" : "注意"
    }

    /// 状态句由小羊来说，不写「孩子离开桌子 X 分钟」
    var heroLine: String {
        if link == .offline { return "设备离线，读不到小羊的状态" }
        switch form {
        case .sick:      return "光线有点暗，小羊不太舒服"
        case .evolved:   return "本轮已连续 \(streakMinutes) 分钟，小羊开花了"
        case .lowLight:  return "光线偏暗，小羊眯起了眼睛"
        case .restBreak: return "坐了挺久了，小羊想让他歇一会儿"
        case .fed:       return "刚吃过草，小羊很开心"
        case .away:      return "桌前没人，小羊在等他回来"
        case .normal:    return "他在专注学习，小羊很精神"
        }
    }
    var heroSub: String {
        if link == .offline { return "最后一次同步 \(lastSync)。检查一下设备的 Wi-Fi" }
        switch form {
        case .sick:      return "体力 \(hp)。顶灯打开它就会缓过来"
        case .lowLight:  return "把顶灯也打开，差值会收回来"
        case .restBreak: return "本轮已连续 \(streakMinutes) 分钟"
        case .away:      return todayMinutes > 0
                                ? "今天已经坐了 \(todayMinutes) 分钟"
                                : "今天还没开始"
        case .fed:       return "体力 \(hp)，刚涨了一点"
        default:         return "本轮已连续 \(streakMinutes) 分钟"
        }
    }
}

// MARK: - 护眼

struct Deduction: Codable, Identifiable, Equatable {
    var id: String { title }
    var title: String
    var detail: String
    var points: Int
}

struct DistanceBucket: Codable, Identifiable, Equatable {
    var id: String { label }
    var label: String
    var percent: Int
    var minutes: Int
}

struct EyeReport: Codable, Equatable {
    var score: Int
    var delta: Int
    var deductions: [Deduction]
    var buckets: [DistanceBucket]
    var closeEvents: Int
    var closeNote: String
    var last7: [Int]
    var last7Avg: Int
    var totalDeduction: Int { deductions.reduce(0) { $0 + $1.points } }
}

// MARK: - 学习

struct Segment: Codable, Identifiable, Equatable {
    var id = UUID()
    var kind: SegmentKind
    var minutes: Int
    enum CodingKeys: String, CodingKey { case kind, minutes }
}

struct DayBar: Codable, Identifiable, Equatable {
    var id: String { label }
    var label: String
    var minutes: Int
    var isToday: Bool
}

struct HourSlot: Codable, Identifiable, Equatable {
    var id: Int { hour }
    var hour: Int
    var value: Int          // 0..100
}

struct StudyReport: Codable, Equatable {
    var todayMinutes: Int
    var segments: [Segment]
    var axis: [String]           // 18:10 / 19:00 / 19:42
    var longestMinutes: Int
    var averageMinutes: Int
    var awayCount: Int
    var week: [DayBar]
    var weekTotal: String
    var hourly: [HourSlot]       // Swift 的 [Int:Int] 会编成交替数组，改用结构体保证 JSON 互通
    var hourlyNote: String
}

// MARK: - 提醒与响应

struct Reminder: Codable, Identifiable, Equatable {
    var id = UUID()
    var when: String
    var kind: String
    var detail: String
    var improved: Bool
    enum CodingKeys: String, CodingKey { case when, kind, detail, improved }
    var result: String { improved ? "已改善" : "未改善" }
}

struct ReminderReport: Codable, Equatable {
    var total: Int
    var improved: Int
    var rate: Int
    var lastWeekRate: Int
    var items: [Reminder]
    var weekly: [Int]            // 近 7 周响应率
    var weekLabels: [String]
    var note: String
}

// MARK: - 提问记录

/// 孩子在设备上问过的一句话，和小羊的回答。
/// 板子自己写不了库 —— 它手里只有音频，文本在语音服务那一侧。
struct AskItem: Codable, Identifiable, Equatable {
    var id: String { day + when + question }
    var when: String        // 08-29 09:19
    var day: String         // 2026-08-29
    var topic: String
    var question: String
    var answer: String
}

struct AskReport: Codable, Equatable {
    var items: [AskItem]
    var total: Int
    var todayCount: Int
}

// MARK: - 小羊

struct DiaryLine: Codable, Identifiable, Equatable {
    var id = UUID()
    var time: String
    var text: String
    enum CodingKeys: String, CodingKey { case time, text }
}

struct Milestone: Codable, Identifiable, Equatable {
    var id = UUID()
    var title: String
    var date: String
    var reached: Bool
    enum CodingKeys: String, CodingKey { case title, date, reached }
}

// MARK: - 周报

struct WeeklyDelta: Codable, Identifiable, Equatable {
    var id: String { label }
    var label: String
    var value: String
    var delta: String
}

struct TopicCount: Codable, Identifiable, Equatable {
    var id: String { name }
    var name: String
    var count: Int
}

/// 往期周报的一条目录
struct WeekRef: Codable, Identifiable, Equatable {
    var id: String { key }
    var key: String          // 2026-W35
    var label: String        // 第 35 周
    var range: String        // 8月24–30日
    var minutes: Int
}

struct WeeklyReport: Codable, Equatable {
    var weekKey: String
    var days: [DayBar]           // 七天，封面的迷你柱
    var weekLabel: String
    var headline: String
    var paragraphs: [String]
    var deltas: [WeeklyDelta]
    var topics: [TopicCount]
    var topicTotal: Int
}

// MARK: - 设置

struct ToggleItem: Codable, Identifiable, Equatable {
    var id: String { label }
    var label: String
    var hint: String
    var on: Bool
}

struct Settings: Codable, Equatable {
    var goalHours: Int
    var distanceMin: Int
    var distanceMax: Int
    var lowLightHint: String
    var channels: [ToggleItem]
    var childVisible: Bool
    var deviceName: String
    var firmware: String
    var calibrated: Bool
}
