import SwiftUI

/// 先给结论，再给可追溯的扣分明细。
/// 偏近用注意色芥末黄，不用红。图表细柱无圆角，只有今天一根上强调色。
struct EyeView: View {
    @EnvironmentObject var store: Store

    var body: some View {
        let e = store.eye
        Page(title: "护眼") {
            Card {
                VStack(alignment: .leading, spacing: 8) {
                    Label2(t: "今天的护眼分")
                    HStack(alignment: .firstTextBaseline, spacing: 7) {
                        Text("\(e.score)").font(Theme.serif(46)).foregroundStyle(Theme.ink)
                        Text("分 · 比昨天 \(e.delta >= 0 ? "+" : "")\(e.delta)")
                            .font(Theme.sans(13)).foregroundStyle(Theme.accent)
                    }
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 12) {
                    Label2(t: "扣分明细 · 共 \(e.totalDeduction)")
                    ForEach(e.deductions) { d in
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(d.title).font(Theme.sans(14)).foregroundStyle(Theme.ink)
                                Text(d.detail).font(Theme.sans(11)).foregroundStyle(Theme.muted)
                            }
                            Spacer()
                            Text("\(d.points)")
                                .font(Theme.sans(15, .medium)).foregroundStyle(Theme.warn)
                        }
                    }
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Label2(t: "距离分布")
                        Spacer()
                        Text("推荐区间 400–850mm")
                            .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                    }
                    GeometryReader { g in
                        HStack(spacing: 2) {
                            ForEach(e.buckets) { b in
                                Rectangle()
                                    .fill(tint(b.label))
                                    .frame(width: max(4, g.size.width * CGFloat(b.percent) / 100 - 2))
                            }
                        }
                    }
                    .frame(height: 13)
                    ForEach(e.buckets) { b in
                        HStack(spacing: 9) {
                            Rectangle().fill(tint(b.label)).frame(width: 9, height: 9)
                            Text(b.label).font(Theme.sans(13)).foregroundStyle(Theme.ink)
                            Spacer()
                            Text("\(b.percent)% · \(b.minutes) 分")
                                .font(Theme.sans(12)).foregroundStyle(Theme.muted)
                        }
                    }
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 10) {
                    Label2(t: "偏近事件 · 今日 \(e.closeEvents) 次")
                    Text(e.closeNote)
                        .font(Theme.sans(13)).foregroundStyle(Theme.ink).lineSpacing(4)
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Label2(t: "近 7 天护眼分")
                        Spacer()
                        Text("均 \(e.last7Avg)").font(Theme.sans(11)).foregroundStyle(Theme.muted)
                    }
                    ThinBars(values: e.last7,
                             labels: ["六", "日", "一", "二", "三", "四", "五"],
                             highlight: e.last7.count - 1)
                }
            }
        }
    }

    private func tint(_ label: String) -> Color {
        switch label {
        case "推荐区间": return Theme.accent
        case "偏近":     return Theme.warn      // 芥末黄，不用红
        default:         return Theme.ink.opacity(0.18)
        }
    }
}
