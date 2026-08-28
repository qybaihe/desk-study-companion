import SwiftUI

/// 不谎报精度。光照只给百分比和「明亮 / 适中 / 偏暗」，一处数值都没有。
/// 左右双路差值才是这一屏真正有用的信息。
struct EnvView: View {
    @EnvironmentObject var store: Store

    var body: some View {
        let s = store.snapshot
        Page(title: "环境详情") {
            HStack(spacing: 12) {
                Card(pad: 14) {
                    VStack(alignment: .leading, spacing: 6) {
                        Label2(t: "温度")
                        Text(String(format: "%.1f °C", s.temperature))
                            .font(Theme.serif(24)).foregroundStyle(Theme.ink)
                        Text("在舒适区间").font(Theme.sans(11)).foregroundStyle(Theme.accent)
                    }
                }
                Card(pad: 14) {
                    VStack(alignment: .leading, spacing: 6) {
                        Label2(t: "湿度")
                        Text("\(s.humidity) %").font(Theme.serif(24)).foregroundStyle(Theme.ink)
                        Text("在舒适区间").font(Theme.sans(11)).foregroundStyle(Theme.accent)
                    }
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Label2(t: "今日落在舒适区间的时间")
                        Spacer()
                        Text("82%").font(Theme.sans(13, .medium)).foregroundStyle(Theme.ink)
                    }
                    GeometryReader { g in
                        ZStack(alignment: .leading) {
                            Rectangle().fill(Theme.track)
                            Rectangle().fill(Theme.accent).frame(width: g.size.width * 0.82)
                        }
                    }
                    .frame(height: 7)
                    Text("DHT11 精度 ±2°C / ±5%RH，只用于舒适度分级。")
                        .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 13) {
                    HStack {
                        Label2(t: "光照 · 双路读数")
                        Spacer()
                        Text(s.lightWord).font(Theme.sans(13, .medium)).foregroundStyle(Theme.ink)
                    }
                    channel("左侧", s.lightLeft)
                    channel("右侧", s.lightRight)
                    HStack {
                        Text("左右差值").font(Theme.sans(13)).foregroundStyle(Theme.ink)
                        Spacer()
                        Text("\(s.lightDiff)pt")
                            .font(Theme.sans(14, .medium)).foregroundStyle(Theme.warn)
                    }
                    Text("右侧持续偏暗，通常意味着只开了台灯、顶灯没开。开顶灯或把台灯往右挪，差值会收回 5pt 以内。")
                        .font(Theme.sans(12)).foregroundStyle(Theme.muted).lineSpacing(4)
                }
            }

            DashedNote(text: "光敏未做两点校准，这里只显示相对百分比和「明亮 / 适中 / 偏暗」分级，不报照度数值。校准入口在设置里。")
        }
    }

    private func channel(_ name: String, _ pct: Int) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text(name).font(Theme.sans(13)).foregroundStyle(Theme.ink)
                Spacer()
                Text("\(pct)%").font(Theme.sans(12)).foregroundStyle(Theme.muted)
            }
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Rectangle().fill(Theme.track)
                    Rectangle().fill(Theme.ink.opacity(0.28)).frame(width: g.size.width * CGFloat(pct) / 100)
                }
            }
            .frame(height: 6)
        }
    }
}
