import Foundation

/// App 永远不直连 TiDB —— MySQL 协议 + 数据库凭据放在客户端是安全事故，
/// 和 ESP32 不能直连是同一个道理。真实数据一律走自建 HTTP 后端。
protocol StudyDataSource {
    func snapshot() async throws -> Snapshot
    func eye() async throws -> EyeReport
    func study() async throws -> StudyReport
    func diary() async throws -> [DiaryLine]
    func milestones() async throws -> [Milestone]
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
            "voiceOn": s.channels.first(where: { $0.label.contains("语音") })?.on ?? true,
            "animOn": s.channels.first(where: { $0.label.contains("动画") })?.on ?? true,
            "pushOn": s.channels.first(where: { $0.label.contains("推送") })?.on ?? true,
            "childVisible": s.childVisible,
        ])
    }

    /// 喂草 / 奖励。板子下次联系服务器时取走（最多等 20 秒）。
    func sendAction(_ kind: String) async throws {
        try await post("api/action", ["kind": kind])
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

@MainActor
final class Store: ObservableObject {
    @Published var snapshot: Snapshot = Mock.snapshot
    @Published var eye: EyeReport = Mock.eye
    @Published var study: StudyReport = Mock.study
    @Published var diary: [DiaryLine] = Mock.diary
    @Published var milestones: [Milestone] = Mock.milestones
    @Published var weekly: WeeklyReport = Mock.weekly
    @Published var weeks: [WeekRef] = []
    /// nil = 最新一周。选了往期就固定在那一周，轮询不再把它冲掉。
    @Published var pinnedWeek: String?
    @Published var reminders: ReminderReport = Mock.reminders
    @Published var settings: Settings = Mock.settings
    @Published var isLive = true
    @Published var lastError: String?

    /// 一装上就指向固定后端。@Published 的初值还是 Mock —— 首帧不至于空白，
    /// 第一次 refresh 成功后整屏被真实数据替换掉。
    private var source: StudyDataSource = APISource(
        baseURL: Backend.baseURL, childID: Backend.childID, token: Backend.token)
    private var poller: Task<Void, Never>?

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
            return error.localizedDescription
        }
    }

    /// 设置页每改一项就写回一次。失败只记 lastError，不回滚 —— 下次
    /// refresh 会把服务端的真值盖回来。
    func saveSettings(_ s: Settings) async {
        settings = s
        guard let api = source as? APISource else { return }
        do { try await api.putSettings(s); lastError = nil }
        catch { lastError = error.localizedDescription }
    }

    /// 返回是否送达。UI 拿它来决定给不给反馈。
    @discardableResult
    func sendAction(_ kind: String) async -> Bool {
        guard let api = source as? APISource else { return false }
        do { try await api.sendAction(kind); lastError = nil; return true }
        catch { lastError = error.localizedDescription; return false }
    }

    /// 切到某一期。传 nil 回到最新。
    func selectWeek(_ key: String?) async {
        pinnedWeek = key
        guard let w = try? await source.weekly(week: key) else { return }
        weekly = w
    }

    func refresh() async {
        do {
            snapshot = try await source.snapshot()
            eye = try await source.eye()
            study = try await source.study()
            diary = try await source.diary()
            milestones = try await source.milestones()
            weekly = try await source.weekly(week: pinnedWeek)
            weeks = (try? await source.weeklyList()) ?? weeks
            reminders = try await source.reminders()
            settings = try await source.settings()
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
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
