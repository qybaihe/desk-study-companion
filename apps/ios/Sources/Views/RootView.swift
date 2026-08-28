import SwiftUI

/// 底部导航四项：此刻 / 小羊 / 周报 / 设置
/// 护眼、学习、提问、环境详情、提醒与响应都是二级页面
///
/// 图标是定制的像素图，落在 25x25 格上（1 格 = 1pt，@2x/@3x 都是整数倍）。
/// 它们是模板图：只有 alpha 会保留，选中时系统填 .tint 的主题绿，未选中填灰。
/// 生成流程见 tooling/asset_builders/make_tab_icons.py
struct RootView: View {
    @EnvironmentObject var store: Store
    var body: some View {
        TabView {
            NavigationStack { NowView() }
                .tabItem { Label("此刻", image: "tabNow") }
            NavigationStack { PetView() }
                .tabItem { Label("小羊", image: "tabPet") }
            NavigationStack { WeeklyView() }
                .tabItem { Label("周报", image: "tabWeekly") }
            NavigationStack { SettingsView() }
                .tabItem { Label("设置", image: "tabSettings") }
        }
        .tint(Theme.accent)
    }
}
