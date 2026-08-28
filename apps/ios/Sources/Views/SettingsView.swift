import SwiftUI

/// 把知情权放在设置的中间位置：「孩子端可见内容」用奶油卡片单独抬出来。
/// 设备离线时不假装有数据。
struct SettingsView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var profile: Profile
    @State private var confirmReset = false
    /// 本地草稿。轮询每 10 秒会覆盖 store.settings，正在写的时候不能让
    /// 开关被服务端的旧值弹回去。
    @State private var draft = Mock.settings
    @State private var saving = false

    /// 改一项就写回一次 device_config，Worker 把 rev +1，板子下次联系时生效。
    private func bind<V: Equatable>(_ key: WritableKeyPath<Settings, V>) -> Binding<V> {
        Binding(
            get: { draft[keyPath: key] },
            set: { v in
                guard draft[keyPath: key] != v else { return }
                draft[keyPath: key] = v
                let next = draft
                saving = true
                Task {
                    await store.saveSettings(next)
                    saving = false
                }
            })
    }

    var body: some View {
        let s = draft
        Page(title: "设置", sub: "你们想怎么陪\(profile.displayName)学？") {
            Card {
                VStack(spacing: 0) {
                    Stepper(value: bind(\.goalHours), in: 1...12) {
                        HStack {
                            Text("每日学习目标").font(Theme.sans(14)).foregroundStyle(Theme.ink)
                            Spacer()
                            Text("\(s.goalHours) 小时").font(Theme.sans(14)).foregroundStyle(Theme.muted)
                        }
                    }
                    .padding(.vertical, 6)
                    div()
                    Stepper(value: bind(\.distanceMin), in: 250...600, step: 25) {
                        HStack {
                            Text("最近距离").font(Theme.sans(14)).foregroundStyle(Theme.ink)
                            Spacer()
                            Text("\(s.distanceMin) mm").font(Theme.sans(14)).foregroundStyle(Theme.muted)
                        }
                    }
                    .padding(.vertical, 6)
                    div()
                    Stepper(value: bind(\.distanceMax), in: 600...1200, step: 25) {
                        HStack {
                            Text("最远距离").font(Theme.sans(14)).foregroundStyle(Theme.ink)
                            Spacer()
                            Text("\(s.distanceMax) mm").font(Theme.sans(14)).foregroundStyle(Theme.muted)
                        }
                    }
                    .padding(.vertical, 6)
                    div()
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("光线偏暗提醒").font(Theme.sans(14)).foregroundStyle(Theme.ink)
                            Spacer()
                        }
                        Text(s.lowLightHint).font(Theme.sans(11)).foregroundStyle(Theme.muted)
                    }
                    .padding(.vertical, 12)
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 0) {
                    Label2(t: "提醒方式").padding(.bottom, 10)
                    ForEach(Array(s.channels.enumerated()), id: \.element.id) { i, c in
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(c.label).font(Theme.sans(14)).foregroundStyle(Theme.ink)
                                Text(c.hint).font(Theme.sans(11)).foregroundStyle(Theme.muted)
                            }
                            Spacer()
                            Toggle("", isOn: Binding(
                                get: { draft.channels[i].on },
                                set: { v in
                                    guard draft.channels[i].on != v else { return }
                                    draft.channels[i].on = v
                                    let next = draft
                                    saving = true
                                    Task { await store.saveSettings(next); saving = false }
                                })).labelsHidden().tint(Theme.accent)
                        }
                        .padding(.vertical, 9)
                    }
                }
            }

            // 知情权 —— 单独抬出来
            Card {
                VStack(alignment: .leading, spacing: 9) {
                    HStack {
                        Text("孩子端可见内容").font(Theme.sans(15, .medium)).foregroundStyle(Theme.ink)
                        Spacer()
                        Toggle("", isOn: bind(\.childVisible)).labelsHidden().tint(Theme.accent)
                    }
                    Text("开启后，\(profile.displayName)在设备上能看到自己的专注时长、护眼分和小羊状态。他有权知道设备记录了什么。")
                        .font(Theme.sans(12)).foregroundStyle(Theme.muted).lineSpacing(4)
                }
            }

            Card {
                VStack(alignment: .leading, spacing: 0) {
                    Label2(t: "设备").padding(.bottom, 10)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(s.deviceName).font(Theme.sans(14)).foregroundStyle(Theme.ink)
                        HStack(spacing: 6) {
                            Circle().fill(store.snapshot.link == .online ? Theme.accent : Theme.muted)
                                .frame(width: 6, height: 6)
                            Text(store.snapshot.link == .online
                                 ? "在线 · \(store.snapshot.lastSync) 同步 · 固件 \(s.firmware)"
                                 : "离线 · 最后同步 \(store.snapshot.lastSync) · 固件 \(s.firmware)")
                                .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                        }
                    }
                    .padding(.vertical, 10)
                    div()
                    VStack(alignment: .leading, spacing: 4) {
                        Text("传感器校准").font(Theme.sans(14)).foregroundStyle(Theme.ink)
                        Text(s.calibrated ? "已校准" : "光敏未标定 · 校准后才能显示照度数值")
                            .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                    }
                    .padding(.vertical, 10)
                }
            }

            NavigationLink { EnvView() }       label: { RowLink(title: "环境详情") }
            NavigationLink { RemindersView() } label: { RowLink(title: "提醒与响应") }

            Card {
                VStack(alignment: .leading, spacing: 0) {
                    Label2(t: "档案").padding(.bottom, 10)
                    row("孩子", profile.titleLine)
                    div()
                    Button { confirmReset = true } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("重设").font(Theme.sans(14)).foregroundStyle(Theme.sick)
                                Text("回到引导页重新建档。设备连接不受影响，云端记录也还在。")
                                    .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                                    .multilineTextAlignment(.leading).lineSpacing(3)
                            }
                            Spacer()
                        }
                        .padding(.vertical, 12)
                    }
                }
            }
            .alert("重设档案？", isPresented: $confirmReset) {
                Button("取消", role: .cancel) {}
                Button("重设", role: .destructive) { profile.reset() }
            } message: {
                Text("会回到引导页重新填名字。设备和云端的数据不会删除。")
            }
        }
        .task { draft = store.settings }
        .onChange(of: store.settings) { _, new in syncDraft(new) }
    }

    private func syncDraft(_ new: Settings) {
        // 正在写的时候不要被服务端的旧值盖回来
        if !saving { draft = new }
    }

    private func row(_ l: String, _ v: String) -> some View {
        HStack {
            Text(l).font(Theme.sans(14)).foregroundStyle(Theme.ink)
            Spacer()
            Text(v).font(Theme.sans(14)).foregroundStyle(Theme.muted)
        }
        .padding(.vertical, 12)
    }
    private func div() -> some View { Rectangle().fill(Theme.line2).frame(height: 0.5) }
}
