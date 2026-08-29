import SwiftUI

@main
struct SheepyApp: App {
    @StateObject private var store = Store()
    @StateObject private var profile = Profile()

    var body: some Scene {
        WindowGroup {
            AppEntry()
                .environmentObject(store)
                .environmentObject(profile)
                .task {
                    // 后端是固定的（见 Backend.swift），不需要任何连接步骤
                    await store.refresh()
                    store.startPolling()
                }
        }
    }
}


/// 首次启动先走引导，之后直接进主界面。
///
/// 主界面在拿到真实数据之前不放出来 —— @Published 的初值是 MockData 里的
/// 演示数字，直接摆出来等于给家长看编造的值。有本地缓存就不会经过这一步。
struct AppEntry: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var profile: Profile

    var body: some View {
        if !profile.onboarded {
            OnboardingView()
        } else {
            switch store.load {
            case .ready:            RootView()
            case .loading:          LoadingView()
            case .failed(let msg):  FailedView(message: msg)
            }
        }
    }
}


/// 首次加载。和引导页同一套底色，不做转圈之外的花样。
struct LoadingView: View {
    var body: some View {
        ZStack {
            Theme.card.ignoresSafeArea()
            VStack(spacing: 22) {
                Sheep(form: .normal, size: 132)
                Text("正在同步…")
                    .font(Theme.sans(15)).foregroundStyle(Theme.muted)
            }
        }
    }
}


/// 第一次就没连上。宁可显示连不上，也不显示假数字。
struct FailedView: View {
    @EnvironmentObject var store: Store
    let message: String
    @State private var retrying = false

    var body: some View {
        ZStack {
            Theme.card.ignoresSafeArea()
            VStack(spacing: 16) {
                Sheep(form: .sick, size: 128)
                Text("连不上后台")
                    .font(Theme.serif(22)).foregroundStyle(Theme.ink)
                Text(message)
                    .font(Theme.sans(13)).foregroundStyle(Theme.muted)
                    .multilineTextAlignment(.center).lineSpacing(5)
                    .padding(.horizontal, 46)
                Button {
                    retrying = true
                    Task { await store.retry(); retrying = false }
                } label: {
                    Text(retrying ? "重试中…" : "重试")
                        .font(Theme.sans(16, .medium))
                        .frame(maxWidth: .infinity).padding(.vertical, 15)
                }
                .background(Theme.accent).foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: Theme.ctlRadius))
                .disabled(retrying)
                .padding(.horizontal, 44).padding(.top, 6)
            }
        }
    }
}
