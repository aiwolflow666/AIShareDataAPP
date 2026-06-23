let currentSymbol=null,currentName=null,chartInstances=[],isSelecting=false,searchAbort=null,backendOnline=null,currentView="analysis",currentReport="",currentData=null;
const $=(s)=>document.querySelector(s);

async function fetchJSON(path,signal){
  const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),30000);
  if(signal)signal.addEventListener("abort",()=>controller.abort());
  try{const res=await fetch(`${window.API_BASE}${path}`,{signal:controller.signal});
    if(!res.ok){const e=await res.json().catch(()=>({}));throw new Error(e.detail||`请求失败 ${res.status}`);}
    return await res.json();
  }catch(e){if(e.name==="AbortError")throw new Error("请求超时,请检查后端是否在运行");throw e;}
  finally{clearTimeout(timeout);}
}
function esc(s){if(s==null)return"";return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function renderError(msg){return `<div class="error">⚠ ${esc(msg)}</div>`;}
function disposeCharts(){chartInstances.forEach(c=>c&&c.dispose());chartInstances=[];}
function fmt(v,suffix="",unit=""){if(v===null||v===undefined)return"--";if(typeof v==="number"){if(unit==="亿")return v.toLocaleString("zh-CN",{maximumFractionDigits:2})+" 亿";return v.toLocaleString("zh-CN",{maximumFractionDigits:2})+suffix;}return v+suffix;}

async function checkBackend(){
  try{const r=await fetch(`${window.API_BASE}/health`,{signal:AbortSignal.timeout(8000)});backendOnline=r.ok;}
  catch{backendOnline=false;}
  const b=$("#backendStatus");if(b){b.className="backend-badge "+(backendOnline?"online":"offline");b.textContent=backendOnline?"● 后端已连接":"● 后端未连接";}
}

function selectSymbol(symbol,name){
  currentSymbol=symbol;currentName=name;isSelecting=true;
  $("#searchResults").classList.remove("show");
  $("#symbolInput").value=`${symbol} ${name||""}`.trim();
  setTimeout(()=>{isSelecting=false;},100);
  switchView("analysis");startAnalysis(symbol,name);
}

async function startAnalysis(symbol,name){
  currentReport="";currentData=null;disposeCharts();
  $("#content").innerHTML=`<div class="analysis-page">
    <div class="stock-info-bar"><div><span class="stock-name-lg">${esc(name||symbol)}</span><span class="stock-code-lg">${esc(symbol)}</span></div>
    <button id="saveBtn" class="save-btn" style="display:none;" onclick="saveCurrentAnalysis()">💾 保存到历史</button></div>
    <div id="analysisSteps" class="analysis-steps"></div>
    <div id="analysisChart" class="chart-container" style="display:none;"></div>
    <div id="analysisMetrics" class="metrics-section"></div>
    <div id="analysisContent" class="analysis-content"></div></div>`;

  const stepsEl=$("#analysisSteps"),contentEl=$("#analysisContent"),chartEl=$("#analysisChart"),metricsEl=$("#analysisMetrics");
  let fullText="",chartData=null,financeSummary=null,realtimeData=null;

  try{
    const startRes=await fetchJSON(`/stocks/${symbol}/analysis/start`);
    const taskId=startRes.task_id;
    const poll=async()=>{
      const res=await fetchJSON(`/stocks/${symbol}/analysis/poll?task_id=${taskId}`);
      for(const ev of res.events){
        if(ev.error){stepsEl.innerHTML="";contentEl.innerHTML=renderError(ev.error);return true;}
        if(ev.done){
          stepsEl.querySelectorAll(".step-item.collecting").forEach(i=>{i.classList.remove("collecting");i.classList.add("done");i.querySelector(".step-icon").textContent="✅";});
          contentEl.innerHTML=marked.parse(fullText);
          currentReport=fullText;
          currentData={symbol,name,chartData,financeSummary,realtime:realtimeData};
          const btn=$("#saveBtn");if(btn)btn.style.display="inline-block";
          return true;
        }
        if(ev.step==="collect"){stepsEl.innerHTML+=`<div class="step-item collecting"><span class="step-icon">⏳</span> ${esc(ev.label)}</div>`;}
        else if(ev.step==="done"){
          const items=stepsEl.querySelectorAll(".step-item.collecting");const last=items[items.length-1];
          if(last){last.classList.remove("collecting");last.classList.add("done");last.innerHTML=`<span class="step-icon">✅</span> ${esc(ev.label)}`;}
          if(ev.chart&&ev.chart.length>0){
            chartData=ev.chart;chartEl.style.display="block";
            const chart=echarts.init(chartEl);chartInstances.push(chart);
            chart.setOption({tooltip:{trigger:"axis"},grid:{left:50,right:20,top:20,bottom:30},
              xAxis:{type:"category",data:chartData.map(d=>d.day),axisLabel:{fontSize:10,rotate:30}},
              yAxis:{type:"value",scale:true},
              dataZoom:[{type:"inside"},{type:"slider",height:16,bottom:4}],
              series:[{name:"收盘价",type:"line",data:chartData.map(d=>d.close),smooth:true,symbol:"none",lineStyle:{width:2,color:"#2563eb"},areaStyle:{color:"rgba(37,99,235,0.1)"}}]});
          }
          if(ev.data)realtimeData=ev.data;
        }
        else if(ev.content){fullText+=ev.content;contentEl.innerHTML=marked.parse(fullText)+'<span class="cursor"></span>';}
      }
      return res.done;
    };
    while(true){const f=await poll();if(f)break;await new Promise(r=>setTimeout(r,600));}
    try{financeSummary=await fetchJSON(`/stocks/${symbol}/finance_summary`);renderMetrics(metricsEl,financeSummary);
      if(currentData)currentData.financeSummary=financeSummary;
    }catch{}
  }catch(e){contentEl.innerHTML=renderError(e.message);}
}

function renderMetrics(el,s){
  if(!s){el.innerHTML="";return;}
  let h="";
  if(s.revenue_profit_trend){const t=s.revenue_profit_trend;
    h+=`<div class="metric-group"><h4>营收与利润</h4><div class="metric-cards">`;
    h+=`<div class="metric-card"><div class="m-label">最新营收</div><div class="m-value">${fmt(t.revenue,"","亿")}</div></div>`;
    h+=`<div class="metric-card"><div class="m-label">营收同比</div><div class="m-value ${t.revenue_yoy>0?"green":"red"}">${fmt(t.revenue_yoy,"%")}</div></div>`;
    h+=`<div class="metric-card"><div class="m-label">净利润</div><div class="m-value">${fmt(t.net_profit,"","亿")}</div></div>`;
    h+=`<div class="metric-card"><div class="m-label">净利同比</div><div class="m-value ${t.net_profit_yoy>0?"green":"red"}">${fmt(t.net_profit_yoy,"%")}</div></div>`;
    h+=`<div class="metric-card"><div class="m-label">EPS</div><div class="m-value">${fmt(t.eps)}</div></div>`;
    h+=`</div></div>`;}
  if(s.profitability){const p=s.profitability;
    h+=`<div class="metric-group"><h4>盈利能力</h4><div class="metric-cards">`;
    h+=`<div class="metric-card"><div class="m-label">毛利率</div><div class="m-value">${fmt(p.gross_margin,"%")}</div></div>`;
    h+=`<div class="metric-card"><div class="m-label">净利率</div><div class="m-value">${fmt(p.net_margin,"%")}</div></div>`;
    h+=`<div class="metric-card"><div class="m-label">ROE</div><div class="m-value">${fmt(p.roe,"%")}</div></div>`;
    h+=`<div class="metric-card"><div class="m-label">ROA</div><div class="m-value">${fmt(p.roa,"%")}</div></div>`;
    h+=`</div></div>`;}
  if(s.solvency){const sol=s.solvency;
    h+=`<div class="metric-group"><h4>偿债能力</h4><div class="metric-cards">`;
    h+=`<div class="metric-card"><div class="m-label">流动比率</div><div class="m-value">${fmt(sol.current_ratio)}</div></div>`;
    h+=`<div class="metric-card"><div class="m-label">速动比率</div><div class="m-value">${fmt(sol.quick_ratio)}</div></div>`;
    h+=`<div class="metric-card"><div class="m-label">资产负债率</div><div class="m-value">${fmt(s.balance_sheet?.debt_ratio,"%")}</div></div>`;
    h+=`</div></div>`;}
  if(s.capm){const c=s.capm;
    h+=`<div class="metric-group"><h4>CAPM 模型</h4><div class="metric-cards">`;
    h+=`<div class="metric-card"><div class="m-label">Beta</div><div class="m-value">${fmt(c.beta)}</div></div>`;
    h+=`<div class="metric-card highlight"><div class="m-label">预期收益率</div><div class="m-value">${c.expected_return}%</div></div>`;
    h+=`</div></div>`;}
  el.innerHTML=h;
}

function getHistory(){try{return JSON.parse(localStorage.getItem("stock_analysis_history")||"[]");}catch{return[];}}
function saveCurrentAnalysis(){
  if(!currentReport||!currentSymbol)return;
  const now=new Date();
  const history=getHistory();
  const record={id:now.getTime().toString(),symbol:currentSymbol,name:currentName||currentSymbol,
    timestamp:now.toISOString(),displayDate:`${now.getMonth()+1}-${now.getDate()}`,
    displayTime:`${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}`,
    price:currentData?.realtime?.["最新价"]||null,
    report:currentReport,chartData:currentData?.chartData||null,
    financeSummary:currentData?.financeSummary||null,realtime:currentData?.realtime||null};
  history.unshift(record);
  if(history.length>50)history.splice(50);
  localStorage.setItem("stock_analysis_history",JSON.stringify(history));
  updateHistoryCount();
  const btn=$("#saveBtn");if(btn){btn.textContent="✅ 已保存";btn.disabled=true;}
}
function updateHistoryCount(){
  const count=getHistory().length;const badge=$("#historyCount");
  if(badge){badge.textContent=count;badge.style.display=count>0?"inline-block":"none";}
}
function renderHistory(){
  const history=getHistory();
  if(!history.length){$("#content").innerHTML=`<div class="placeholder"><div class="placeholder-icon">📋</div><p>暂无历史记录</p><p class="muted">完成 AI 分析后点击"保存到历史"即可记录</p></div>`;return;}
  const grouped={};
  history.forEach(r=>{const k=r.displayDate;if(!grouped[k])grouped[k]=[];grouped[k].push(r);});
  let html=`<div class="history-page"><div class="history-toolbar"><button class="danger-btn" onclick="clearHistory()">🗑 清空全部</button></div>`;
  for(const[date,records]of Object.entries(grouped)){
    html+=`<div class="history-date">${esc(date)}</div>`;
    for(const r of records){
      const snippet=r.report.substring(0,80).replace(/[#*]/g,"").trim()+"...";
      html+=`<div class="history-card" onclick="viewHistory('${r.id}')">
        <div class="hc-main"><span class="hc-name">${esc(r.name)}</span><span class="hc-code">${esc(r.symbol)}</span><span class="hc-time">${esc(r.displayTime)}</span>${r.price?`<span class="hc-price">¥${esc(r.price)}</span>`:""}</div>
        <div class="hc-snippet">${esc(snippet)}</div>
        <button class="hc-del" onclick="event.stopPropagation();deleteHistory('${r.id}')">✕</button></div>`;
    }
  }
  html+=`</div>`;$("#content").innerHTML=html;
}
function viewHistory(id){
  const history=getHistory();const record=history.find(r=>r.id===id);if(!record)return;
  disposeCharts();
  let metricsHtml="";if(record.financeSummary){const tmp=document.createElement("div");renderMetrics(tmp,record.financeSummary);metricsHtml=tmp.innerHTML;}
  $("#content").innerHTML=`<div class="analysis-page">
    <div class="snapshot-banner">📸 历史快照 — ${esc(record.name)} ${esc(record.displayDate)} ${esc(record.displayTime)} ${record.price?"¥"+esc(record.price):""}</div>
    ${record.chartData?'<div id="histChart" class="chart-container"></div>':""}
    <div class="metrics-section">${metricsHtml}</div>
    <div class="analysis-content">${marked.parse(record.report)}</div>
    <div class="history-actions"><button class="btn" onclick="renderHistory()">← 返回列表</button><button class="btn" onclick="rerunAnalysis('${esc(record.symbol)}','${esc(record.name)}')">🔄 重新分析</button></div></div>`;
  if(record.chartData){const chartEl=$("#histChart");if(chartEl){const chart=echarts.init(chartEl);chartInstances.push(chart);
    chart.setOption({tooltip:{trigger:"axis"},grid:{left:50,right:20,top:20,bottom:30},
      xAxis:{type:"category",data:record.chartData.map(d=>d.day),axisLabel:{fontSize:10,rotate:30}},
      yAxis:{type:"value",scale:true},dataZoom:[{type:"inside"},{type:"slider",height:16,bottom:4}],
      series:[{name:"收盘价",type:"line",data:record.chartData.map(d=>d.close),smooth:true,symbol:"none",lineStyle:{width:2,color:"#2563eb"},areaStyle:{color:"rgba(37,99,235,0.1)"}}]});}}
}
function deleteHistory(id){let h=getHistory();h=h.filter(r=>r.id!==id);localStorage.setItem("stock_analysis_history",JSON.stringify(h));updateHistoryCount();renderHistory();}
function clearHistory(){if(!confirm("确定清空所有历史记录?"))return;localStorage.removeItem("stock_analysis_history");updateHistoryCount();renderHistory();}
function rerunAnalysis(symbol,name){currentSymbol=symbol;currentName=name;switchView("analysis");startAnalysis(symbol,name);}
function switchView(view){currentView=view;disposeCharts();document.querySelectorAll(".nav-btn").forEach(b=>b.classList.remove("active"));document.querySelector(`.nav-btn[data-view="${view}"]`)?.classList.add("active");if(view==="history")renderHistory();}

let searchTimer=null;
async function doSearch(){
  const keyword=$("#symbolInput").value.trim();if(!keyword||isSelecting)return;
  if(searchAbort)searchAbort.abort();searchAbort=new AbortController();
  $("#searchResults").classList.add("show");
  $("#searchResults").innerHTML='<div class="item muted">搜索中...</div>';
  try{
    const data=await fetchJSON(`/search?keyword=${encodeURIComponent(keyword)}`,searchAbort.signal);
    if(!data.length){$("#searchResults").innerHTML='<div class="item muted">无匹配结果</div>';return;}
    $("#searchResults").innerHTML=data.map(r=>`<div class="item" data-symbol="${esc(r["代码"])}" data-name="${esc(r["名称"])}"><span><span class="code">${esc(r["代码"])}</span> ${esc(r["名称"])}</span><span class="market">${esc(r["市场"]||"")}</span></div>`).join("");
  }catch(e){if(e.name!=="AbortError")$("#searchResults").innerHTML=`<div class="item muted">搜索失败: ${esc(e.message)}</div>`;}
}

$("#searchBtn").addEventListener("click",doSearch);
$("#symbolInput").addEventListener("input",()=>{if(isSelecting)return;clearTimeout(searchTimer);searchTimer=setTimeout(doSearch,400);});
$("#symbolInput").addEventListener("keydown",e=>{if(e.key==="Enter"){clearTimeout(searchTimer);doSearch();}});
document.addEventListener("click",e=>{if(!e.target.closest(".search-bar")&&!e.target.closest(".search-results"))$("#searchResults").classList.remove("show");});
$("#searchResults").addEventListener("click",e=>{const item=e.target.closest(".item");if(!item||!item.dataset.symbol)return;selectSymbol(item.dataset.symbol,item.dataset.name);});
document.querySelector(".main-nav").addEventListener("click",e=>{const btn=e.target.closest(".nav-btn");if(!btn)return;switchView(btn.dataset.view);});
window.addEventListener("resize",()=>{chartInstances.forEach(c=>c&&c.resize());});

checkBackend();updateHistoryCount();
