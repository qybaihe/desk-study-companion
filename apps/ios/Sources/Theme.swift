import SwiftUI

/// 设计系统。色值逐一取自 Banxue Parent App.dc.html 的 :root / [data-theme="dark"]。
enum Theme {
    private static func dyn(_ l: UInt32, _ d: UInt32) -> Color {
        Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(hex: d) : UIColor(hex: l) })
    }
    static let bg     = dyn(0xF8F8F8, 0x1C1A17)
    static let panel  = dyn(0xF0F0E8, 0x26241F)
    static let card   = dyn(0xF0E8D8, 0x302D26)
    static let ink    = dyn(0x262421, 0xEDE9E0)
    static let muted  = dyn(0x8C867C, 0x9A948A)
    static let accent = dyn(0x6B8F71, 0x8FB395)   // 鼠尾草绿 · 唯一强调色，占比 ≤5%
    static let warn   = dyn(0xC9A227, 0xD4B455)   // 注意 · 芥末黄（偏近用它，不用红）
    static let sick   = dyn(0x6E86A6, 0x8AA2C0)   // 异常 / SICK · 低饱和蓝。全套设计无红色
    static let blush  = dyn(0xF8B0B8, 0xF0A8B4)
    static let shell  = dyn(0xEAE8E1, 0x131210)

    static var line:  Color { ink.opacity(0.11) }
    static var line2: Color { ink.opacity(0.06) }
    static var track: Color { ink.opacity(0.08) }

    static let cardRadius: CGFloat = 16
    static let ctlRadius: CGFloat = 10

    /// 大标题用衬线（设计稿是 Noto Serif SC）
    static func serif(_ size: CGFloat, _ weight: Font.Weight = .medium) -> Font {
        .system(size: size, weight: weight, design: .serif)
    }
    static func sans(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight)
    }
    static func mono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
}

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(red:   CGFloat((hex >> 16) & 0xFF) / 255,
                  green: CGFloat((hex >> 8) & 0xFF) / 255,
                  blue:  CGFloat(hex & 0xFF) / 255, alpha: 1)
    }
}
