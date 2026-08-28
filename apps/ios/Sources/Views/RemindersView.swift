import SwiftUI

/// 这是这个产品独有的指标。标题不是「本周提醒 8 次」，
/// 而是「8 次里 6 次他自己调整了」。未改善用中性灰，不用红。
struct RemindersView: View {
    @EnvironmentObject var store: Store

    var body: some View {
        let r = store.reminders
        Page(title: "提醒与响应") {
            Card(pad: 20) {
                VStack(alignment: .leading, spacing: 13) {
                    Text("本周 \(r.total) 次提醒里，\(r.improved) 次他自己调整了")
                        .font(Theme.serif(20)).foregroundStyle(Theme.ink).lineSpacing(5)
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text("\(r.rate)%").font(Theme.serif(34)).foregroundStyle(Theme.accent)
                        Text("响应率 · 上周 \(r.lastWeekRate)%")
                            .font(Theme.sans(12)).foregroundStyle(Theme.muted)
                    }
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 0) {
                    Label2(t: "提醒时间轴").padding(.bottom, 12)
                    ForEach(Array(r.items.enumerated()), id: \.element.id) { i, item in
                        HStack(alignment: .top, spacing: 11) {
                            Rectangle()
                                .fill(item.improved ? Theme.accent : Theme.ink.opacity(0.22))
                                .frame(width: 8, height: 8)
                                .padding(.top, 5)
                            VStack(alignment: .leading, spacing: 3) {
                                HStack {
                                    Text(item.kind).font(Theme.sans(14)).foregroundStyle(Theme.ink)
                                    Spacer()
                                    // 未改善用中性灰，全套设计里没有一处红色
                                    Text(item.result)
                                        .font(Theme.sans(11, .medium))
                                        .foregroundStyle(item.improved ? Theme.accent : Theme.muted)
                                }
                                Text(item.when).font(Theme.mono(11)).foregroundStyle(Theme.muted)
                                Text(item.detail).font(Theme.sans(12)).foregroundStyle(Theme.muted)
                            }
                        }
                        .padding(.vertical, 9)
                        if i < r.items.count - 1 {
                            Rectangle().fill(Theme.line2).frame(height: 0.5)
                        }
                    }
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 12) {
                    Label2(t: "近 7 周响应率")
                    ThinBars(values: r.weekly, labels: r.weekLabels,
                             highlight: r.weekly.count - 1)
                }
            }

            Card {
                Text(r.note)
                    .font(Theme.sans(13)).foregroundStyle(Theme.ink).lineSpacing(5)
            }
        }
    }
}
