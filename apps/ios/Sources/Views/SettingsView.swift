import SwiftUI

/// 设置页用分组列表，不用卡片堆。
///
/// 原来的问题：八块奶油色块浮在近白底上，是全 App 黄色占比最高的一屏。
/// 「此刻」页也是卡片堆，但那些卡片每张有一个大数字当锚点，色块是在给数据
/// 做底；设置页卡片里全是「标题 + 副标题 + 控件」的行，行本身已经有分隔线
/// 做结构了，再包一层色块就是双重容器。
///
/// 现在：组标题放在卡片外面（浅底上），卡片只装行。八块合并成四组。
/// 说明性小字从九处砍到一处 —— 控件名起对了就不需要副标题。
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
                push()
            })
    }

    private func push() {
        let next = draft
        saving = true
        Task { await store.saveSettings(next); saving = false }
    }

    var body: some View {
        let s = draft
        Page(title: "设置", sub: "你们想怎么陪\(profile.displayName)学？") {

            group("学习目标") {
                stepRow("每日学习目标", "\(s.goalHours) 小时",
                        bind(\.goalHours), 1...12, 1)
                div()
                stepRow("最近距离", "\(s.distanceMin) mm",
                        bind(\.distanceMin), 250...600, 25)
                div()
                stepRow("最远距离", "\(s.distanceMax) mm",
                        bind(\.distanceMax), 600...1200, 25)
                div()
                plainRow("光线偏暗提醒", lightValue)
            }

            group("提醒与可见") {
                ForEach(Array(s.channels.enumerated()), id: \.element.id) { i, c in
                    toggleRow(c.label, Binding(
                        get: { draft.channels.indices.contains(i) ? draft.channels[i].on : false },
                        set: { v in
                            guard draft.channels.indices.contains(i),
                                  draft.channels[i].on != v else { return }
                            draft.channels[i].on = v
                            push()
                        }))
                    div()
                }
                toggleRow("孩子端显示学习数据", bind(\.childVisible))
            }
            // 这一屏唯一保留的说明文字 —— 它讲的是产品的态度，不是在解释控件
            note("孩子在设备上能看到自己的专注时长、护眼分和小羊状态。他有权知道设备记录了什么。")

            group("设备") {
                deviceRow
                div()
                plainRow("传感器校准", s.calibrated ? "已校准" : "未标定")
                div()
                NavigationLink { EnvView() }       label: { linkRow("环境详情") }
                div()
                NavigationLink { RemindersView() } label: { linkRow("提醒与响应") }
            }

            group("档案") {
                plainRow("孩子", profile.titleLine)
                div()
                Button { confirmReset = true } label: { linkRow("重设档案") }
            }
            .alert("重设档案？", isPresented: $confirmReset) {
                Button("取消", role: .cancel) {}
                Button("重设", role: .destructive) { profile.reset() }
            } message: {
                Text("会回到引导页重新填名字。设备连接不受影响，云端记录也还在。")
            }
        }
        .task { draft = store.settings }
        .onChange(of: store.settings) { _, new in syncDraft(new) }
    }

    // MARK: 组

    /// 组标题放在卡片外面，卡片只装行 —— 这样卡片更紧凑，也不用每组都留标题空间
    @ViewBuilder
    private func group<C: View>(_ title: String, @ViewBuilder rows: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label2(t: title).padding(.leading, 4)
            VStack(spacing: 0) { rows() }
                .padding(.horizontal, 16)
                .background(Theme.card)
                .clipShape(RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous))
        }
    }

    private func note(_ text: String) -> some View {
        Text(text)
            .font(Theme.sans(12.5)).foregroundStyle(Theme.muted)
            .lineSpacing(5)
            .padding(.horizontal, 4)
            .padding(.top, -4)
    }

    // MARK: 行

    private var lightValue: String {
        // 原来这里挂着一整行 11pt 小字在解释阈值，改成和上面三行一样右侧给值
        s(of: draft.lowLightHint)
    }
    private func s(of hint: String) -> String {
        // "低于 88% 判定偏暗，冷却 30 分钟" → "低于 88%"
        hint.components(separatedBy: "判定").first?
            .trimmingCharacters(in: .whitespaces) ?? hint
    }

    private func plainRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(Theme.sans(15)).foregroundStyle(Theme.ink)
            Spacer()
            Text(value).font(Theme.sans(15)).foregroundStyle(Theme.muted)
        }
        .frame(height: 52)
    }

    private func linkRow(_ label: String) -> some View {
        HStack {
            Text(label).font(Theme.sans(15)).foregroundStyle(Theme.ink)
            Spacer()
            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .medium)).foregroundStyle(Theme.muted)
        }
        .frame(height: 52)
        .contentShape(Rectangle())
    }

    private func toggleRow(_ label: String, _ on: Binding<Bool>) -> some View {
        HStack {
            Text(label).font(Theme.sans(15)).foregroundStyle(Theme.ink)
            Spacer()
            Toggle("", isOn: on).labelsHidden().tint(Theme.accent)
        }
        .frame(height: 52)
    }

    private func stepRow(_ label: String, _ value: String,
                         _ binding: Binding<Int>,
                         _ range: ClosedRange<Int>, _ step: Int) -> some View {
        HStack(spacing: 12) {
            Text(label).font(Theme.sans(15)).foregroundStyle(Theme.ink)
            Spacer(minLength: 8)
            Text(value).font(Theme.sans(15)).foregroundStyle(Theme.muted)
            stepper(binding, range, step)
        }
        .frame(height: 52)
    }

    /// 自绘加减，不用系统 Stepper —— 它的灰胶囊不属于这套色板里任何一个色，
    /// 三个并排像三块补丁。这里用页面底色做浅凹槽。
    private func stepper(_ v: Binding<Int>, _ range: ClosedRange<Int>, _ step: Int) -> some View {
        HStack(spacing: 0) {
            stepButton("minus", v.wrappedValue > range.lowerBound) {
                v.wrappedValue = max(range.lowerBound, v.wrappedValue - step)
            }
            Rectangle().fill(Theme.ink.opacity(0.10)).frame(width: 0.5, height: 16)
            stepButton("plus", v.wrappedValue < range.upperBound) {
                v.wrappedValue = min(range.upperBound, v.wrappedValue + step)
            }
        }
        .background(Theme.bg)
        .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
    }

    private func stepButton(_ icon: String, _ enabled: Bool, _ act: @escaping () -> Void) -> some View {
        Button(action: act) {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(enabled ? Theme.ink : Theme.ink.opacity(0.22))
                .frame(width: 38, height: 30)
                .contentShape(Rectangle())
        }
        .disabled(!enabled)
    }

    private var deviceRow: some View {
        let on = store.snapshot.link == .online
        return HStack {
            Text("书桌设备").font(Theme.sans(15)).foregroundStyle(Theme.ink)
            Spacer()
            HStack(spacing: 6) {
                Circle().fill(on ? Theme.accent : Theme.muted).frame(width: 6, height: 6)
                Text(on ? "在线 · \(store.snapshot.lastSync)"
                        : "离线 · \(store.snapshot.lastSync)")
                    .font(Theme.sans(15)).foregroundStyle(Theme.muted)
            }
        }
        .frame(height: 52)
    }

    private func syncDraft(_ new: Settings) {
        // 正在写的时候不要被服务端的旧值盖回来
        if !saving { draft = new }
    }
    private func div() -> some View { Rectangle().fill(Theme.line2).frame(height: 0.5) }
}
