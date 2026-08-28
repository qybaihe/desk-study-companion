import SwiftUI

private struct Bubble: Identifiable {
    let id = UUID(); let mine: Bool; let text: String; let chart: [Int]?
}

/// 小羊做 AI 头像 —— 它的身份和桌宠是同一个，家长问的是「那只羊」，
/// 不是一个客服机器人。回答里嵌 7 天小柱图，样式和图表页完全一致。
struct AskView: View {
    @EnvironmentObject var store: Store
    @State private var input = ""
    @State private var msgs: [Bubble] = [
        .init(mine: true, text: "今天效率怎么样？", chart: nil),
        .init(mine: false,
              text: "今天 52 分钟。最后这一轮 23 分钟，是今天最长的一段。19 点以后他比 18 点更坐得住——这两周都是这样。",
              chart: [64, 71, 46, 58, 39, 44, 52]),
        .init(mine: true, text: "台灯该怎么调？", chart: nil),
        .init(mine: false,
              text: "左右两路光敏差了 14 个百分点，右边一直偏暗。多半是只开了台灯、顶灯没开。把顶灯打开，或者把台灯往右挪一点。",
              chart: nil),
    ]
    private let presets = ["这周比上周好吗？", "他什么时候最容易坐不住？", "小羊为什么不舒服？"]

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(msgs) { m in
                        if m.mine {
                            HStack {
                                Spacer(minLength: 52)
                                Text(m.text)
                                    .font(Theme.sans(14)).foregroundStyle(Theme.ink).lineSpacing(4)
                                    .padding(12)
                                    .background(Theme.panel)
                                    .clipShape(RoundedRectangle(cornerRadius: 13))
                            }
                        } else {
                            HStack(alignment: .top, spacing: 9) {
                                Sheep(form: .normal, size: 30, animated: false)
                                VStack(alignment: .leading, spacing: 10) {
                                    Text(m.text)
                                        .font(Theme.sans(14)).foregroundStyle(Theme.ink).lineSpacing(5)
                                    if let c = m.chart {
                                        VStack(alignment: .leading, spacing: 7) {
                                            Label2(t: "近 7 天专注（分钟）")
                                            ThinBars(values: c,
                                                     labels: ["六","日","一","二","三","四","五"],
                                                     highlight: c.count - 1, height: 54)
                                        }
                                    }
                                }
                                .padding(13)
                                .background(Theme.card)
                                .clipShape(RoundedRectangle(cornerRadius: 13))
                                Spacer(minLength: 20)
                            }
                        }
                    }
                }
                .padding(16)
            }
            .background(Theme.bg)

            VStack(spacing: 9) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(presets, id: \.self) { p in
                            Button { send(p) } label: {
                                Text(p).font(Theme.sans(12))
                                    .padding(.horizontal, 12).padding(.vertical, 8)
                                    .background(Theme.card).foregroundStyle(Theme.ink)
                                    .clipShape(Capsule())
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                }
                HStack(spacing: 9) {
                    TextField("问点什么…", text: $input)
                        .textFieldStyle(.plain).font(Theme.sans(14))
                        .padding(.horizontal, 13).padding(.vertical, 11)
                        .background(Theme.panel)
                        .clipShape(RoundedRectangle(cornerRadius: Theme.ctlRadius))
                    Button { send(input) } label: {
                        Image(systemName: "arrow.up").font(.system(size: 14, weight: .semibold))
                            .padding(11).background(Theme.accent)
                            .foregroundStyle(.white).clipShape(Circle())
                    }
                    .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                .padding(.horizontal, 16)
            }
            .padding(.vertical, 11)
            .background(Theme.bg)
        }
        .navigationTitle("提问")
        .navigationBarTitleDisplayMode(.inline)
    }

    /// 真实实现：后端 → Agent Stack 的 POST /api/sessions/{id}/turns
    private func send(_ text: String) {
        let t = text.trimmingCharacters(in: .whitespaces)
        guard !t.isEmpty else { return }
        msgs.append(.init(mine: true, text: t, chart: nil))
        input = ""
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) {
            msgs.append(.init(mine: false,
                              text: "（待接入 Agent Stack）我会结合孩子自己的作息基线来回答，而不是套通用建议。",
                              chart: nil))
        }
    }
}
