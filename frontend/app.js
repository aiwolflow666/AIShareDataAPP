let currentSymbol = null;
let currentName = null;
let chartInstances = [];
let tabCache = {};
let isSelecting = false;
let searchAbort = null;
let currentTab = "info";
let backendOnline = null;

const $ = (sel) => document.querySelector(sel);

async function checkBackend() {
  try {
    const res = await fetch(`${window.API_BASE}/health`, { signal: AbortSignal.timeout(8000) });
    backendOnline = res.ok;
  } catch {
    backendOnline = false;
  }
  const badge = $("#backendStatus");
  if (badge) {
    badge.className = "backend-badge " + (backendOnline ? "online" : "offline");
    badge.textContent = backendOnline ? "● 后端已连接" : "● 后端未连接";
  }
}

async function fetchJSON(path, signal) {
  const url = `${window.API_BASE}${path}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);
  if (signal) signal.addEventListener("abort", () => controller.abort());
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `请求失败 ${res.status}`);
    }
    return await res.json();
  } catch (e) {
    if (e.name === "AbortError") throw new Error("请求超时,请检查后端服务是否在运行");
    throw e;
  } finally {
    clearTimeout(timeout);
  }
}

function renderError(msg) {
  return `<div class="error">⚠ ${msg}</div>`;
}

function renderLoading() {
  return `<div class="loading">加载中...</div>`;
}

function disposeCharts() {
  chartInstances.forEach((c) => c && c.dispose());
  chartInstances = [];
}

function esc(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function tableFromRecords(records, maxRows = 50) {
  if (!records || !records.length) return '<p class="empty">无数据</p>';
  const keys = Object.keys(records[0]);
  const rows = records.slice(0, maxRows);
  const head = keys.map((k) => `<th>${esc(k)}</th>`).join("");
  const body = rows
    .map((r) => `<tr>${keys.map((k) => `<td>${esc(r[k])}</td>`).join("")}</tr>`)
    .join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

async function loadTab(tab, symbol, force = false) {
  if (tab !== "analysis" && !force && tabCache[tab] && tabCache[tab].symbol === symbol) {
    disposeCharts();
    $("#content").innerHTML = tabCache[tab].html;
    if (tabCache[tab].afterRender) tabCache[tab].afterRender();
    return;
  }

  disposeCharts();
  $("#content").innerHTML = renderLoading();
  try {
    await loaders[tab](symbol);
  } catch (e) {
    if (e.name !== "AbortError") {
      $("#content").innerHTML = renderError(e.message);
    }
  }
}

function cacheTab(tab, symbol, html, afterRender) {
  tabCache[tab] = { symbol, html, afterRender };
}

const loaders = {
  async info(symbol) {
    const data = await fetchJSON(`/stocks/${symbol}/info`);
    const html = `<div class="info-grid">${data
      .map((d) => `<div class="info-card"><div class="label">${esc(d.item)}</div><div class="value">${esc(d.value)}</div></div>`)
      .join("")}</div>`;
    $("#content").innerHTML = html;
    cacheTab("info", symbol, html);
  },

  async history(symbol) {
    const data = await fetchJSON(`/stocks/${symbol}/history`);
    if (!data.length) {
      const html = '<p class="empty">无数据</p>';
      $("#content").innerHTML = html;
      cacheTab("history", symbol, html);
      return;
    }
    const rowsHtml = tableFromRecords(data, 200);
    const html = `
      <div id="historyChart" class="chart-container"></div>
      <details class="data-details"><summary>查看明细数据 (${data.length} 条)</summary>${rowsHtml}</details>
    `;
    $("#content").innerHTML = html;
    const afterRender = () => {
      const chart = echarts.init($("#historyChart"));
      chartInstances.push(chart);
      chart.setOption({
        tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
        legend: { data: ["K线", "成交量"], top: 5 },
        grid: [
          { left: 60, right: 30, top: 40, height: "55%" },
          { left: 60, right: 30, top: "72%", height: "18%" },
        ],
        xAxis: [
          { type: "category", data: data.map((d) => d["日期"]), scale: true, boundaryGap: false, axisLine: { onZero: false }, splitLine: { show: false }, axisLabel: { fontSize: 10 } },
          { type: "category", gridIndex: 1, data: data.map((d) => d["日期"]), axisLabel: { show: false } },
        ],
        yAxis: [
          { scale: true, splitArea: { show: true } },
          { gridIndex: 1, splitNumber: 2 },
        ],
        dataZoom: [
          { type: "inside", xAxisIndex: [0, 1] },
          { type: "slider", xAxisIndex: [0, 1], height: 18, bottom: 8 },
        ],
        series: [
          {
            name: "K线",
            type: "candlestick",
            data: data.map((d) => [parseFloat(d["开盘"]), parseFloat(d["收盘"]), parseFloat(d["最低"]), parseFloat(d["最高"])]),
            itemStyle: { color: "#dc2626", color0: "#16a34a", borderColor: "#dc2626", borderColor0: "#16a34a" },
          },
          {
            name: "成交量",
            type: "bar",
            xAxisIndex: 1,
            yAxisIndex: 1,
            data: data.map((d) => parseInt(d["成交量"]) || 0),
            itemStyle: { color: "#93c5fd" },
          },
        ],
      });
    };
    afterRender();
    cacheTab("history", symbol, html, afterRender);
  },

  async finance(symbol) {
    const data = await fetchJSON(`/stocks/${symbol}/finance`);
    const reportNames = { "资产负债表": "balance", "利润表": "profit", "现金流量表": "cashflow" };
    const tabs = Object.keys(data).filter(k => reportNames[k]);
    if (!tabs.length) {
      const html = '<p class="empty">无数据</p>';
      $("#content").innerHTML = html;
      cacheTab("finance", symbol, html);
      return;
    }

    let html = '<div class="finance-subtabs">';
    tabs.forEach((name, i) => {
      html += `<button class="finance-subtab ${i === 0 ? "active" : ""}" data-report="${name}">${name}</button>`;
    });
    html += '</div><div id="financeTable"></div>';
    $("#content").innerHTML = html;

    function renderReport(reportName) {
      const report = data[reportName];
      if (!report) return;
      const cols = report.columns;
      const rows = report.rows;
      let tableHtml = '<div class="table-scroll"><table><thead><tr>';
      cols.forEach(c => { tableHtml += `<th>${esc(c)}</th>`; });
      tableHtml += '</tr></thead><tbody>';
      rows.forEach(r => {
        const isSection = cols.slice(1).every(c => !r[c]);
        tableHtml += `<tr class="${isSection ? "section-row" : ""}">`;
        cols.forEach(c => { tableHtml += `<td>${esc(r[c] || "")}</td>`; });
        tableHtml += '</tr>';
      });
      tableHtml += '</tbody></table></div>';
      $("#financeTable").innerHTML = tableHtml;
    }

    renderReport(tabs[0]);
    document.querySelector(".finance-subtabs").addEventListener("click", (e) => {
      const btn = e.target.closest(".finance-subtab");
      if (!btn) return;
      document.querySelectorAll(".finance-subtab").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      renderReport(btn.dataset.report);
    });

    cacheTab("finance", symbol, html, () => {
      document.querySelector(".finance-subtabs")?.addEventListener("click", (e) => {
        const btn = e.target.closest(".finance-subtab");
        if (!btn) return;
        document.querySelectorAll(".finance-subtab").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        renderReport(btn.dataset.report);
      });
      renderReport(tabs[0]);
    });
  },

  async industry(symbol) {
    const data = await fetchJSON(`/stocks/${symbol}/industry`);
    const html = `
      <div class="industry-tag">所属行业: ${esc(data.industry)}</div>
      <p class="muted">股票代码: ${esc(data.symbol || symbol)}</p>
    `;
    $("#content").innerHTML = html;
    cacheTab("industry", symbol, html);
  },

  async orderbook(symbol) {
    const data = await fetchJSON(`/stocks/${symbol}/orderbook`);
    const cards = Object.entries(data)
      .map(([k, v]) => `<div class="info-card"><div class="label">${esc(k)}</div><div class="value">${esc(v)}</div></div>`)
      .join("");
    const html = `<div class="info-grid">${cards}</div>`;
    $("#content").innerHTML = html;
    cacheTab("orderbook", symbol, html);
  },

  async predict(symbol) {
    const data = await fetchJSON(`/stocks/${symbol}/predict?days=30`);
    const preds = data.predictions || [];
    const recent = data.recent_closes || [];

    const html = `
      <div class="stat-row">
        <div class="stat"><div class="label">最近收盘</div><div class="value">${data.last_close}</div></div>
        <div class="stat"><div class="label">MA5</div><div class="value">${data.ma5}</div></div>
        <div class="stat"><div class="label">MA20</div><div class="value">${data.ma20}</div></div>
        <div class="stat"><div class="label">MA60</div><div class="value">${data.ma60}</div></div>
      </div>
      <div id="predictChart" class="chart-container"></div>
      <div class="disclaimer">${esc(data.disclaimer)}</div>
    `;
    $("#content").innerHTML = html;

    const afterRender = () => {
      const chart = echarts.init($("#predictChart"));
      chartInstances.push(chart);

      const histDays = recent.map((d) => d.day);
      const histVals = recent.map((d) => d.close);
      const predDays = preds.map((_, i) => `预测+${i + 1}`);
      const predVals = [data.last_close, ...preds];
      const predLabels = ["今日", ...predDays];

      chart.setOption({
        tooltip: { trigger: "axis" },
        legend: { data: ["历史收盘", "预测走势"], bottom: 0 },
        grid: { left: 60, right: 30, top: 30, bottom: 50 },
        xAxis: { type: "category", data: [...histDays, ...predLabels], axisLabel: { fontSize: 10, interval: Math.floor((histDays.length + preds.length) / 8) } },
        yAxis: { type: "value", scale: true },
        dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 28 }],
        series: [
          {
            name: "历史收盘",
            type: "line",
            data: [...histVals, null],
            smooth: true,
            symbol: "none",
            lineStyle: { width: 2, color: "#2563eb" },
            areaStyle: { color: "rgba(37,99,235,0.1)" },
          },
          {
            name: "预测走势",
            type: "line",
            data: [null, ...Array(histDays.length - 1).fill(null), data.last_close, ...preds.slice(1)],
            smooth: true,
            symbol: "none",
            lineStyle: { width: 2, type: "dashed", color: "#dc2626" },
            areaStyle: { color: "rgba(220,38,38,0.08)" },
          },
        ],
      });
    };
    afterRender();
    cacheTab("predict", symbol, html, afterRender);
  },

  async analysis(symbol) {
    $("#content").innerHTML = `
      <div class="analysis-container">
        <div id="analysisSteps" class="analysis-steps"></div>
        <div id="analysisChart" class="chart-container" style="display:none;height:300px;"></div>
        <div id="analysisContent" class="analysis-content"></div>
      </div>`;

    const stepsEl = $("#analysisSteps");
    const contentEl = $("#analysisContent");
    const chartEl = $("#analysisChart");
    let fullText = "";

    try {
      const startRes = await fetchJSON(`/stocks/${symbol}/analysis/start`);
      const taskId = startRes.task_id;

      const poll = async () => {
        const res = await fetchJSON(`/stocks/${symbol}/analysis/poll?task_id=${taskId}`);
        for (const ev of res.events) {
          if (ev.error) {
            stepsEl.innerHTML = "";
            contentEl.innerHTML = renderError(ev.error);
            return true;
          }
          if (ev.done) {
            const items = stepsEl.querySelectorAll(".step-item.collecting");
            items.forEach(i => { i.classList.remove("collecting"); i.classList.add("done"); i.querySelector(".step-icon").textContent = "✅"; });
            contentEl.innerHTML = marked.parse(fullText);
            return true;
          }
          if (ev.step === "collect") {
            stepsEl.innerHTML += `<div class="step-item collecting"><span class="step-icon">⏳</span> ${esc(ev.label)}</div>`;
          } else if (ev.step === "done") {
            const items = stepsEl.querySelectorAll(".step-item.collecting");
            const last = items[items.length - 1];
            if (last) {
              last.classList.remove("collecting");
              last.classList.add("done");
              last.innerHTML = `<span class="step-icon">✅</span> ${esc(ev.label)}`;
            }
            if (ev.chart && ev.chart.length > 0) {
              chartEl.style.display = "block";
              const chart = echarts.init(chartEl);
              chartInstances.push(chart);
              chart.setOption({
                tooltip: { trigger: "axis" },
                grid: { left: 50, right: 20, top: 20, bottom: 30 },
                xAxis: { type: "category", data: ev.chart.map(d => d.day), axisLabel: { fontSize: 10, rotate: 30 } },
                yAxis: { type: "value", scale: true },
                dataZoom: [{ type: "inside" }, { type: "slider", height: 16, bottom: 4 }],
                series: [{
                  name: "收盘价",
                  type: "line",
                  data: ev.chart.map(d => d.close),
                  smooth: true,
                  symbol: "none",
                  lineStyle: { width: 2, color: "#2563eb" },
                  areaStyle: { color: "rgba(37,99,235,0.1)" },
                }],
              });
            }
          } else if (ev.content) {
            fullText += ev.content;
            contentEl.innerHTML = marked.parse(fullText) + '<span class="cursor"></span>';
          }
        }
        return res.done;
      };

      while (true) {
        const finished = await poll();
        if (finished) break;
        await new Promise(r => setTimeout(r, 500));
      }
    } catch (e) {
      contentEl.innerHTML = renderError(e.message);
    }
  },
};

function selectSymbol(symbol, name) {
  currentSymbol = symbol;
  currentName = name;
  tabCache = {};
  isSelecting = true;
  $("#searchResults").classList.remove("show");
  $("#symbolInput").value = `${symbol} ${name || ""}`.trim();
  setTimeout(() => { isSelecting = false; }, 100);
  $("#stockBar").style.display = "flex";
  $("#currentStockName").textContent = name ? `${name} (${symbol})` : symbol;
  $(".tab-btn.active")?.classList.remove("active");
  document.querySelector('.tab-btn[data-tab="info"]').classList.add("active");
  currentTab = "info";
  loadTab("info", symbol);
}

async function doSearch() {
  const keyword = $("#symbolInput").value.trim();
  if (!keyword || isSelecting) return;

  if (searchAbort) searchAbort.abort();
  searchAbort = new AbortController();

  $("#searchResults").classList.add("show");
  $("#searchResults").innerHTML = '<div class="item muted">搜索中...</div>';
  try {
    const data = await fetchJSON(`/search?keyword=${encodeURIComponent(keyword)}`, searchAbort.signal);
    if (!data.length) {
      $("#searchResults").innerHTML = '<div class="item muted">无匹配结果</div>';
      return;
    }
    $("#searchResults").innerHTML = data
      .map((r) =>
        `<div class="item" data-symbol="${esc(r["代码"])}" data-name="${esc(r["名称"])}"><span><span class="code">${esc(r["代码"])}</span> ${esc(r["名称"])}</span><span class="market">${esc(r["市场"] || "")}</span></div>`
      )
      .join("");
  } catch (e) {
    if (e.name !== "AbortError") {
      $("#searchResults").innerHTML = `<div class="item muted">搜索失败: ${esc(e.message)}</div>`;
    }
  }
}

let searchTimer = null;
$("#searchBtn").addEventListener("click", doSearch);
$("#symbolInput").addEventListener("input", () => {
  if (isSelecting) return;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(doSearch, 400);
});
$("#symbolInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    clearTimeout(searchTimer);
    doSearch();
  }
});

document.addEventListener("click", (e) => {
  if (!e.target.closest(".search-bar") && !e.target.closest(".search-results")) {
    $("#searchResults").classList.remove("show");
  }
});

$("#searchResults").addEventListener("click", (e) => {
  const item = e.target.closest(".item");
  if (!item || !item.dataset.symbol) return;
  selectSymbol(item.dataset.symbol, item.dataset.name);
});

$(".tabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab-btn");
  if (!btn || !currentSymbol) return;
  if (btn.dataset.tab === currentTab) return;
  $(".tab-btn.active")?.classList.remove("active");
  btn.classList.add("active");
  currentTab = btn.dataset.tab;
  loadTab(currentTab, currentSymbol);
});

window.addEventListener("resize", () => {
  chartInstances.forEach((c) => c && c.resize());
});

checkBackend();
setInterval(checkBackend, 30000);

checkBackend();
setInterval(checkBackend, 30000);

checkBackend();
setInterval(checkBackend, 30000);
