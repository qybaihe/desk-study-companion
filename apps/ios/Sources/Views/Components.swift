import SwiftUI

struct Card<C: View>: View {
    var pad: CGFloat = 16
    var fill: Color = Theme.card
    @ViewBuilder var content: C
    var body: some View {
        content
            .padding(pad)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(fill)
            .clipShape(RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous))
    }
}

struct Label2: View {
    let t: String
    var body: some View {
        Text(t).font(Theme.sans(11, .medium)).tracking(1.6).foregroundStyle(Theme.muted)
    }
}

/// 分格像素条 —— 像素语言唯一进入数据显示的地方，因为它属于小羊。
/// 图表页一律不用。
struct PixelBar: View {
    var value: Double
    var tint: Color = Theme.accent
    var height: CGFloat = 10
    private let cell: CGFloat = 7

    var body: some View {
        GeometryReader { g in
            let n = max(1, Int(g.size.width / cell))
            let f = Int((Double(n) * min(max(value, 0), 1)).rounded())
            HStack(spacing: 2) {
                ForEach(0..<n, id: \.self) { i in
                    Rectangle().fill(i < f ? tint : Theme.track).frame(width: cell - 2)
                }
            }
        }
        .frame(height: height)
    }
}

/// 小羊。有动画帧的状态逐帧播放，没有的用 2048 母版静态显示。
/// 帧已按 6 倍最近邻预放大，所以这里用默认插值即可（再用 .none 会因非整数倍缩放而块大小不匀）。
struct Sheep: View {
    var form: PetForm
    var size: CGFloat = 148
    var animated = true

    var body: some View {
        if animated, let a = form.animation {
            TimelineView(.periodic(from: .now, by: 1.0 / a.fps)) { ctx in
                let t = ctx.date.timeIntervalSinceReferenceDate
                let i = Int(t * a.fps) % a.count
                Image("\(a.prefix)\(i)")
                    .resizable().scaledToFit()
                    .frame(width: size, height: size)
            }
        } else {
            Image(form.asset)
                .resizable().scaledToFit()
                .frame(width: size, height: size)
        }
    }
}

/// 细柱图 —— 数据图表保持干净现代，无圆角，只有"今天"一根上强调色
struct ThinBars: View {
    var values: [Int]
    var labels: [String] = []
    var highlight: Int? = nil
    var height: CGFloat = 92

    var body: some View {
        let mx = max(values.max() ?? 1, 1)
        VStack(spacing: 6) {
            HStack(alignment: .bottom, spacing: 8) {
                ForEach(Array(values.enumerated()), id: \.offset) { i, v in
                    Rectangle()
                        .fill(i == highlight ? Theme.accent : Theme.ink.opacity(0.18))
                        .frame(height: max(3, height * CGFloat(v) / CGFloat(mx)))
                        .frame(maxWidth: .infinity)
                }
            }
            .frame(height: height, alignment: .bottom)
            if !labels.isEmpty {
                HStack(spacing: 8) {
                    ForEach(labels, id: \.self) {
                        Text($0).font(Theme.sans(10)).foregroundStyle(Theme.muted)
                            .frame(maxWidth: .infinity)
                    }
                }
            }
        }
    }
}

struct Ring: View {
    var pct: Int
    var size: CGFloat = 64
    var body: some View {
        ZStack {
            Circle().stroke(Theme.track, lineWidth: 7)
            Circle().trim(from: 0, to: Double(pct) / 100)
                .stroke(Theme.accent, style: .init(lineWidth: 7, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text("\(pct)%").font(Theme.sans(13, .medium)).foregroundStyle(Theme.ink)
        }
        .frame(width: size, height: size)
    }
}

/// 虚线框 —— 用于"孩子在设备上看到的是同一只羊"这类独立声明
struct DashedNote: View {
    let text: String
    var body: some View {
        Text(text)
            .font(Theme.sans(12))
            .foregroundStyle(Theme.muted)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 11)
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(style: StrokeStyle(lineWidth: 1, dash: [4, 4]))
                    .foregroundStyle(Theme.line)
            )
    }
}

struct RowLink: View {
    var title: String
    var body: some View {
        HStack {
            Text(title).font(Theme.sans(15)).foregroundStyle(Theme.ink)
            Spacer()
            Image(systemName: "chevron.right").font(.system(size: 12)).foregroundStyle(Theme.muted)
        }
        .padding(.vertical, 13).padding(.horizontal, 16)
        .background(Theme.card)
        .clipShape(RoundedRectangle(cornerRadius: Theme.cardRadius, style: .continuous))
    }
}

struct Page<C: View>: View {
    var title: String
    var sub: String? = nil
    @ViewBuilder var content: C
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 13) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(title).font(Theme.serif(25)).foregroundStyle(Theme.ink)
                    if let sub { Text(sub).font(Theme.sans(12)).foregroundStyle(Theme.muted) }
                }
                .padding(.bottom, 2)
                content
                Color.clear.frame(height: 22)      // Tab Bar 让位
            }
            .padding(16)
        }
        .background(Theme.bg)
    }
}
