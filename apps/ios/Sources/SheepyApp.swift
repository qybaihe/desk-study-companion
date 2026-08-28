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


/// 首次启动先走引导，之后直接进主界面
struct AppEntry: View {
    @EnvironmentObject var profile: Profile
    var body: some View {
        if profile.onboarded { RootView() } else { OnboardingView() }
    }
}
