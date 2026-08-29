import Foundation

/// 上一次成功拿到的数据，落在本地。
///
/// 为什么需要：App 启动时 @Published 的初值是 MockData 里的演示数字
/// （16:02 同步、52 分钟、护眼分 92），第一次请求回来之前家长看到的是
/// 编造的值。缓存之后，回头用户一进来看到的是自己真实的（可能稍旧的）
/// 数据；第一次装的用户走加载态，谁也不会看到假数字。
enum Cache {
    private static let d = UserDefaults.standard
    private static let enc = JSONEncoder()
    private static let dec = JSONDecoder()

    static func save<T: Encodable>(_ value: T, _ key: String) {
        guard let data = try? enc.encode(value) else { return }
        d.set(data, forKey: "cache." + key)
    }

    static func load<T: Decodable>(_ type: T.Type, _ key: String) -> T? {
        guard let data = d.data(forKey: "cache." + key) else { return nil }
        return try? dec.decode(type, from: data)
    }

    /// 重设档案时一起清掉，免得新孩子看到上一个孩子的数字
    static func clear() {
        for k in d.dictionaryRepresentation().keys where k.hasPrefix("cache.") {
            d.removeObject(forKey: k)
        }
    }
}
