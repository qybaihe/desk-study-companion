import SwiftUI

/// 情感温度最高的一屏。日记做成手账版式：时间戳出挑、短句、发丝线分隔，
/// 不做成数据卡片 —— 这是全 App 唯一不谈指标的地方。
struct PetView: View {
    @EnvironmentObject var store: Store
    @State private var sending = false
    @State private var sent: String?     // 刚送出的那一个，用来给按钮一个回执

    /// 动作排进云端队列，板子最多 20 秒后取走并在 LCD 上演出来。
    /// 体力/成长会跟着变，下一次上报就同步回这里 —— 不在本地假装。
    private func send(_ kind: String) {
        guard !sending else { return }
        sending = true
        Task {
            let ok = await store.sendAction(kind)
            sending = false
            if ok {
                sent = kind
                try? await Task.sleep(nanoseconds: 2_500_000_000)
                if sent == kind { sent = nil }
            }
        }
    }
    @State private var poke = false

    var body: some View {
        let s = store.snapshot
        Page(title: "小羊", sub: s.form.label) {
            Card(pad: 20) {
                VStack(spacing: 10) {
                    Sheep(form: s.form, size: 156)
                        .scaleEffect(poke ? 1.1 : 1)
                        .animation(.spring(response: 0.26, dampingFraction: 0.4), value: poke)
                        .onTapGesture {
                            poke = true
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.28) { poke = false }
                        }
                    Text("点一下小羊，它会跳一下")
                        .font(Theme.sans(12)).foregroundStyle(Theme.muted)
                }
                .frame(maxWidth: .infinity)
            }

            // HP 和成长值用分格像素条
            Card {
                VStack(alignment: .leading, spacing: 15) {
                    VStack(alignment: .leading, spacing: 7) {
                        HStack {
                            Label2(t: "体力 HP")
                            Spacer()
                            Text("\(s.hp)").font(Theme.sans(13, .medium))
                                .foregroundStyle(s.hp < 30 ? Theme.sick : Theme.ink)
                        }
                        PixelBar(value: Double(s.hp) / 100,
                                 tint: s.hp < 30 ? Theme.sick : Theme.accent)
                    }
                    VStack(alignment: .leading, spacing: 7) {
                        HStack {
                            Label2(t: "成长值 GROW")
                            Spacer()
                            Text("\(s.grow) / \(s.growTarget) 开花")
                                .font(Theme.sans(12)).foregroundStyle(Theme.muted)
                        }
                        PixelBar(value: Double(s.grow) / Double(s.growTarget), tint: Theme.blush)
                        Text("还差 \(max(0, s.growTarget - s.grow)) 点开花")
                            .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                    }
                }
            }

            // 小羊日记 · 手账版式
            Card {
                VStack(alignment: .leading, spacing: 0) {
                    HStack {
                        Label2(t: "小羊日记")
                        Spacer()
                        Text("8 / 28").font(Theme.mono(11)).foregroundStyle(Theme.muted)
                    }
                    .padding(.bottom, 12)

                    ForEach(Array(store.diary.enumerated()), id: \.element.id) { i, d in
                        HStack(alignment: .top, spacing: 12) {
                            Text(d.time)
                                .font(Theme.mono(12, .medium))
                                .foregroundStyle(d.time == "现在" ? Theme.accent : Theme.muted)
                                .frame(width: 46, alignment: .leading)
                            Text(d.text)
                                .font(Theme.serif(14))
                                .foregroundStyle(Theme.ink)
                                .lineSpacing(3)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(.vertical, 9)
                        if i < store.diary.count - 1 {
                            Rectangle().fill(Theme.line2).frame(height: 0.5)   // 发丝线
                        }
                    }
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 12) {
                    Label2(t: "成长里程碑")
                    ForEach(store.milestones) { m in
                        HStack(spacing: 11) {
                            // 像素里程碑图标
                            Rectangle()
                                .fill(m.reached ? Theme.accent : Theme.track)
                                .frame(width: 9, height: 9)
                            Text(m.title)
                                .font(Theme.sans(14))
                                .foregroundStyle(m.reached ? Theme.ink : Theme.muted)
                            Spacer()
                            Text(m.date).font(Theme.sans(11)).foregroundStyle(Theme.muted)
                        }
                    }
                }
            }

            HStack(spacing: 11) {
                Button { send("feed") } label: {
                    Text(sent == "feed" ? "喂过了" : "喂一把草")
                        .frame(maxWidth: .infinity).padding(.vertical, 13)
                }
                .background(Theme.accent).foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: Theme.ctlRadius))

                Button { send("reward") } label: {
                    Text(sent == "reward" ? "已送出" : "送个奖励")
                        .frame(maxWidth: .infinity).padding(.vertical, 13)
                }
                .background(Theme.panel).foregroundStyle(Theme.ink)
                .clipShape(RoundedRectangle(cornerRadius: Theme.ctlRadius))
            }
            .font(Theme.sans(15, .medium))
            .disabled(sending)

            // 把监控翻转成共育的支点，给它独立一行虚线框
            DashedNote(text: "孩子在设备上看到的是同一只羊")
        }
    }
}
