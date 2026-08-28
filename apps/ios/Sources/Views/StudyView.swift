import SwiftUI

/// 一条横向分段条读懂一天。在座 / 离开 / 环境异常三种段落，异常段用低饱和蓝。
/// 段落统计只留三个数。热力条是「最容易坐住的时段」，用于安排作业顺序，不是考核。
struct StudyView: View {
    @EnvironmentObject var store: Store

    var body: some View {
        let st = store.study
        Page(title: "学习") {
            Card {
                VStack(alignment: .leading, spacing: 14) {
                    VStack(alignment: .leading, spacing: 6) {
                        Label2(t: "今天在桌前的一段时间")
                        HStack(alignment: .firstTextBaseline, spacing: 5) {
                            Text("\(st.todayMinutes)").font(Theme.serif(40)).foregroundStyle(Theme.ink)
                            Text("分钟专注").font(Theme.sans(12)).foregroundStyle(Theme.muted)
                        }
                        Text("今日目标 \(store.snapshot.goalHours) 小时 · 已完成 \(store.snapshot.goalPct)%")
                            .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                    }

                    GeometryReader { g in
                        let total = max(1, st.segments.reduce(0) { $0 + $1.minutes })
                        HStack(spacing: 2) {
                            ForEach(st.segments) { seg in
                                Rectangle()
                                    .fill(tint(seg.kind))
                                    .frame(width: max(3, g.size.width * CGFloat(seg.minutes) / CGFloat(total) - 2))
                            }
                        }
                    }
                    .frame(height: 17)

                    HStack {
                        ForEach(st.axis, id: \.self) { t in
                            Text(t).font(Theme.mono(10)).foregroundStyle(Theme.muted)
                            if t != st.axis.last { Spacer() }
                        }
                    }

                    HStack(spacing: 16) {
                        legend(.present, "在座")
                        legend(.away, "离开")
                        legend(.abnormal, "环境异常")
                        Spacer()
                    }
                }
            }

            HStack(spacing: 11) {
                stat("最长连续", "\(st.longestMinutes) 分")
                stat("平均段长", "\(st.averageMinutes) 分")
                stat("离桌", "\(st.awayCount) 次")
            }

            Card {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Label2(t: "近 7 天专注时长")
                        Spacer()
                        Text(st.weekTotal).font(Theme.sans(11)).foregroundStyle(Theme.muted)
                    }
                    ThinBars(values: st.week.map(\.minutes),
                             labels: st.week.map(\.label),
                             highlight: st.week.firstIndex(where: \.isToday))
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 12) {
                    Label2(t: "一天中最容易坐住的时段")
                    HStack(spacing: 4) {
                        ForEach(st.hourly) { slot in
                            VStack(spacing: 5) {
                                RoundedRectangle(cornerRadius: 2)
                                    .fill(Theme.accent.opacity(0.14 + 0.86 * Double(slot.value) / 100))
                                    .frame(height: 34)
                                Text("\(slot.hour)").font(Theme.sans(10)).foregroundStyle(Theme.muted)
                            }
                        }
                    }
                    Text(st.hourlyNote)
                        .font(Theme.sans(12)).foregroundStyle(Theme.muted).lineSpacing(3)
                }
            }
        }
    }

    private func tint(_ k: SegmentKind) -> Color {
        switch k {
        case .present:  return Theme.accent
        case .away:     return Theme.ink.opacity(0.14)
        case .abnormal: return Theme.sick        // 异常段用低饱和蓝
        }
    }

    private func legend(_ k: SegmentKind, _ t: String) -> some View {
        HStack(spacing: 6) {
            Rectangle().fill(tint(k)).frame(width: 12, height: 9)
            Text(t).font(Theme.sans(11)).foregroundStyle(Theme.muted)
        }
    }

    private func stat(_ label: String, _ value: String) -> some View {
        Card(pad: 13) {
            VStack(alignment: .leading, spacing: 5) {
                Label2(t: label)
                Text(value).font(Theme.serif(20)).foregroundStyle(Theme.ink)
            }
        }
    }
}
