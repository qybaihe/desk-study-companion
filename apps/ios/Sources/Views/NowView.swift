import SwiftUI

/// 首页把上半屏几乎整块让给小羊。
/// 四卡不等宽：专注（配目标环）最重，护眼分次之，环境和提问再降一级。
/// 这一屏的绿色只有三处：目标环、护眼分条、响应率格子。
struct NowView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var profile: Profile

    var body: some View {
        let s = store.snapshot
        ScrollView {
            VStack(alignment: .leading, spacing: 13) {
                header
                heroCard(s)
                focusCard(s)
                HStack(spacing: 12) {
                    eyeCard(s)
                    envCard(s)
                }
                HStack(spacing: 12) {
                    askCard(s)
                    reminderCard(s)
                }
                commentCard(s)
                NavigationLink { StudyView() } label: { RowLink(title: "学习详情") }
                NavigationLink { AskView() }   label: { RowLink(title: "提问") }
                Color.clear.frame(height: 22)      // Tab Bar 让位
            }
            .padding(16)
        }
        .background(Theme.bg)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var todayLine: String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "zh_CN")
        f.dateFormat = "M月d日 · EEEE"
        return f.string(from: Date())
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 3) {
                Text(todayLine).font(Theme.sans(12)).foregroundStyle(Theme.muted)
                Text(profile.titleLine).font(Theme.serif(21)).foregroundStyle(Theme.ink)
            }
            Spacer()
            HStack(spacing: 5) {
                Circle().fill(store.snapshot.link == .online ? Theme.accent : Theme.muted)
                    .frame(width: 6, height: 6)
                Text(store.snapshot.link == .online
                     ? "在线 · \(store.snapshot.lastSync) 同步" : "离线")
                    .font(Theme.sans(11)).foregroundStyle(Theme.muted)
            }
        }
    }

    private func heroCard(_ s: Snapshot) -> some View {
        Card(pad: 20) {
            VStack(spacing: 12) {
                Sheep(form: s.form, size: 150)
                Text(s.heroLine)
                    .font(Theme.serif(18)).foregroundStyle(Theme.ink)
                    .multilineTextAlignment(.center)
                Text(s.heroSub)
                    .font(Theme.sans(13)).foregroundStyle(Theme.muted)
                    .multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity)
        }
    }

    // 专注 —— 配目标环，四卡里最重的一张
    private func focusCard(_ s: Snapshot) -> some View {
        NavigationLink { StudyView() } label: {
            Card {
                HStack(spacing: 18) {
                    VStack(alignment: .leading, spacing: 6) {
                        Label2(t: "今日专注")
                        HStack(alignment: .firstTextBaseline, spacing: 4) {
                            Text("\(s.todayMinutes)").font(Theme.serif(38))
                            Text("分钟").font(Theme.sans(12)).foregroundStyle(Theme.muted)
                        }
                        .foregroundStyle(Theme.ink)
                        Text("目标 \(s.goalHours) 小时")
                            .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                    }
                    Spacer()
                    Ring(pct: s.goalPct, size: 72)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private func eyeCard(_ s: Snapshot) -> some View {
        NavigationLink { EyeView() } label: {
            Card(pad: 14) {
                VStack(alignment: .leading, spacing: 7) {
                    Label2(t: "护眼分")
                    Text("\(s.eyeScore)").font(Theme.serif(30)).foregroundStyle(Theme.ink)
                    PixelBar(value: Double(s.eyeScore) / 100, height: 7)
                    Text("扣 \(s.eyeDeducted) 分 · 可查明细")
                        .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private func envCard(_ s: Snapshot) -> some View {
        NavigationLink { EnvView() } label: {
            Card(pad: 14) {
                VStack(alignment: .leading, spacing: 7) {
                    Label2(t: "环境")
                    Text(s.comfortWord).font(Theme.serif(24)).foregroundStyle(Theme.ink)
                    Text(String(format: "%.1f°C · 湿度 %d%%", s.temperature, s.humidity))
                        .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                    Text("光线 \(s.lightWord)")
                        .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private func askCard(_ s: Snapshot) -> some View {
        NavigationLink { AskView() } label: {
            Card(pad: 14) {
                VStack(alignment: .leading, spacing: 7) {
                    Label2(t: "今日提问")
                    HStack(alignment: .firstTextBaseline, spacing: 3) {
                        Text("\(s.askCount)").font(Theme.serif(24))
                        Text("个").font(Theme.sans(11)).foregroundStyle(Theme.muted)
                    }
                    .foregroundStyle(Theme.ink)
                    Text(s.askNote).font(Theme.sans(11)).foregroundStyle(Theme.muted)
                }
            }
        }
        .buttonStyle(.plain)
    }

    // 响应率格子 —— 这一屏第三处绿
    private func reminderCard(_ s: Snapshot) -> some View {
        NavigationLink { RemindersView() } label: {
            Card(pad: 14) {
                VStack(alignment: .leading, spacing: 7) {
                    Label2(t: "今日提醒与响应")
                    Text("\(s.responseRate)%").font(Theme.serif(24)).foregroundStyle(Theme.accent)
                    Text("提醒 \(s.reminderCount) 次 · \(s.reminderImproved) 次他自己调整了")
                        .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .buttonStyle(.plain)
    }

    private func commentCard(_ s: Snapshot) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 8) {
                Label2(t: "今日速评")
                Text(s.todayComment)
                    .font(Theme.sans(14)).foregroundStyle(Theme.ink).lineSpacing(5)
            }
        }
    }
}
