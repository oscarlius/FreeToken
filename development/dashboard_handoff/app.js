"use strict";

const CONFIG = { snapshotUrl: "snapshot.json", apiUrl: "/api/devtest", pollMs: 5000, staleMs: 15000 };
const apiMode = new URLSearchParams(location.search).get("source") === "api";
let lastData = null;
let timer = 0;

const el = (tag, text, className) => {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  return node;
};
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const fmt = (number) => String(Math.round(number * 1000) / 1000);
const valueText = (number, unit = "") => finite(number) ? `${fmt(number)}${unit ? ` ${unit}` : ""}` : "缺失";
const clear = (node) => node.replaceChildren();

function tone(status) {
  const text = String(status || "");
  if (/异常|未通过|退回|失败|阻塞/.test(text)) return "bad";
  if (/完成|通过/.test(text) && !/未通过|待/.test(text)) return "ok";
  if (/进行|待|未知|复核/.test(text)) return "warn";
  return "info";
}

function counts(items, pick) {
  const map = new Map();
  items.forEach((item) => {
    const key = pick(item) || "缺失";
    map.set(key, (map.get(key) || 0) + 1);
  });
  return [...map.entries()];
}

function mixBar(entries) {
  const bar = el("div", undefined, "mix");
  bar.setAttribute("aria-hidden", "true");
  entries.forEach(([label, count]) => {
    const part = el("span");
    part.className = tone(label);
    part.style.flex = String(count);
    part.title = `${label} ${count}`;
    bar.append(part);
  });
  return bar;
}

function facts(rows) {
  const list = el("dl", undefined, "facts");
  rows.forEach(([key, content]) => {
    const dd = el("dd");
    if (content instanceof Node) dd.append(content);
    else dd.textContent = content;
    list.append(el("dt", key), dd);
  });
  return list;
}

function evidence(items = []) {
  if (!items.length) return null;
  const list = el("ul", undefined, "evidence");
  items.forEach((item) => list.append(el("li", `${item.path || ""}${item.summary ? ` — ${item.summary}` : ""}`)));
  return list;
}

function card(title, status) {
  const box = el("article", undefined, "card");
  const head = el("div", undefined, "card-head");
  head.append(el("h2", title), el("span", status, `badge ${tone(status)}`));
  box.append(head);
  return box;
}

function statCard(label, value, entries) {
  const box = el("div", undefined, "card");
  box.append(el("div", label, "label"), el("div", value, "value"));
  if (entries.length) {
    box.append(mixBar(entries));
    box.append(el("div", entries.map(([name, count]) => `${name} ${count}`).join(" · "), "small"));
  }
  return box;
}

function renderSummary(data) {
  const root = document.getElementById("summary");
  clear(root);
  const dev = data.development || [];
  const tests = data.tests || [];
  const comps = data.comparisons || [];
  const comparable = comps.filter((item) => item.comparable === true).length;
  root.append(
    statCard("开发卡", String(dev.length), counts(dev, (item) => item.status)),
    statCard("测试", String(tests.length), counts(tests, (item) => item.stage)),
    statCard("可比较对照", `${comparable}/${comps.length || 0}`, []),
    statCard("基线", data.baseline?.code_version || "缺失", [])
  );
}

function renderDevelopment(data) {
  const root = document.getElementById("development");
  clear(root);
  const items = data.development || [];
  const lane = el("div", undefined, "lane");
  items.forEach((item) => {
    const step = el("div", undefined, `step ${tone(item.status)}`);
    step.append(
      el("div", undefined, "step-bar"),
      el("div", item.card || "未编号", "step-id"),
      el("div", item.title || "未命名", "step-name"),
      el("div", item.status || "缺失", "step-status")
    );
    lane.append(step);
  });
  if (items.length) root.append(lane);
  items.forEach((item) => {
    const box = card(`${item.card} · ${item.title}`, item.status || "缺失");
    box.append(facts([
      ["候选提交", item.candidate_commit || "未提供"],
      ["快照维护时间", item.updated_at || "缺失"],
      ["下一步", item.next_step || "缺失"]
    ]));
    if (item.blockers?.length) {
      box.append(el("p", "验收缺口", "block-label"), evidence(item.blockers.map((text) => ({ path: text }))));
    }
    const proof = evidence(item.evidence);
    if (proof) {
      box.append(el("p", "证据路径（仅展示）", "small"), proof);
    }
    root.append(box);
  });
}

function pidNode(item) {
  const alive = item.pid_alive === true ? "是（仅本次观察）" : item.pid_alive === false ? "否" : "未知";
  const wrap = el("span", undefined, "pid");
  const dot = el("span", undefined, `dot ${item.pid_alive === true ? "live" : item.pid_alive === false ? "dead" : "warm"}`);
  wrap.append(dot, document.createTextNode(alive));
  return wrap;
}

function renderTests(data) {
  const root = document.getElementById("tests");
  clear(root);
  const items = data.tests || [];
  const stages = counts(items, (item) => item.stage);
  if (stages.length) {
    const board = el("div", undefined, "card");
    board.append(el("div", "阶段构成", "label"), mixBar(stages), el("div", stages.map(([name, count]) => `${name} ${count}`).join(" · "), "small"));
    root.append(board);
  }
  items.forEach((item) => {
    const status = `${item.stage || "缺失"} · ${item.execution_status || "缺失"}`;
    const box = card(`${item.card} · ${item.rid || "未分配"}`, status);
    const life = el("div", undefined, "life");
    [
      ["执行", item.execution_status || "缺失"],
      ["复核", item.review_status || "缺失"],
      ["封存", item.sealed === true ? "已封存" : "未封存"],
      ["正式判定", item.formal_verdict || "缺失"]
    ].forEach(([name, text]) => {
      const cell = el("div");
      cell.append(el("b", name), el("span", text));
      life.append(cell);
    });
    box.append(life);
    box.append(facts([
      ["批次 / PID", `${item.batch ?? "缺失"} / ${item.batch_pid ?? "缺失"}`],
      ["进程存活", pidNode(item)],
      ["身份校验", item.identity_verified === true ? "已校验" : "未校验或未知"],
      ["观察来源", item.process_observer || "缺失"],
      ["状态更新时间", item.status_updated_at || "缺失"],
      ["进度", item.progress ? `${item.progress.done}/${item.progress.total}` : "未声明总数"]
    ]));
    const proof = evidence(item.evidence);
    if (proof) box.append(el("p", "证据路径（仅展示）", "small"), proof);
    root.append(box);
  });
}

function barRow(label, number, unit, kind, max) {
  const row = el("div", undefined, "pair");
  const track = el("div", undefined, "track");
  const fill = document.createElement("i");
  fill.className = kind;
  if (finite(number) && finite(max) && max > 0) fill.style.width = `${Math.max(0, Math.min(100, (Math.abs(number) / max) * 100))}%`;
  track.append(fill);
  row.append(el("div", label, "name"), track, el("div", valueText(number, unit), "num"));
  return row;
}

function deltaTone(item, deltaAbs) {
  if (!finite(deltaAbs) || deltaAbs === 0) return "";
  if (item.direction === "lower_is_better") return deltaAbs < 0 ? "ok" : "bad";
  if (item.direction === "higher_is_better") return deltaAbs > 0 ? "ok" : "bad";
  return "";
}

function renderComparisons(data) {
  const root = document.getElementById("comparisons");
  clear(root);
  (data.comparisons || []).forEach((item) => {
    const hasValues = finite(item.baseline?.value) && finite(item.experiment?.value);
    const canCalculate = item.comparable === true && hasValues;
    const box = card(item.metric || "未命名指标", canCalculate ? "可比较" : "不可直接比较");
    const max = hasValues ? Math.max(Math.abs(item.baseline.value), Math.abs(item.experiment.value)) : 0;
    box.append(
      barRow("基线", item.baseline?.value, item.unit, "base", max),
      barRow("实验", item.experiment?.value, item.unit, "exp", max)
    );
    const deltaAbs = canCalculate ? item.experiment.value - item.baseline.value : null;
    const deltaPct = canCalculate && item.baseline.value !== 0 ? (deltaAbs / item.baseline.value) * 100 : null;
    const delta = canCalculate
      ? `${valueText(deltaAbs, item.unit)}；${deltaPct === null ? "相对差不可计算（基线为零）" : `${String(deltaPct)}%`}`
      : "不计算差值";
    const deltaNode = el("p", `差值（实验−基线）：${delta}`, `delta ${deltaTone(item, deltaAbs)}`.trim());
    box.append(deltaNode);
    box.append(facts([
      ["基线", `${item.baseline?.rid || "缺失"} / ${item.baseline?.arm || "缺失"}`],
      ["实验", `${item.experiment?.rid || "缺失"} / ${item.experiment?.arm || "缺失"}`],
      ["字段路径", `${item.baseline?.field_path || "字段路径缺失"} · ${item.experiment?.field_path || "字段路径缺失"}`],
      ["方向", item.direction || "缺失"],
      ["可比性说明", item.reason || "缺失"],
      ["允许差异", item.allowed_differences?.length ? item.allowed_differences.join("、") : "无"],
      ["科学状态", item.scientific_status || "缺失"]
    ]));
    root.append(box);
  });
  if (data.first_shots?.length) {
    const box = card("首轮单列，不纳入冷均值", "仅展示");
    const items = data.first_shots;
    const max = Math.max(...items.map((item) => finite(item.value) ? Math.abs(item.value) : 0), 0);
    const groups = new Map();
    items.forEach((item) => {
      const arm = String(item.arm || "");
      const pass = (arm.match(/p(\d+)/) || [, "?"])[1];
      const side = arm.startsWith("A") ? "A" : "B";
      if (!groups.has(pass)) groups.set(pass, {});
      groups.get(pass)[side] = item;
    });
    const grid = el("div", undefined, "shot-grid");
    groups.forEach((sides, pass) => {
      const col = el("div", undefined, "shot-col");
      col.append(el("div", `第 ${pass} 次`, "shot-title"));
      col.append(barRow("切分开", sides.A?.value, sides.A?.unit || "", "base", max));
      col.append(barRow("切分关", sides.B?.value, sides.B?.unit || "", "exp", max));
      grid.append(col);
    });
    const legend = el("div", undefined, "legend");
    legend.append(el("span"));
    const a = el("span");
    a.append(el("i", undefined, "base"), document.createTextNode("切分开"));
    const b = el("span");
    b.append(el("i", undefined, "exp"), document.createTextNode("切分关"));
    legend.append(a, b);
    box.append(grid, legend);
    items.forEach((item) => box.append(facts([[`${item.rid || "缺失"} · ${item.arm || "缺失"}`, `${valueText(item.value, item.unit)}；${item.note || ""}`], ["字段路径", item.field_path || "缺失"]])));
    root.append(box);
  }
}

function renderErrors(data) {
  const root = document.getElementById("errors");
  clear(root);
  const items = data.errors || [];
  if (!items.length) return;
  const box = el("div", undefined, "card");
  box.append(el("div", "数据源提示", "label"));
  const list = el("ul", undefined, "evidence");
  items.forEach((item) => list.append(el("li", typeof item === "string" ? item : (item.message || JSON.stringify(item)))));
  box.append(list);
  root.append(box);
}

function modeLabel(mode) {
  if (mode === "snapshot") return "本地快照，非实时";
  if (mode === "live") return "只读 API 数据";
  if (mode === "demo") return "演示数据，非实时";
  throw new Error(`不支持的 mode: ${String(mode)}`);
}

function render(data, source) {
  lastData = data;
  const observed = new Date(data.observed_at);
  const age = Number.isFinite(observed.valueOf()) ? Date.now() - observed.valueOf() : NaN;
  const stale = !Number.isFinite(age) || age > CONFIG.staleMs;
  const state = document.getElementById("source-status");
  state.className = `notice${stale ? " warn" : ""}`;
  state.textContent = `${modeLabel(data.mode)} · 采集时间 ${data.observed_at || "缺失"} · ${stale ? "数据过期/连接异常：不能据此判定进程停止" : "数据新鲜"}`;
  document.getElementById("baseline").textContent = `当前 E2 基线：${data.baseline?.code_version || "缺失"} · ${data.baseline?.commit || "缺失"} · 来源 ${source}${data.source_note ? `。${data.source_note}` : ""}`;
  renderErrors(data);
  renderSummary(data);
  renderDevelopment(data);
  renderTests(data);
  renderComparisons(data);
}

async function refresh() {
  const url = apiMode ? CONFIG.apiUrl : CONFIG.snapshotUrl;
  try {
    const response = await fetch(url, { cache: "no-store", headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (data.schema !== "ft_devtest/v1") throw new Error("不支持的数据 schema");
    modeLabel(data.mode);
    render(data, url);
  } catch (error) {
    const state = document.getElementById("source-status");
    state.className = "notice warn";
    state.textContent = `读取 ${url} 失败：${error.message}。${lastData ? "保留上一份快照；不回退到伪造实时数据。" : "没有可显示数据。"}`;
  }
}

document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => {
  document.querySelectorAll(".tab, .panel").forEach((node) => node.classList.remove("active"));
  button.classList.add("active");
  document.getElementById(button.dataset.tab).classList.add("active");
}));

function startPolling() {
  if (timer) clearInterval(timer);
  timer = setInterval(refresh, CONFIG.pollMs);
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    clearInterval(timer);
    timer = 0;
  } else {
    refresh();
    startPolling();
  }
});

refresh();
startPolling();
