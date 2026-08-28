const demoData = {
  xiaoman: {
    name: "小满",
    context: {
      today: "今天状态不错，光线调整后保持稳定。",
      week: "本周专注时间稳步增加，护眼提醒比上周减少。",
      month: "本月已经形成较稳定的放学后学习节奏。"
    },
    summary: "已连续专注 18 分钟，坐姿距离正常，桌面光线均匀。",
    liveClock: "18:24",
    distance: 36,
    lightState: "舒适",
    temp: 24.6,
    humidity: 48,
    focus: { today: 52, week: 286, month: 1184 },
    eyeScore: 92,
    rounds: 3,
    questions: 4,
    weekFocus: [32, 48, 41, 56, 38, 45, 52],
    insights: [
      ["专注时间在增长", "今天比昨日多学习 12 分钟", "进步"],
      ["坐姿调整有效", "16:32 提醒后，距离恢复到 36 cm", "已改善"],
      ["数学值得再复习", "4 个问题中有 3 个来自分数应用题", "建议"]
    ],
    distances: [38, 37, 35, 29, 34, 36, 37, 36],
    eyeEvents: [
      ["16:32", "距离低于 30 cm", "持续 24 秒后温和提醒", "已改善"],
      ["16:33", "孩子调整坐姿", "距离恢复至 36 cm", "正常"],
      ["17:18", "短暂靠近书本", "未达到提醒条件", "未打扰"]
    ],
    lights: { left: 612, right: 588, difference: 4 },
    sessions: [
      ["15:40", "数学 · 分数应用题", "24 分钟", "完成 8 道题"],
      ["16:24", "英语 · 单词朗读", "16 分钟", "跟读 12 个词"],
      ["17:05", "语文 · 阅读理解", "12 分钟", "完成一篇阅读"]
    ],
    qa: [
      ["数学", "为什么通分后分母要相同？", "用披萨分块举例后理解", true],
      ["数学", "这道分数应用题应该先算什么？", "仍需明天复习", false],
      ["英语", "“quiet”怎么发音？", "完成三次跟读", true],
      ["语文", "这一段的中心句在哪里？", "能够自己找出", true]
    ],
    subjects: [["数学", 75], ["英语", 16], ["语文", 9]],
    reportScore: 88,
    dimensions: [["专注节奏", 91], ["护眼表现", 92], ["任务完成", 86], ["主动提问", 82], ["环境舒适", 89]],
    milestones: [
      ["01", "最长连续专注达到 24 分钟", "比上周平均水平增加 6 分钟"],
      ["02", "坐姿提醒次数下降", "从上周平均每天 3 次降到 1 次"],
      ["03", "开始主动提出数学问题", "从“不会”变成能说清楚卡在哪里"]
    ]
  },
  lele: {
    name: "乐乐",
    context: {
      today: "今天完成两轮阅读，第二轮中途离席一次。",
      week: "本周阅读习惯稳定，晚间光线需要继续留意。",
      month: "本月主动提问增加，专注轮次还可以更加规律。"
    },
    summary: "已连续专注 11 分钟，距离正常，右侧光线稍亮。",
    liveClock: "11:08",
    distance: 39,
    lightState: "右侧稍亮",
    temp: 25.1,
    humidity: 45,
    focus: { today: 36, week: 218, month: 902 },
    eyeScore: 86,
    rounds: 2,
    questions: 3,
    weekFocus: [25, 34, 28, 41, 30, 24, 36],
    insights: [
      ["阅读习惯稳定", "连续 5 天完成了至少一轮阅读", "坚持"],
      ["晚间右侧偏亮", "建议把台灯向书桌中央移动一些", "关注"],
      ["离席次数略多", "第二轮学习中途离开 2 次", "建议"]
    ],
    distances: [41, 40, 39, 32, 35, 38, 39, 39],
    eyeEvents: [
      ["18:12", "距离短暂降至 32 cm", "未达到提醒条件", "未打扰"],
      ["18:28", "离开座位", "专注计时自动暂停", "已暂停"],
      ["18:31", "重新回到座位", "距离 39 cm", "正常"]
    ],
    lights: { left: 520, right: 634, difference: 18 },
    sessions: [
      ["17:30", "语文 · 课外阅读", "21 分钟", "阅读 14 页"],
      ["18:18", "英语 · 绘本跟读", "15 分钟", "完成一章"]
    ],
    qa: [
      ["语文", "这个故事里的主人公为什么生气？", "能够结合情节回答", true],
      ["英语", "“through”应该怎么读？", "仍需跟读练习", false],
      ["语文", "“迫不及待”是什么意思？", "能够自己造句", true]
    ],
    subjects: [["语文", 66], ["英语", 34], ["数学", 0]],
    reportScore: 82,
    dimensions: [["专注节奏", 78], ["护眼表现", 86], ["任务完成", 84], ["主动提问", 88], ["环境舒适", 76]],
    milestones: [
      ["01", "连续五天完成课外阅读", "已经形成稳定的放学后阅读习惯"],
      ["02", "开始用完整句子描述问题", "提问质量比上周更加清楚"],
      ["03", "能够自己确认词语含义", "完成解释后还能独立造句"]
    ]
  }
};

const pageTitles = {
  overview: "家庭概览", eyes: "护眼距离", light: "桌面光线", focus: "专注学习",
  qa: "提问辅导", environment: "学习环境", report: "学习复盘"
};

const state = { child: "xiaoman", period: "today", page: "overview", theme: "orange" };
let clockSeconds = 18 * 60 + 24;
let toastTimer;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function setText(selector, value) {
  const node = $(selector);
  if (node) node.textContent = value;
}

function renderFocusChart(values) {
  const days = ["一", "二", "三", "四", "五", "六", "日"];
  const max = Math.max(70, ...values);
  $("#focusChart").innerHTML = values.map((value, index) => `
    <div class="bar-column">
      <span class="bar-target"></span>
      <i class="bar-fill" data-value="${value} 分钟" style="height:${Math.max(10, value / max * 88)}%"></i>
      <label>周${days[index]}</label>
    </div>`).join("");
}

function renderInsights(items) {
  $("#insightList").innerHTML = items.map((item, index) => `
    <div class="insight-item">
      <span class="insight-index">0${index + 1}</span>
      <div><strong>${item[0]}</strong><small>${item[1]}</small></div>
      <span class="insight-tag">${item[2]}</span>
    </div>`).join("");
}

function renderDistanceTrack(values) {
  const min = 24;
  const max = 48;
  $("#distanceTrack").innerHTML = values.map((value, index) => {
    const bottom = ((value - min) / (max - min)) * 82 + 7;
    return `<div class="distance-point"><i style="bottom:${bottom}%" title="${value} cm"></i><span>${15 + index}:00</span></div>`;
  }).join("");
}

function renderEvents(items) {
  $("#eyeEvents").innerHTML = items.map(item => `
    <div class="event-row"><span>${item[0]}</span><strong>${item[1]}</strong><span>${item[2]}</span><b>${item[3]}</b></div>`).join("");
}

function renderSessions(items) {
  $("#sessionList").innerHTML = items.map(item => `
    <div class="session-row"><span class="session-time">${item[0]}</span><div><strong>${item[1]}</strong><small>${item[3]}</small></div><span class="session-duration">${item[2]}</span></div>`).join("");
}

function renderQA(items) {
  $("#qaList").innerHTML = items.map(item => `
    <div class="qa-item"><span class="qa-subject">${item[0]}</span><div><strong>${item[1]}</strong><small>${item[2]}</small></div><span class="${item[3] ? "understood" : "review-needed"}">${item[3] ? "已经理解" : "建议复习"}</span></div>`).join("");
}

function renderSubjects(items) {
  $("#subjectBars").innerHTML = items.map(item => `
    <div class="subject-row"><div><span>${item[0]}</span><strong>${item[1]}%</strong></div><div><i style="width:${item[1]}%"></i></div></div>`).join("");
}

function renderDimensions(items) {
  $("#dimensionList").innerHTML = items.map(item => `
    <div class="dimension-row"><span>${item[0]}</span><div><i style="width:${item[1]}%"></i></div><strong>${item[1]}</strong></div>`).join("");
}

function renderMilestones(items) {
  $("#milestoneList").innerHTML = items.map(item => `
    <div class="milestone-item"><span>${item[0]}</span><div><strong>${item[1]}</strong><small>${item[2]}</small></div></div>`).join("");
}

function renderEnvironmentTimeline(data) {
  const events = [
    ["15:30", `温度 ${data.temp.toFixed(1)}°C，湿度 ${data.humidity}%`, "舒适"],
    ["16:10", "检测到桌面左侧光线偏暗", "已调整"],
    ["16:11", "左右光线恢复到舒适范围", "正常"],
    ["17:20", "空气与设备温度检查", "正常"]
  ];
  $("#environmentTimeline").innerHTML = events.map(item => `
    <div class="timeline-item"><span>${item[0]}</span><i class="timeline-dot"></i><strong>${item[1]}</strong><b>${item[2]}</b></div>`).join("");
}

function renderAll() {
  const data = demoData[state.child];
  const periodFocus = data.focus[state.period];
  const periodUnit = state.period === "today" ? "分钟" : "分钟";
  const percent = Math.min(100, Math.round(data.focus.today / 70 * 100));

  setText("#contextLine", data.context[state.period]);
  setText("#heroChildName", data.name);
  setText("#heroSummary", data.summary);
  setText("#liveClock", data.liveClock);
  setText("#overviewDistance", `${data.distance} cm`);
  setText("#overviewLight", data.lightState);
  setText("#overviewTemp", `${data.temp.toFixed(1)}°C`);
  setText("#metricFocus", "");
  $("#metricFocus").innerHTML = `${periodFocus}<small>${periodUnit}</small>`;
  setText("#metricFocusNote", state.period === "today" ? "比昨日多 12 分钟" : state.period === "week" ? "完成周目标 82%" : "形成 18 个有效学习日");
  $("#metricEye").innerHTML = `${data.eyeScore}<small>分</small>`;
  $("#metricRounds").innerHTML = `${data.rounds}<small>轮</small>`;
  $("#metricQuestions").innerHTML = `${data.questions}<small>次</small>`;
  setText("#weekTotal", data.focus.week);
  setText("#capEye", `${data.distance} cm · 正常`);
  setText("#capLight", data.lightState);
  setText("#capFocus", `${data.focus.today} 分钟`);
  setText("#capQA", `${data.questions} 个问题`);
  setText("#capEnv", `${data.temp.toFixed(1)}°C · 舒适`);
  setText("#eyeCurrentDistance", `${data.distance} cm`);
  setText("#lightCurrentState", data.lightState === "舒适" ? "光线舒适" : data.lightState);
  setText("#lightCurrentDetail", `左右差异 ${data.lights.difference}%`);
  setText("#leftLightValue", data.lights.left);
  setText("#rightLightValue", data.lights.right);
  $("#leftLightFill").style.height = `${Math.min(90, data.lights.left / 8)}%`;
  $("#rightLightFill").style.height = `${Math.min(90, data.lights.right / 8)}%`;
  $("#lightMarker").style.left = `${Math.min(85, 35 + data.lights.difference)}%`;
  setText("#focusTotalLarge", `${data.focus.today} 分钟`);
  setText("#focusRoundsLarge", `完成 ${data.rounds} 轮`);
  setText("#focusPercent", `${percent}%`);
  $("#focusRing").style.setProperty("--progress", `${percent}%`);
  $("#focusRing small").textContent = `${data.focus.today} / 70 分钟`;
  setText("#qaTotalLarge", `${data.questions} 个`);
  setText("#envTemp", "");
  $("#envTemp").innerHTML = `${data.temp.toFixed(1)}<small>°C</small>`;
  setText("#envHumidity", "");
  $("#envHumidity").innerHTML = `${data.humidity}<small>%</small>`;
  setText("#reportChildName", data.name);
  setText("#reportScore", data.reportScore);

  renderFocusChart(data.weekFocus);
  renderInsights(data.insights);
  renderDistanceTrack(data.distances);
  renderEvents(data.eyeEvents);
  renderSessions(data.sessions);
  renderQA(data.qa);
  renderSubjects(data.subjects);
  renderDimensions(data.dimensions);
  renderMilestones(data.milestones);
  renderEnvironmentTimeline(data);
}

function showPage(page) {
  state.page = page;
  $$(".page").forEach(node => node.classList.toggle("active", node.dataset.page === page));
  $$(".nav-item").forEach(node => node.classList.toggle("active", node.dataset.pageTarget === page));
  setText("#pageTitle", pageTitles[page]);
  document.body.classList.remove("menu-open");
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

function bindEvents() {
  $$("[data-page-target], [data-go-page]").forEach(button => {
    button.addEventListener("click", () => showPage(button.dataset.pageTarget || button.dataset.goPage));
  });

  $$(".child-option").forEach(button => {
    button.addEventListener("click", () => {
      state.child = button.dataset.child;
      clockSeconds = state.child === "xiaoman" ? 18 * 60 + 24 : 11 * 60 + 8;
      $$(".child-option").forEach(node => node.classList.toggle("active", node === button));
      renderAll();
      showToast(`已切换到 ${demoData[state.child].name} 的学习数据`);
    });
  });

  $$(".period-option").forEach(button => {
    button.addEventListener("click", () => {
      state.period = button.dataset.period;
      $$(".period-option").forEach(node => node.classList.toggle("active", node === button));
      renderAll();
    });
  });

  $("#themeToggle").addEventListener("click", () => {
    state.theme = state.theme === "orange" ? "pink" : "orange";
    document.body.dataset.theme = state.theme;
    setText("#themeLabel", state.theme === "orange" ? "橙白" : "粉白");
    showToast(`已切换为${state.theme === "orange" ? "橙白" : "粉白"}主题`);
  });

  $("#sendEncouragement").addEventListener("click", () => showToast(`鼓励已加入设备队列：${demoData[state.child].name}，继续保持！`));
  $("#notificationButton").addEventListener("click", () => showToast("当前有 1 条光线改善记录，没有紧急提醒"));
  $("#exportReport").addEventListener("click", () => showToast("演示报告已生成；接入后可导出 PDF 或分享链接"));
  $("#addDemoSession").addEventListener("click", () => showToast("这是本地演示：真实版本会自动同步新一轮学习记录"));
  $$(".switch-row input").forEach(input => input.addEventListener("change", () => showToast(input.checked ? "提醒已开启" : "提醒已暂停")));

  $("#mobileMenu").addEventListener("click", () => document.body.classList.add("menu-open"));
  $("#mobileBackdrop").addEventListener("click", () => document.body.classList.remove("menu-open"));
}

function tickClock() {
  clockSeconds += 1;
  const minutes = Math.floor(clockSeconds / 60).toString().padStart(2, "0");
  const seconds = (clockSeconds % 60).toString().padStart(2, "0");
  setText("#liveClock", `${minutes}:${seconds}`);
}

bindEvents();
renderAll();
setInterval(tickClock, 1000);
