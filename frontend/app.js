let currentSymbol = null;

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

function tableFromRecords(records, maxRows = 50) {
  if (!records || !records.length) return "<p>无数据</p>";
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
    $("#content").innerHTML = tableFromRecords(data);
  } catch (e) {
    $("#content").innerHTML = renderError(e.message);
  }
}

async function loadHistory(symbol) {
  $("#content").innerHTML = renderLoading();
  try {
    const data = await fetchJSON(`/stocks/${symbol}/history`);
    $("#content").innerHTML = tableFromRecords(data, 100);
  } catch (e) {
    $("#content").innerHTML = renderError(e.message);
  }
}

async function loadFinance(symbol) {
  $("#content").innerHTML = renderLoading();
  try {
    const data = await fetchJSON(`/stocks/${symbol}/finance`);
    $("#content").innerHTML = tableFromRecords(data);
  } catch (e) {
    $("#content").innerHTML = renderError(e.message);
  }
}

async function loadIndustry(symbol) {
  $("#content").innerHTML = renderLoading();
  try {
    const data = await fetchJSON(`/stocks/${symbol}/industry`);
    const industry = data.industry ? `<p><strong>所属行业:</strong> ${data.industry}</p>` : "<p>未找到行业字段</p>";
    $("#content").innerHTML = industry + tableFromRecords(data.raw || []);
  } catch (e) {
    $("#content").innerHTML = renderError(e.message);
  }
}

async function loadOrderbook(symbol) {
  $("#content").innerHTML = renderLoading();
  try {
    const data = await fetchJSON(`/stocks/${symbol}/orderbook`);
    const records = Object.entries(data).map(([k, v]) => ({ item: k, value: v }));
    $("#content").innerHTML = tableFromRecords(records);
  } catch (e) {
    $("#content").innerHTML = renderError(e.message);
  }
}

async function loadPredict(symbol) {
  $("#content").innerHTML = renderLoading();
  try {
    const data = await fetchJSON(`/stocks/${symbol}/predict?days=30`);
    const preds = data.predictions || [];
    const max = Math.max(...preds, 1);
    const bars = preds
      .map((p) => `<div class="bar" style="height:${(p / max) * 100}%;" title="${p}"></div>`)
      .join("");
    $("#content").innerHTML = `
      <p><strong>最近收盘:</strong> ${data.last_close} | <strong>MA5:</strong> ${data.ma5} | <strong>MA20:</strong> ${data.ma20} | <strong>MA60:</strong> ${data.ma60}</p>
      <p><strong>方法:</strong> ${data.method}</p>
      <div class="predict-chart">${bars}</div>
      <p style="color:#888;font-size:12px;">${data.disclaimer}</p>
    `;
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
  $("#searchResults").innerHTML = "";
  $("#symbolInput").value = `${symbol} ${name || ""}`.trim();
  $(".tab-btn.active")?.classList.remove("active");
  document.querySelector('.tab-btn[data-tab="info"]').classList.add("active");
  loadInfo(symbol);
}

async function doSearch() {
  const keyword = $("#symbolInput").value.trim();
  if (!keyword) return;
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
          `<div class="item" data-symbol="${r["代码"]}" data-name="${r["名称"]}">${r["代码"]} ${r["名称"]} ¥${r["最新价"]}</div>`
      )
      .join("");
  } catch (e) {
    $("#searchResults").innerHTML = `<div class="item">搜索失败: ${e.message}</div>`;
  }
}

$("#searchBtn").addEventListener("click", doSearch);
$("#symbolInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") doSearch();
});

$("#searchResults").addEventListener("click", (e) => {
  const item = e.target.closest(".item");
  if (!item || !item.dataset.symbol) return;
  selectSymbol(item.dataset.symbol, item.dataset.name);
});

$(".tabs").addEventListener("click", (e) => {
  const btn = e.target.closest(".tab-btn");
  if (!btn || !currentSymbol) return;
  $(".tab-btn.active")?.classList.remove("active");
  btn.classList.add("active");
  tabLoaders[btn.dataset.tab]?.(currentSymbol);
});
