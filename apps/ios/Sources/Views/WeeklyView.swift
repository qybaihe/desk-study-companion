import SwiftUI

/// 周报不套通用的 Page 版式 —— 它是一份刊物，不是又一屏仪表盘。
///
/// 原来的问题：三张奶油卡片浮在近白的底色上，卡与卡之间的白缝在这里读作
/// 断裂而不是节奏（「此刻」页卡多密度高，白缝才是网格）。所以封面改成
/// 通栏的一整块，正文直接落在页面底色上不再包卡片 —— 长文不需要框。
struct WeeklyView: View {
    @EnvironmentObject var store: Store
    @State private var showArchive = false

    private var w: WeeklyReport { store.weekly }
    private var idx: Int? { store.weeks.firstIndex { $0.key == w.weekKey } }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                cover
                VStack(alignment: .leading, spacing: 26) {
                    article
                    topics
                    archive
                    NavigationLink { RemindersView() } label: {
                        RowLink(title: "看本周 \(store.reminders.total) 次提醒分别怎么收场")
                    }
                }
                .padding(.horizontal, 20)
                .padding(.top, 28)
                Color.clear.frame(height: 30)
            }
        }
        .background(Theme.bg)
        .navigationBarTitleDisplayMode(.inline)
    }

    // MARK: 封面 —— 通栏铺满，不是卡片

    private var cover: some View {
        VStack(alignment: .leading, spacing: 0) {
            masthead
                .padding(.bottom, 20)

            Text(w.headline)
                .font(Theme.serif(27))
                .foregroundStyle(Theme.ink)
                .lineSpacing(8)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.bottom, 22)

            weekBars
                .padding(.bottom, 20)

            Rectangle().fill(Theme.ink.opacity(0.10)).frame(height: 0.5)
                .padding(.bottom, 16)

            scoreboard
        }
        .padding(.horizontal, 20)
        .padding(.top, 22)
        .padding(.bottom, 24)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            // 只把底色顶上去，正文位置不动。封面要压到状态栏后面才像封面。
            Theme.card.ignoresSafeArea(edges: .top)
        )
        .clipShape(.rect(bottomLeadingRadius: 28, bottomTrailingRadius: 28))
    }

    /// 刊头：报头字 + 期号 + 左右翻期
    private var masthead: some View {
        VStack(alignment: .leading, spacing: 9) {
            HStack {
                Text("SHEEPY WEEKLY")
                    .font(Theme.mono(10, .medium)).tracking(2.4)
                    .foregroundStyle(Theme.muted)
                Spacer()
                HStack(spacing: 2) {
                    pager("chevron.left", delta: 1)     // 往前一期 = 列表里更靠后
                    pager("chevron.right", delta: -1)
                }
            }
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(weekNumber)
                    .font(Theme.serif(34, .semibold)).foregroundStyle(Theme.ink)
                Text(dateRange)
                    .font(Theme.sans(13)).foregroundStyle(Theme.muted)
            }
        }
    }

    /// 「第 35 周 · 8月24–30日」拆成两段，期号要能当标题用
    private var weekNumber: String {
        w.weekLabel.components(separatedBy: " · ").first ?? w.weekLabel
    }
    private var dateRange: String {
        w.weekLabel.components(separatedBy: " · ").dropFirst().joined(separator: " · ")
    }

    private func pager(_ icon: String, delta: Int) -> some View {
        let target = idx.map { $0 + delta } ?? -1
        let ok = store.weeks.indices.contains(target)
        return Button {
            guard ok else { return }
            Task { await store.selectWeek(store.weeks[target].key) }
        } label: {
            Image(systemName: icon)
                .font(.system(size: 12, weight: .medium))
                .frame(width: 32, height: 28)
                .foregroundStyle(ok ? Theme.ink : Theme.ink.opacity(0.22))
        }
        .disabled(!ok)
    }

    // MARK: 七天

    private var weekBars: some View {
        let peak = max(w.days.map(\.minutes).max() ?? 1, 1)
        // 并列最高时只标第一根 —— 「这一周的重点」只能有一个，两根都绿就没有重点了
        let star = w.days.firstIndex { $0.minutes == peak && peak > 0 }
        let H: CGFloat = 66
        return HStack(alignment: .bottom, spacing: 0) {
            ForEach(Array(w.days.enumerated()), id: \.element.id) { i, d in
                VStack(spacing: 7) {
                    ZStack(alignment: .bottom) {
                        // 空的那天也要有底槽，否则一条细线浮在下面像分隔线
                        RoundedRectangle(cornerRadius: 4)
                            .fill(Theme.ink.opacity(0.05))
                            .frame(height: H)
                        RoundedRectangle(cornerRadius: 4)
                            .fill(i == star ? Theme.accent : Theme.ink.opacity(0.22))
                            .frame(height: d.minutes > 0
                                   ? max(6, H * CGFloat(d.minutes) / CGFloat(peak)) : 0)
                    }
                    .frame(width: 26)
                    Text(d.label)
                        .font(Theme.sans(10))
                        .foregroundStyle(i == star ? Theme.accent : Theme.muted)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .frame(height: 88, alignment: .bottom)
    }

    // MARK: 记分板 —— 三格，数字压场

    private var scoreboard: some View {
        HStack(alignment: .top, spacing: 0) {
            ForEach(Array(w.deltas.enumerated()), id: \.element.id) { i, d in
                VStack(alignment: .leading, spacing: 4) {
                    Text(d.label)
                        .font(Theme.sans(11)).foregroundStyle(Theme.muted)
                    Text(d.value)
                        .font(Theme.serif(26, .semibold)).foregroundStyle(Theme.ink)
                    deltaChip(d.delta)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if i < w.deltas.count - 1 {
                    Rectangle().fill(Theme.ink.opacity(0.08))
                        .frame(width: 0.5, height: 46)
                }
            }
        }
    }

    /// 涨用绿，跌用低饱和蓝 —— 全套设计里没有红色，跌不该被读成报错
    private func deltaChip(_ text: String) -> some View {
        let down = text.hasPrefix("−")
        let flat = !text.hasPrefix("+") && !down     // 「持平」「首周」都不画箭头
        return HStack(spacing: 2) {
            if !flat {
                Image(systemName: down ? "arrow.down" : "arrow.up")
                    .font(.system(size: 8, weight: .bold))
            }
            Text(flat ? text : String(text.dropFirst()))
                .font(Theme.sans(11, .medium))
        }
        .foregroundStyle(flat ? Theme.muted : (down ? Theme.sick : Theme.accent))
    }

    // MARK: 正文 —— 不包卡片，字号提到 16

    private var article: some View {
        VStack(alignment: .leading, spacing: 17) {
            ForEach(Array(w.paragraphs.enumerated()), id: \.offset) { _, p in
                Text(p)
                    .font(Theme.sans(16))
                    .foregroundStyle(Theme.ink)
                    .lineSpacing(9)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 7) {
                Rectangle().fill(Theme.accent).frame(width: 14, height: 1.5)
                Text("由本周传感器数据自动生成")
                    .font(Theme.sans(11)).foregroundStyle(Theme.muted)
            }
            .padding(.top, 3)
        }
    }

    // MARK: 问题类型

    @ViewBuilder private var topics: some View {
        Card(pad: 18) {
            VStack(alignment: .leading, spacing: 13) {
                Label2(t: w.topics.isEmpty ? "问题类型"
                                           : "问题类型 TOP 3 · 共 \(w.topicTotal) 个")
                if w.topics.isEmpty {
                    // 这一周没人问过。空着比编三条出来诚实。
                    Text("这一周没有提问记录。")
                        .font(Theme.sans(14)).foregroundStyle(Theme.muted)
                        .padding(.vertical, 4)
                }
                ForEach(Array(w.topics.enumerated()), id: \.element.id) { i, t in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(t.name).font(Theme.sans(14)).foregroundStyle(Theme.ink)
                            Spacer()
                            Text("\(t.count)").font(Theme.sans(13, .medium)).foregroundStyle(Theme.muted)
                        }
                        GeometryReader { g in
                            // 灰条读起来像禁用态，改成强调色的浓淡阶梯
                            RoundedRectangle(cornerRadius: 2)
                                .fill(Theme.accent.opacity(1.0 - Double(i) * 0.28))
                                .frame(width: g.size.width * CGFloat(t.count)
                                       / CGFloat(max(w.topicTotal, 1)))
                        }
                        .frame(height: 5)
                    }
                }
            }
        }
    }

    // MARK: 往期

    private var archive: some View {
        VStack(alignment: .leading, spacing: 11) {
            Label2(t: "往期周报")
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 9) {
                    ForEach(store.weeks) { ref in
                        let on = ref.key == w.weekKey
                        Button {
                            Task { await store.selectWeek(ref.key) }
                        } label: {
                            VStack(alignment: .leading, spacing: 5) {
                                Text(ref.label)
                                    .font(Theme.serif(16, .semibold))
                                Text(ref.range)
                                    .font(Theme.sans(11))
                                Text("\(ref.minutes / 60) 小时 \(ref.minutes % 60) 分")
                                    .font(Theme.sans(11))
                                    .padding(.top, 1)
                            }
                            .foregroundStyle(on ? .white : Theme.ink)
                            .frame(width: 104, alignment: .leading)
                            .padding(.vertical, 12).padding(.horizontal, 13)
                            .background(on ? Theme.accent : Theme.card)
                            .clipShape(RoundedRectangle(cornerRadius: 13, style: .continuous))
                        }
                    }
                }
                .padding(.horizontal, 20)
            }
            .padding(.horizontal, -20)        // 卡片贴着屏幕边缘滚出去
        }
    }
}
