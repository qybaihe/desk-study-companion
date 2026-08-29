import Foundation
import SwiftUI

/// 后端是固定的一台机器，不让用户填。
///
/// 家长装上 App 就该看到自己孩子的数据 —— 让他去输地址、令牌、孩子标识，
/// 三个字段错一个就连不上，而这三个值对每一台设备都是同一份。
/// 所以直接编进包里，引导页只问一件真正因人而异的事：孩子叫什么。
enum Backend {
    static let baseURL = URL(string: "https://sheepy.timoz.me")!
    /// 机密不进仓库。照着 Secrets.example.swift 建一份 Secrets.swift。
    static let token   = Secrets.apiToken

    /// 和板子固件里的 CHILD_ID 是同一个常量。两边必须一致，
    /// 否则 App 读的是一个空的孩子。改这里就要同步改 firmware/sheepy_config.py。
    static let childID = "sheepy"
}


/// 孩子档案。本地存一份用于显示，同时写到后端的 child 表。
@MainActor
final class Profile: ObservableObject {
    @Published var name: String      { didSet { def.set(name, forKey: kName) } }
    @Published var grade: String     { didSet { def.set(grade, forKey: kGrade) } }
    @Published var onboarded: Bool   { didSet { def.set(onboarded, forKey: kDone) } }

    private let def = UserDefaults.standard
    private let kName = "child.name", kGrade = "child.grade", kDone = "onboarded"

    init() {
        name      = def.string(forKey: kName) ?? ""
        grade     = def.string(forKey: kGrade) ?? ""
        onboarded = def.bool(forKey: kDone)
    }

    var displayName: String { name.isEmpty ? "孩子" : name }
    /// 「小满 · 二年级」；没填年级就只有名字
    var titleLine: String { grade.isEmpty ? displayName : "\(displayName) · \(grade)" }

    /// 重设：清掉本地档案，回到引导页重新建一个。
    /// 只清本地 —— 云端那份数据还在，重新用同一个名字建档就接得回去。
    func reset() {
        name = ""; grade = ""; onboarded = false
        // 缓存一起清 —— 否则新建的孩子会先看到上一个孩子的数字
        Cache.clear()
    }
}
