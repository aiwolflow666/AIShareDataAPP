let currentSymbol = null;
let currentName = null;
let chartInstances = [];

const $ = (sel) => document.querySelector(sel);

async function fetchJSON(path) {
  const url = `${window.API_BASE}${path}`;
  const res = await fetch(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `请求失败 ${res.status}`);
  }
  return res.json();
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

function tableFromRecords(records, maxRows = 50) {
  if (!records || !records.length) return '<p style="color:#6b7280;text-align:center;padding:24px;">无数据</p>';
  const keys = Object.keys(records[0]);
  const rows = records.slice(0, maxRows);
  const head = keys.map((k) => `<th>${k}</th>`).join("");
  const body = rows
    .map((r) => `<tr>${keys.map((k) => `<td>${r[k] ?? ""}</td>`).join("")}</tr>`)
    .join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

async function loadInfo(symbol) {
  $("#content").innerHTML = renderLoading();
  try {
    const data = await fetchJSON(`/stocks/${symbol}/info`);
    const html = data
      .map(
        (d) =>
          `<div class="info-card"><div class="label">${d.item}</div><div class="value">${d.value}</div></div>`
      )
      .join("");
    $("#content").innerHTML = `<div class="info-grid">${html}</div>`;
  } catch (e) {
    $("#content").innerHTML = renderError(e.message);
  }
}

async function loadHistory(symbol) {
  $("#content").innerHTML = renderLoading();
  try {
    const data = await fetchJSON(`/stocks/${symbol}/history`);
    if (!data.length) {
      $("#content").innerHTML = '<p style="color:#6b7280;text-align:center;padding:24px;">无数据</p>';
      return;
    }
    const rowsHtml = tableFromRecords(data, 200);

    $("#content").innerHTML = `
      <div id="historyChart" class="chart-container"></div>
      <h3 style="margin:16px 0 8px;font-size:15px;">明细数据</h3>
      ${rowsHtml}
    `;

    const chart = echarts.init($("#historyChart"));
    chartInstances.push(chart);
    chart.setOption({
      title: { text: "历史收盘价", left: "center", textStyle: { fontSize: 14 } },
      tooltip: { trigger: "axis" },
      grid: { left: 60, right: 30, top: 40, bottom: 40 },
      xAxis: {
        type: "category",
        data: data.map((d) => d["日期"]),
        axisLabel: { fontSize: 10, rotate: 30 },
      },
      yAxis: { type: "value", scale: true },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 8 }],
      series: [
        {
          name: "收盘价",
          type: "line",
          data: data.map((d) => parseFloat(d["收盘"])),
          smooth: true,
          symbol: "none",
          lineStyle: { width: 2, color: "#2563eb" },
          areaStyle: { color: "rgba(37,99,235,0.1)" },
        },
      ],
    });
  } catch (e) {
    $("#content").innerHTML = renderError(e.message);
  }
}

async function loadFinance(symbol) {
  $("#content").innerHTML = renderLoading();
  try {
    const data = await fetchJSON(`/stocks/${symbol}/finance`);
    $("#content").innerHTML = `<h3 style="margin-bottom:12px;font-size:15px;">财务摘要</h3>${tableFromRecords(data, 100)}`;
  } catch (e) {
    $("#content").innerHTML = renderError(e.message);
  }
}

async function loadIndustry(symbol) {
  $("#content").innerHTML = renderLoading();
  try {
    const data = await fetchJSON(`/stocks/${symbol}/industry`);
    $("#content").innerHTML = `
      <div class="industry-tag">所属行业: ${data.industry}</div>
      <p style="color:#6b7280;">股票代码: ${data.symbol || symbol}</p>
    `;
  } catch (e) {
    $("#content").innerHTML = renderError(e.message);
  }
}

async function loadOrderbook(symbol) {
  $("#content").innerHTML = renderLoading();
  try {
    const data = await fetchJSON(`/stocks/${symbol}/orderbook`);
    const cards = Object.entries(data)
      .map(([k, v]) => `<div class="info-card"><div class="label">${k}</div><div class="value">${v}</div></div>`)
      .join("");
    $("#content").innerHTML = `<div class="info-grid">${cards}</div>`;
  } catch (e) {
    $("#content").innerHTML = renderError(e.message);
  }
}

async function loadPredict(symbol) {
  $("#content").innerHTML = renderLoading();
  try {
    const data = await fetchJSON(`/stocks/${symbol}/predict?days=30`);
    const preds = data.predictions || [];

    $("#content").innerHTML = `
      <div class="stat-row">
        <div class="stat"><div class="label">最近收盘</div><div class="value">${data.last_close}</div></div>
        <div class="stat"><div class="label">MA5</div><div class="value">${data.ma5}</div></div>
        <div class="stat"><div class="label">MA20</div><div class="value">${data.ma20}</div></div>
        <div class="stat"><div class="label">MA60</div><div class="value">${data.ma60}</div></div>
      </div>
      <div id="predictChart" class="chart-container"></div>
      <div class="disclaimer">${data.disclaimer}</div>
    `;

    const chart = echarts.init($("#predictChart"));
    chartInstances.push(chart);

    const baseLine = Array(preds.length).fill(data.last_close);
    chart.setOption({
      title: { text: "未来 30 天预测走势", left: "center", textStyle: { fontSize: 14 } },
      tooltip: { trigger: "axis" },
      legend: { data: ["预测价", "当前价"], bottom: 0 },
      grid: { left: 60, right: 30, top: 40, bottom: 50 },
      xAxis: { type: "category", data: preds.map((_, i) => `第${i + 1}天`) },
      yAxis: { type: "value", scale: true },
      series: [
        {
          name: "预测价",
          type: "line",
          data: preds,
          smooth: true,
          symbol: "none",
          lineStyle: { width: 2, color: "#dc2626" },
          areaStyle: { color: "rgba(220,38,38,0.1)" },
        },
        {
          name: "当前价",
          type: "line",
          data: baseLine,
          symbol: "none",
          lineStyle: { width: 1, type: "dashed", color: "#9ca3af" },
        },
      ],
    });
  } catch (e) {
    $("#content").innerHTML = renderError(e.message);
  }
}

const tabLoaders = {
  info: loadInfo,
  history: loadHistory,
  finance: loadFinance,
  industry: loadIndustry,
  orderbook: loadOrderbook,
  predict: loadPredict,
};

function selectSymbol(symbol, name) {
  currentSymbol = symbol;
  currentName = name;
  disposeCharts();
  $("#searchResults").classList.remove("show");
  $("#symbolInput").value = `${symbol} ${name || ""}`.trim();
  $("#stockBar").style.display = "flex";
  $("#currentStockName").textContent = name || symbol;
  $(".tab-btn.active")?.classList.remove("active");
  document.querySelector('.tab-btn[data-tab="info"]').classList.add("active");
  loadInfo(symbol);
}

let searchTimer = null;
async function doSearch() {
  const keyword = $("#symbolInput").value.trim();
  if (!keyword) return;
  $("#searchResults").classList.add("show");
  $("#searchResults").innerHTML = '<div class="item">搜索中...</div>';
  try {
    const data = await fetchJSON(`/search?keyword=${encodeURIComponent(keyword)}`);
    if (!data.length) {
      $("#searchResults").innerHTML = '<div class="item">无匹配结果</div>';
      return;
    }
    $("#searchResults").innerHTML = data
      .map(
        (r) =>
          `<div class="item" data-symbol="${r["代码"]}" data-name="${r["名称"]}"><span><span class="code">${r["代码"]}</span> ${r["名称"]}</span><span class="price">${r["最新价"] || ""}</span></div>`
      )
      .join("");
  } catch (e) {
    $("#searchResults").innerHTML = `<div class="item">搜索失败: ${e.message}</div>`;
  }
}

$("#searchBtn").addEventListener("click", doSearch);
$("#symbolInput").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(doSearch, 350);
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
  disposeCharts();
  $(".tab-btn.active")?.classList.remove("active");
  btn.classList.add("active");
  tabLoaders[btn.dataset.tab]?.(currentSymbol);
});

window.addEventListener("resize", () => {
  chartInstances.forEach((c) => c && c.resize());
});
