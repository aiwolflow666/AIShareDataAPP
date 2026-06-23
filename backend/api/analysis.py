import os
import json
import re
import uuid
import threading
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from .stocks import SESSION, _symbol_to_sina

router = APIRouter()

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_env():
    env = {}
    env_path = os.path.join(_BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


ENV = _load_env()
LLM_API_KEY = ENV.get("LLM_API_KEY", "")
LLM_BASE_URL = ENV.get("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding/v3")
LLM_MODEL = ENV.get("LLM_MODEL", "deepseek-v4-pro")

_tasks = {}


def _collect_realtime(symbol):
    sina_code = _symbol_to_sina(symbol)
    r = SESSION.get(f"https://hq.sinajs.cn/list={sina_code}", timeout=10)
    r.raise_for_status()
    m = re.search(r'"([^"]+)"', r.text)
    if not m or not m.group(1):
        return None
    parts = m.group(1).split(",")
    return {
        "名称": parts[0],
        "今开": parts[1],
        "昨收": parts[2],
        "最新价": parts[3],
        "最高": parts[4],
        "最低": parts[5],
        "成交量(手)": str(int(parts[8]) // 100) if parts[8].isdigit() else parts[8],
        "成交额": parts[9],
    }


def _collect_history(symbol, datalen=120):
    r = SESSION.get(
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
        params={"symbol": _symbol_to_sina(symbol), "scale": "240", "ma": "no", "datalen": str(datalen)},
        timeout=15,
    )
    r.raise_for_status()
    data = json.loads(r.text) if r.text else []
    return data


def _collect_finance(symbol):
    r = SESSION.get(
        f"https://money.finance.sina.com.cn/corp/go.php/vFD_FinanceSummary/stockid/{symbol}.phtml",
        timeout=15,
    )
    r.raise_for_status()
    r.encoding = "gb2312"
    tables = re.findall(r'<table[^>]*class="tbl_table[^"]*"[^>]*>(.*?)</table>', r.text, re.S)
    result = []
    for table in tables[:4]:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
        for row in rows:
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            if len(cells) >= 2 and cells[0]:
                result.append(f"{cells[0]}: {cells[1]}")
    return result


def _collect_industry(symbol):
    r = SESSION.get(
        f"https://money.finance.sina.com.cn/corp/go.php/vCI_StockHolder/stockid/{symbol}.phtml",
        timeout=15,
    )
    r.raise_for_status()
    r.encoding = "gb2312"
    m = re.search(r"所属行业[：:]\s*([^<\s]+)", r.text)
    return m.group(1).strip() if m else "未知"


def _build_prompt(symbol, name, realtime, history, finance_summary, industry):
    recent = history[-60:] if len(history) >= 60 else history
    closes = [float(d["close"]) for d in recent]
    ma5 = round(sum(closes[-5:]) / 5, 2) if len(closes) >= 5 else None
    ma20 = round(sum(closes[-20:]) / 20, 2) if len(closes) >= 20 else None
    ma60 = round(sum(closes[-60:]) / 60, 2) if len(closes) >= 60 else None
    high52 = max(closes) if closes else None
    low52 = min(closes) if closes else None
    change_30 = round((closes[-1] - closes[-30]) / closes[-30] * 100, 2) if len(closes) >= 30 else None

    history_text = "\n".join(
        [f"  {d['day']} 开{d['open']} 高{d['high']} 低{d['low']} 收{d['close']} 量{d['volume']}" for d in recent[-20:]]
    )

    fs_text = "暂无财务归纳数据"
    if finance_summary:
        parts = []
        rpt = finance_summary.get("revenue_profit_trend", {})
        if rpt:
            parts.append(f"营收与利润趋势: 最新营收{rpt.get('revenue','?')}亿(同比{rpt.get('revenue_yoy','?')}%), 净利润{rpt.get('net_profit','?')}亿(同比{rpt.get('net_profit_yoy','?')}%), EPS {rpt.get('eps','?')}, 报告期{finance_summary.get('latest_period','?')}")
        prof = finance_summary.get("profitability", {})
        if prof:
            parts.append(f"盈利能力: 毛利率{prof.get('gross_margin','?')}%, 净利率{prof.get('net_margin','?')}%, ROE {prof.get('roe','?')}%, ROA {prof.get('roa','?')}%, 营业利润率{prof.get('operating_margin','?')}%")
        bs = finance_summary.get("balance_sheet", {})
        if bs:
            parts.append(f"资产负债: 总资产{bs.get('total_assets','?')}亿, 总负债{bs.get('total_liabilities','?')}亿, 股东权益{bs.get('equity','?')}亿, 资产负债率{bs.get('debt_ratio','?')}%")
        sol = finance_summary.get("solvency", {})
        if sol:
            parts.append(f"偿债能力: 流动比率{sol.get('current_ratio','?')}, 速动比率{sol.get('quick_ratio','?')}, 产权比率{sol.get('debt_to_equity','?')}, 现金比率{sol.get('cash_ratio','?')}")
        capm = finance_summary.get("capm")
        if capm:
            parts.append(f"CAPM模型: Rf={capm.get('rf')}%, Rm={capm.get('rm')}%, Beta={capm.get('beta')}, 预期收益率={capm.get('expected_return')}%")
        risks = finance_summary.get("risk_signals", [])
        if risks:
            parts.append("风险信号: " + "; ".join([f"{r['signal']}({r['severity']})" for r in risks]))
        fc = finance_summary.get("forecast")
        if fc:
            parts.append(f"盈利预测: 增速{fc.get('growth_rate')}%, 预测净利润{fc.get('next_year_net_profit','?')}, {fc.get('method','')}")
        fs_text = "\n".join([f"  {p}" for p in parts])

    return f"""你是一位专业的证券分析师，请基于以下最新数据对股票进行深度分析。

股票代码: {symbol}
股票名称: {name}
所属行业: {industry}

== 实时行情 ==
{json.dumps(realtime, ensure_ascii=False, indent=2) if realtime else '无数据'}

== 均线与技术指标 ==
MA5: {ma5} | MA20: {ma20} | MA60: {ma60}
近60日最高: {high52} | 近60日最低: {low52}
近30日涨跌幅: {change_30}%

== 最近20日K线数据 ==
{history_text}

== 财务归纳指标 (数据源: akshare, 报告期见上) ==
{fs_text}

请输出 Markdown 格式的深度分析报告，包含以下板块（每个板块都要有实质性内容，引用上面的具体数字，不要泛泛而谈）：

## 一、基本面概览
用表格列出关键指标（当前价、行业、报告期、营收、净利润、EPS等），并点评。

## 二、营收与利润趋势
分析营收和净利润的同比变化，判断成长性是加速还是放缓。

## 三、盈利能力分析
分析毛利率、净利率、ROE、ROA，与行业平均水平对比，评估盈利质量。

## 四、资产负债与偿债能力
分析资产负债率、流动比率、速动比率，评估财务安全性和偿债风险。

## 五、技术面分析
分析当前价格相对均线位置、近60日区间、近期涨跌幅、量价配合，判断超买/超卖。

## 六、CAPM 模型与估值
基于 CAPM 预期收益率评估当前估值是否合理，结合 PE/PB 推算（如有数据）。

## 七、风险信号
列出已检测到的风险信号，并补充其他潜在风险，用表格呈现。

## 八、盈利预测与走势判断
基于盈利预测数据，分短期（1-3月）、中期（6-12月）、长期（1-3年）给出判断，标注关键支撑/阻力位。

## 九、投资建议
给出明确建议（适合什么类型投资者、建议操作、关注指标）。

要求：
- 数据驱动，引用具体数字
- 客观中立，既说机会也说风险
- 结尾加免责声明
"""


def _run_analysis(task_id, symbol):
    task = _tasks[task_id]
    try:
        task["events"].append({"step": "collect", "label": "正在获取实时行情..."})
        try:
            realtime = _collect_realtime(symbol)
            name = realtime["名称"] if realtime else symbol
        except Exception:
            name = symbol
            realtime = None
        task["events"].append({"step": "done", "label": f"实时行情: {name}", "data": realtime})

        task["events"].append({"step": "collect", "label": "正在获取历史K线(120日)..."})
        try:
            history = _collect_history(symbol)
        except Exception:
            history = []
        chart_data = [{"day": d["day"], "close": float(d["close"]), "volume": int(d.get("volume", 0))} for d in history[-60:]]
        task["events"].append({"step": "done", "label": f"历史K线: {len(history)}条", "chart": chart_data})

        task["events"].append({"step": "collect", "label": "正在获取财务归纳数据(akshare)..."})
        try:
            from .stocks import stock_finance_summary
            finance_summary = stock_finance_summary(symbol)
            label = f"财务归纳: 营收{finance_summary.get('revenue_profit_trend',{}).get('revenue','?')}亿 净利{finance_summary.get('revenue_profit_trend',{}).get('net_profit','?')}亿"
        except Exception:
            finance_summary = None
            label = "财务归纳: 获取失败"
        task["events"].append({"step": "done", "label": label})

        task["events"].append({"step": "collect", "label": "正在获取行业信息..."})
        try:
            industry = _collect_industry(symbol)
        except Exception:
            industry = "未知"
        task["events"].append({"step": "done", "label": f"行业: {industry}"})

        task["events"].append({"step": "collect", "label": "正在调用 AI 生成分析报告..."})

        prompt = _build_prompt(symbol, name, realtime, history, finance_summary, industry)

        headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "temperature": 0.7,
            "max_tokens": 4096,
        }
        resp = requests.post(f"{LLM_BASE_URL}/chat/completions", headers=headers, json=payload, stream=True, timeout=120)
        if resp.status_code != 200:
            task["events"].append({"error": f"LLM调用失败({resp.status_code}): {resp.text[:300]}"})
            task["done"] = True
            return

        resp.encoding = "utf-8"
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                chunk = line[6:]
                if chunk.strip() == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        task["events"].append({"content": content})
                except json.JSONDecodeError:
                    continue

        task["events"].append({"done": True})
        task["done"] = True
    except Exception as e:
        task["events"].append({"error": str(e)})
        task["done"] = True


@router.get("/stocks/{symbol}/analysis/start")
def analysis_start(symbol: str):
    if not LLM_API_KEY:
        raise HTTPException(status_code=500, detail="未配置 LLM_API_KEY，请在 .env 中填写")
    task_id = str(uuid.uuid4())[:8]
    _tasks[task_id] = {"events": [], "done": False, "cursor": 0}
    t = threading.Thread(target=_run_analysis, args=(task_id, symbol), daemon=True)
    t.start()
    return JSONResponse(content={"task_id": task_id}, media_type="application/json; charset=utf-8")


@router.get("/stocks/{symbol}/analysis/poll")
def analysis_poll(symbol: str, task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    new_events = task["events"][task["cursor"]:]
    task["cursor"] = len(task["events"])
    return JSONResponse(content={"events": new_events, "done": task["done"]}, media_type="application/json; charset=utf-8")
