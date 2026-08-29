import Foundation

/// App 永远不直连 TiDB —— MySQL 协议 + 数据库凭据放在客户端是安全事故，
/// 和 ESP32 不能直连是同一个道理。真实数据一律走自建 HTTP 后端。
protocol StudyDataSource {
    func snapshot() async throws -> Snapshot
    func eye() async throws -> EyeReport
    func study() async throws -> StudyReport
    func diary() async throws -> [DiaryLine]
    func milestones() async throws -> [Milestone]
    func asks() async throws -> AskReport
    func weekly(week: String?) async throws -> WeeklyReport
    func weeklyList() async throws -> [WeekRef]
    func reminders() async throws -> ReminderReport
    func settings() async throws -> Settings
}

struct MockSource: StudyDataSource {
    func snapshot() async throws -> Snapshot        { Mock.snapshot }
    func eye() async throws -> EyeReport            { Mock.eye }
    func study() async throws -> StudyReport        { Mock.study }
    func diary() async throws -> [DiaryLine]        { Mock.diary }
    func milestones() async throws -> [Milestone]   { Mock.milestones }
    func asks() async throws -> AskReport            { Mock.asks }
    func weekly(week: String?) async throws -> WeeklyReport { Mock.weekly }
    func weeklyList() async throws -> [WeekRef]     { [] }
    func reminders() async throws -> ReminderReport { Mock.reminders }
    func settings() async throws -> Settings        { Mock.settings }
}

/// 指向自建 FastAPI 中转层（同一个后端也接收 ESP32 的批量上报）。
struct APISource: StudyDataSource {
    var baseURL: URL
    var childID: String
    var token: String?              // Worker 的 API_TOKEN，设了就必须带
    var session: URLSession = .shared

    private func get<T: Decodable>(_ path: String,
                                   extra: [URLQueryItem] = []) async throws -> T {
        var c = URLComponents(url: baseURL.appendingPathComponent(path),
                              resolvingAgainstBaseURL: false)!
        c.queryItems = [URLQueryItem(name: "child_id", value: childID)] + extra
        var req = URLRequest(url: c.url!)
        req.timeoutInterval = 10
        if let token, !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    func snapshot() async throws -> Snapshot        { try await get("api/snapshot") }
    func eye() async throws -> EyeReport            { try await get("api/eye") }
    func study() async throws -> StudyReport        { try await get("api/study") }
    func diary() async throws -> [DiaryLine]        { try await get("api/diary") }
    func milestones() async throws -> [Milestone]   { try await get("api/milestones") }
    func asks() async throws -> AskReport            { try await get("api/ask") }
    func weekly(week: String?) async throws -> WeeklyReport {
        try await get("api/weekly",
                      extra: week.map { [URLQueryItem(name: "week", value: $0)] } ?? [])
    }
    func weeklyList() async throws -> [WeekRef]     { try await get("api/weekly/list") }
    func reminders() async throws -> ReminderReport { try await get("api/reminders") }
    func settings() async throws -> Settings        { try await get("api/settings") }

    private func post(_ path: String, _ body: [String: Any]) async throws {
        var req = URLRequest(url: baseURL.appendingPathComponent(path))
        req.httpMethod = "POST"
        req.timeoutInterval = 10
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token, !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        var payload = body
        payload["child_id"] = childID
        req.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let (_, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }

    /// 设置页改完写回 device_config。Worker 会把 rev +1，板子据此重读。
    func putSettings(_ s: Settings) async throws {
        try await post("api/settings", [
            "goalHours": s.goalHours,
            "distanceMin": s.distanceMin,
            "distanceMax": s.distanceMax,
            // 按下标取，不按标签文字 —— 标签是可以改文案的，改一次匹配就错位
            "voiceOn": s.channels.indices.contains(0) ? s.channels[0].on : true,
            "animOn": s.channels.indices.contains(1) ? s.channels[1].on : true,
            "pushOn": s.channels.indices.contains(2) ? s.channels[2].on : true,
            "childVisible": s.childVisible,
        ])
    }

    /// 喂草 / 奖励。板子下次联系服务器时取走（最多等 20 秒）。
    func sendAction(_ kind: String) async throws {
        try await post("api/action", ["kind": kind])
    }

    /// 给孩子捎一句话。位图在这一端渲染好 —— 板子的 OLED 没有中文字库。
    func sendMessage(_ text: String) async throws {
        var body: [String: Any] = ["text": text]
        if let bmp = OLEDBitmap.render(text) {
            body["bitmap"] = bmp.base64EncodedString()
        }
        try await post("api/message", body)
    }

    /// 建档/改名。child_id 固定，这里只写展示信息。
    func putChild(name: String, grade: String) async throws {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/child"))
        req.httpMethod = "POST"
        req.timeoutInterval = 10
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token, !token.isEmpty {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "child_id": childID, "name": name, "grade": grade,
        ])
        let (_, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            throw URLError(.badServerResponse)
        }
    }
}

/// URLSession 的 localizedDescription 在这套环境下是英文（"The request timed out."），
/// 摆在一个中文 App 的错误页上很扎眼。常见几种自己翻。
func friendlyError(_ error: Error) -> String {
    guard let e = error as? URLError else {
        return (error as NSError).code == NSURLErrorBadServerResponse
            ? "后台返回了意外的结果" : "出了点问题，稍后再试"
    }
    switch e.code {
    case .timedOut:              return "连接超时。检查一下网络，或者稍后再试"
    case .notConnectedToInternet: return "手机没有联网"
    case .networkConnectionLost: return "网络中断了"
    case .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed:
                                 return "找不到后台服务器"
    case .badServerResponse:     return "后台返回了意外的结果"
    case .userAuthenticationRequired: return "访问令牌不对"
    default:                     return "连接失败（\(e.code.rawValue)）"
    }
}


@MainActor
final class Store: ObservableObject {
    @Published var snapshot: Snapshot = Mock.snapshot
    @Published var eye: EyeReport = Mock.eye
    @Published var study: StudyReport = Mock.study
    @Published var diary: [DiaryLine] = Mock.diary
    @Published var milestones: [Milestone] = Mock.milestones
    @Published var asks: AskReport = Mock.asks
    @Published var weekly: WeeklyReport = Mock.weekly
    @Published var weeks: [WeekRef] = []
    /// nil = 最新一周。选了往期就固定在那一周，轮询不再把它冲掉。
    @Published var pinnedWeek: String?
    @Published var reminders: ReminderReport = Mock.reminders
    @Published var settings: Settings = Mock.settings
    @Published var isLive = true
    @Published var lastError: String?

    /// 首屏状态。App 不能在拿到真实数据之前把 Mock 的数字摆出来 ——
    /// 家长看到的每一个数字都必须是真的，哪怕代价是先转一会儿圈。
    enum Load: Equatable { case loading, ready, failed(String) }
    @Published var load: Load = .loading

    /// 一装上就指向固定后端。
    private var source: StudyDataSource = APISource(
        baseURL: Backend.baseURL, childID: Backend.childID, token: Backend.token)
    private var poller: Task<Void, Never>?

    init() {
        // 有缓存就直接进主界面 —— 回头用户不该为了看一眼数据先转圈
        if let s = Cache.load(Snapshot.self, "snapshot") {
            snapshot = s
            eye        = Cache.load(EyeReport.self, "eye") ?? eye
            study      = Cache.load(StudyReport.self, "study") ?? study
            diary      = Cache.load([DiaryLine].self, "diary") ?? diary
            milestones = Cache.load([Milestone].self, "milestones") ?? milestones
            asks       = Cache.load(AskReport.self, "asks") ?? asks
            weekly     = Cache.load(WeeklyReport.self, "weekly") ?? weekly
            weeks      = Cache.load([WeekRef].self, "weeks") ?? weeks
            reminders  = Cache.load(ReminderReport.self, "reminders") ?? reminders
            settings   = Cache.load(Settings.self, "settings") ?? settings
            load = .ready
        }
    }

    /// 留给调试：临时指到本地 FastAPI。正常路径不走这里。
    func connect(to baseURL: URL, childID: String, token: String? = nil) {
        source = APISource(baseURL: baseURL, childID: childID, token: token)
        isLive = true
        Task { await refresh() }
    }

    /// 引导页填完名字时调一次，把孩子写进 child 表。
    func register(name: String, grade: String) async -> String? {
        guard let api = source as? APISource else { return nil }
        do {
            try await api.putChild(name: name, grade: grade)
            await refresh()
            return nil
        } catch {
            return friendlyError(error)
        }
    }

    /// 设置页每改一项就写回一次。失败只记 lastError，不回滚 —— 下次
    /// refresh 会把服务端的真值盖回来。
    func saveSettings(_ s: Settings) async {
        settings = s
        guard let api = source as? APISource else { return }
        do { try await api.putSettings(s); lastError = nil }
        catch { lastError = friendlyError(error) }
    }

    /// 返回是否送达。UI 拿它来决定给不给反馈。
    @discardableResult
    func sendAction(_ kind: String) async -> Bool {
        guard let api = source as? APISource else { return false }
        do { try await api.sendAction(kind); lastError = nil; return true }
        catch { lastError = friendlyError(error); return false }
    }

    /// 给孩子捎一句话。板子取走后在 OLED 上显示十秒。
    @discardableResult
    func sendMessage(_ text: String) async -> Bool {
        guard let api = source as? APISource else { return false }
        do { try await api.sendMessage(text); lastError = nil; return true }
        catch { lastError = friendlyError(error); return false }
    }

    /// 切到某一期。传 nil 回到最新。
    func selectWeek(_ key: String?) async {
        pinnedWeek = key
        guard let w = try? await source.weekly(week: key) else { return }
        weekly = w
    }

    func refresh() async {
        // 九个接口并发发，不要串着等。串行时首次打开要转三四秒 ——
        // 每个接口都是一次独立的 HTTP 往返，它们之间没有依赖。
        let src = source
        let week = pinnedWeek
        do {
            async let a = src.snapshot()
            async let b = src.eye()
            async let c = src.study()
            async let d = src.diary()
            async let e = src.milestones()
            async let k = src.asks()
            async let f = src.weekly(week: week)
            async let g = src.reminders()
            async let h = src.settings()
            async let list = try? src.weeklyList()

            snapshot   = try await a
            eye        = try await b
            study      = try await c
            diary      = try await d
            milestones = try await e
            asks       = try await k
            weekly     = try await f
            reminders  = try await g
            settings   = try await h
            weeks      = (await list) ?? weeks
            lastError = nil
            cacheAll()
            load = .ready
        } catch {
            let msg = friendlyError(error)
            lastError = msg
            // 已经有数据在屏幕上就别把它换成错误页，留着旧数据 + 顶部提示
            if load == .loading { load = .failed(msg) }
        }
    }

    private func cacheAll() {
        Cache.save(snapshot, "snapshot");   Cache.save(eye, "eye")
        Cache.save(study, "study");         Cache.save(diary, "diary")
        Cache.save(milestones, "milestones"); Cache.save(asks, "asks")
        Cache.save(reminders, "reminders"); Cache.save(settings, "settings")
        Cache.save(weeks, "weeks")
        // 翻往期时不要把某一期覆盖成"最新一期"的缓存
        if pinnedWeek == nil { Cache.save(weekly, "weekly") }
    }

    /// 首屏失败后手动重试
    func retry() async {
        load = .loading
        await refresh()
    }

    /// 小羊状态变化很慢（体力每 30 秒 ±1），10 秒轮询足够，不需要 WebSocket
    func startPolling() {
        guard isLive else { return }
        poller?.cancel()
        poller = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 10_000_000_000)
                await self?.refresh()
            }
        }
    }

    func stopPolling() { poller?.cancel(); poller = nil }
}
