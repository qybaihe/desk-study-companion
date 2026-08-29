import UIKit

/// 把一句中文渲染成 OLED 能直接显示的 128×64 单色位图。
///
/// 板子那块 OLED 用的是 framebuf 内置的 8×8 ASCII 字库，画不了中文。与其往
/// 128KB 的固件里塞一套中文字库，不如让有字体的这一端（手机）把字排好版、
/// 画成位图传下去 —— 板子只负责 blit，一个字库都不用带。
enum OLEDBitmap {
    static let width = 128
    static let height = 64

    /// 返回 MicroPython framebuf 的 MONO_VLSB 字节序：
    /// 每字节纵向 8 个像素，低位在上；索引 = page * width + x。
    static func render(_ text: String) -> Data? {
        guard let gray = rasterize(text) else { return nil }

        var out = Data(count: width * height / 8)
        out.withUnsafeMutableBytes { buf in
            let p = buf.bindMemory(to: UInt8.self)
            for y in 0..<height {
                for x in 0..<width {
                    // rasterize 出来的是白底黑字，OLED 是黑底亮字，所以取反
                    guard gray[y * width + x] < 128 else { continue }
                    p[(y / 8) * width + x] |= UInt8(1 << (y % 8))
                }
            }
        }
        return out
    }

    /// 画成 8 位灰度。字号从大往小试，直到整句能塞进 128×64。
    private static func rasterize(_ text: String) -> [UInt8]? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }

        var chosen: (font: UIFont, rect: CGRect)?
        for size in [17, 15, 13, 11, 9] as [CGFloat] {
            let f = UIFont.systemFont(ofSize: size, weight: .medium)
            let para = NSMutableParagraphStyle()
            para.alignment = .center
            para.lineBreakMode = .byCharWrapping
            para.lineSpacing = 1
            let r = (trimmed as NSString).boundingRect(
                with: CGSize(width: CGFloat(width) - 4, height: .greatestFiniteMagnitude),
                options: [.usesLineFragmentOrigin, .usesFontLeading],
                attributes: [.font: f, .paragraphStyle: para], context: nil)
            if r.height <= CGFloat(height) - 4 {
                chosen = (f, r); break
            }
        }
        // 最小字号还是放不下就截断，宁可少几个字也不要糊成一片
        let font = chosen?.font ?? UIFont.systemFont(ofSize: 9, weight: .medium)
        let body = chosen != nil ? trimmed : String(trimmed.prefix(40)) + "…"

        let cs = CGColorSpaceCreateDeviceGray()
        guard let ctx = CGContext(data: nil, width: width, height: height,
                                  bitsPerComponent: 8, bytesPerRow: width,
                                  space: cs, bitmapInfo: CGImageAlphaInfo.none.rawValue)
        else { return nil }
        ctx.setFillColor(gray: 1, alpha: 1)                 // 白底
        ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))

        let para = NSMutableParagraphStyle()
        para.alignment = .center
        // 必须和上面测量时用的一致，否则量出来能放下、画出来却截断成一行
        para.lineBreakMode = .byCharWrapping
        para.lineSpacing = 1
        let attrs: [NSAttributedString.Key: Any] = [
            .font: font, .paragraphStyle: para, .foregroundColor: UIColor.black,
        ]
        let measured = (body as NSString).boundingRect(
            with: CGSize(width: CGFloat(width) - 4, height: CGFloat(height) - 2),
            options: [.usesLineFragmentOrigin, .usesFontLeading],
            attributes: attrs, context: nil)

        UIGraphicsPushContext(ctx)
        ctx.translateBy(x: 0, y: CGFloat(height))
        ctx.scaleBy(x: 1, y: -1)                            // CG 原点在左下，翻过来
        (body as NSString).draw(
            with: CGRect(x: 2, y: max(0, (CGFloat(height) - measured.height) / 2),
                         width: CGFloat(width) - 4, height: measured.height),
            options: [.usesLineFragmentOrigin, .usesFontLeading],
            attributes: attrs, context: nil)
        UIGraphicsPopContext()

        guard let data = ctx.data else { return nil }
        let p = data.bindMemory(to: UInt8.self, capacity: width * height)
        return Array(UnsafeBufferPointer(start: p, count: width * height))
    }
}
