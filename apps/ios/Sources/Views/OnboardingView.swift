import SwiftUI

/// 初始引导。小羊居中、文字在下、按钮在最下。
/// 底色用奶油色（和卡片同色）铺满整屏，和 App 内部形成层次差。
struct OnboardStep {
    var form: PetForm
    var title: String
    var body: String
}

let onboardSteps: [OnboardStep] = [
    .init(form: .normal,
          title: "这是小羊",
          body: "它住在孩子的书桌上。\n他坐下来学习的时候，小羊就醒着。"),
    .init(form: .lowLight,
          title: "它能感觉到光线",
          body: "台灯够不够亮、是不是只开了台灯没开顶灯，它都分得出来。\n光线不对，它会眯起眼睛。"),
    .init(form: .restBreak,
          title: "它会提醒，也会记住结果",
          body: "凑太近、坐太久，它出声提醒。\n更要紧的是，它记得提醒之后有没有真的改善。"),
    .init(form: .evolved,
          title: "你们看到的是同一只羊",
          body: "孩子在设备上看到的小羊，和你手机里这只是同一只。\n他知道你看到了什么 —— 这不是监控，是一起养它。"),
]

struct OnboardingView: View {
    @EnvironmentObject var store: Store
    @EnvironmentObject var profile: Profile
    @State private var page = 0
    @State private var name = ""
    @State private var grade = ""
    @State private var connecting = false
    @State private var connectError: String?
    @FocusState private var focus: Field?

    private enum Field { case name, grade }

    private var isLast: Bool { page == onboardSteps.count }

    var body: some View {
        ZStack {
            Theme.card.ignoresSafeArea()
            VStack(spacing: 0) {
                Spacer(minLength: 24)

                if isLast {
                    namePage
                } else {
                    stepPage(onboardSteps[page])
                }

                Spacer(minLength: 16)
                dots
                    .padding(.bottom, 22)
                buttons
                    .padding(.horizontal, 28)
                    .padding(.bottom, 26)
            }
        }
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("完成") { focus = nil }
                    .font(Theme.sans(15, .medium))
                    .foregroundStyle(Theme.accent)
            }
        }
    }

    // MARK: 引导步

    private func stepPage(_ s: OnboardStep) -> some View {
        VStack(spacing: 26) {
            Sheep(form: s.form, size: 178)
                .id(s.form)                       // 换页时重建，动画从头播
                .transition(.opacity)
            VStack(spacing: 13) {
                Text(s.title)
                    .font(Theme.serif(25))
                    .foregroundStyle(Theme.ink)
                    .multilineTextAlignment(.center)
                Text(s.body)
                    .font(Theme.sans(15))
                    .foregroundStyle(Theme.muted)
                    .multilineTextAlignment(.center)
                    .lineSpacing(7)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 34)
        }
    }

    // MARK: 建档 —— 只问一件因人而异的事

    private var namePage: some View {
        VStack(spacing: 24) {
            Sheep(form: .fed, size: 132)
            VStack(spacing: 11) {
                Text("它该叫谁的小羊？")
                    .font(Theme.serif(25)).foregroundStyle(Theme.ink)
                Text("设备已经绑好了，不用你填地址。\n填个名字，这只羊就归他了。")
                    .font(Theme.sans(15)).foregroundStyle(Theme.muted)
                    .multilineTextAlignment(.center).lineSpacing(6)
            }

            VStack(spacing: 10) {
                field("孩子的名字", placeholder: "小满", text: $name)
                    .focused($focus, equals: .name)
                    .submitLabel(.next)
                    .onSubmit { focus = .grade }
                field("年级（可不填）", placeholder: "二年级", text: $grade)
                    .focused($focus, equals: .grade)
                    .submitLabel(.done)
                    .onSubmit { submit() }
            }
            .padding(.horizontal, 28)
            .onAppear { focus = .name }

            if let e = connectError {
                Text(e).font(Theme.sans(12)).foregroundStyle(Theme.warn)
                    .multilineTextAlignment(.center).padding(.horizontal, 30)
            }
        }
    }

    private func field(_ label: String, placeholder: String,
                       text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(label).font(Theme.sans(11, .medium)).tracking(1.4)
                .foregroundStyle(Theme.muted)
            TextField(placeholder, text: text)
                .font(Theme.sans(15))
                .padding(.horizontal, 13).padding(.vertical, 12)
                .background(Theme.bg)
                .clipShape(RoundedRectangle(cornerRadius: Theme.ctlRadius))
        }
    }

    // MARK: 页码点 —— 用像素方块，呼应小羊

    private var dots: some View {
        HStack(spacing: 7) {
            ForEach(0...onboardSteps.count, id: \.self) { i in
                Rectangle()
                    .fill(i == page ? Theme.accent : Theme.ink.opacity(0.16))
                    .frame(width: i == page ? 18 : 7, height: 7)
            }
        }
        .animation(.easeInOut(duration: 0.22), value: page)
    }

    // MARK: 按钮

    private var buttons: some View {
        VStack(spacing: 11) {
            Button {
                if isLast { submit() } else {
                    withAnimation(.easeInOut(duration: 0.25)) { page += 1 }
                }
            } label: {
                HStack(spacing: 7) {
                    if connecting { ProgressView().tint(.white) }
                    Text(isLast ? (connecting ? "正在建档…" : "开始") : "下一步")
                }
                .font(Theme.sans(16, .medium))
                .frame(maxWidth: .infinity).padding(.vertical, 15)
            }
            .background(Theme.accent).foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: Theme.ctlRadius))
            .disabled(connecting)

            Button(isLast ? "以后再说" : "跳过") {
                profile.onboarded = true
            }
            .font(Theme.sans(14))
            .foregroundStyle(Theme.muted)
        }
    }

    private func submit() {
        connectError = nil
        let n = name.trimmingCharacters(in: .whitespaces)
        guard !n.isEmpty else {
            connectError = "给孩子起个名字吧"
            return
        }
        connecting = true
        Task {
            let err = await store.register(
                name: n, grade: grade.trimmingCharacters(in: .whitespaces))
            connecting = false
            if let err {
                connectError = "连不上后台：\(err)"
            } else {
                profile.name = n
                profile.grade = grade.trimmingCharacters(in: .whitespaces)
                profile.onboarded = true
            }
        }
    }
}
