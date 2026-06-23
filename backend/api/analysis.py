import os
import json
import re
import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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
LLM_BASE_URL = ENV.get("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
LLM_MODEL = ENV.get("LLM_MODEL", "deepseek-v4-pro")


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


def _build_prompt(symbol, name, realtime, history, finance, industry):
    recent = history[-60:] if len(history) >= 60 else history
    closes = [float(d["close"]) for d in recent]
    ma5 = round(sum(closes[-5:]) / 5, 2) if len(closes) >= 5 else None
    ma20 = round(sum(closes[-20:]) / 20, 2) if len(closes) >= 20 else None
    ma60 = round(sum(closes[-60:]) / 60, 2) if len(closes) >= 60 else None
    high52 = max(closes) if closes else None
    low52 = min(closes) if closes else None
    recent_30 = recent[-30:]
    change_30 = round((closes[-1] - closes[-30]) / closes[-30] * 100, 2) if len(closes) >= 30 else None

    history_text = "\n".join(
        [f"  {d['day']} 开{d['open']} 高{d['high']} 低{d['low']} 收{d['close']} 量{d['volume']}" for d in recent[-20:]]
    )
    finance_text = "\n".join([f"  {f}" for f in finance[:30]])

    return f"""你是一位专业的证券分析师，请基于以下数据对股票进行深度分析。

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

== 财务摘要 ==
{finance_text if finance_text else '  暂无财务数据'}

请输出 Markdown 格式的深度分析报告，包含以下板块（每个板块都要有实质性内容，不要泛泛而谈）：

## 一、基本面概览
用表格列出关键指标（当前价、市值估算、行业、均线位置等），并点评。

## 二、财务分析
分析营收、利润趋势、毛利率、净利率、现金流等，指出亮点与隐患。

## 三、技术面分析
分析当前价格相对均线位置、近60日区间、近期涨跌幅、量价配合，判断超买/超卖。

## 四、估值与同行对比
基于行业和财务数据，评估当前估值是否合理（PE/PB/PS 估算）。

## 五、核心逻辑与风险
列出看多逻辑（3-5条）和主要风险（3-5条），用表格呈现。

## 六、走势判断
分短期（1-3月）、中期（6-12月）、长期（1-3年）给出判断，标注关键支撑/阻力位。

## 七、投资建议
给出明确建议（适合什么类型投资者、建议操作、关注指标）。

要求：
- 数据驱动，引用具体数字
- 客观中立，既说机会也说风险
- 结尾加免责声明
"""


def _stream_llm(prompt):
    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    resp = requests.post(
        f"{LLM_BASE_URL}/chat/completions",
        headers=headers,
        json=payload,
        stream=True,
        timeout=120,
    )
    if resp.status_code != 200:
        err = resp.text[:500]
        yield f"data: {json.dumps({'error': f'LLM调用失败({resp.status_code}): {err}'}, ensure_ascii=False)}\n\n"
        return

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
                    yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
            except json.JSONDecodeError:
                continue

    yield "data: [DONE]\n\n"


@router.get("/stocks/{symbol}/analysis")
def stock_analysis(symbol: str):
    if not LLM_API_KEY:
        raise HTTPException(status_code=500, detail="未配置 LLM_API_KEY，请在 .env 中填写")

    def generate():
        import json as _json

        yield f"data: {_json.dumps({'step': 'collect', 'label': '正在获取实时行情...'}, ensure_ascii=False)}\n\n"
        try:
            realtime = _collect_realtime(symbol)
            name = realtime["名称"] if realtime else symbol
        except Exception:
            name = symbol
            realtime = None
        yield f"data: {_json.dumps({'step': 'done', 'label': f'实时行情: {name}', 'data': realtime}, ensure_ascii=False)}\n\n"

        yield f"data: {_json.dumps({'step': 'collect', 'label': '正在获取历史K线(120日)...'}, ensure_ascii=False)}\n\n"
        try:
            history = _collect_history(symbol)
        except Exception:
            history = []
        chart_data = [{"day": d["day"], "close": float(d["close"]), "volume": int(d.get("volume", 0))} for d in history[-60:]]
        yield f"data: {_json.dumps({'step': 'done', 'label': f'历史K线: {len(history)}条', 'chart': chart_data}, ensure_ascii=False)}\n\n"

        yield f"data: {_json.dumps({'step': 'collect', 'label': '正在获取财务数据...'}, ensure_ascii=False)}\n\n"
        try:
            finance = _collect_finance(symbol)
        except Exception:
            finance = []
        yield f"data: {_json.dumps({'step': 'done', 'label': f'财务数据: {len(finance)}项'}, ensure_ascii=False)}\n\n"

        yield f"data: {_json.dumps({'step': 'collect', 'label': '正在获取行业信息...'}, ensure_ascii=False)}\n\n"
        try:
            industry = _collect_industry(symbol)
        except Exception:
            industry = "未知"
        yield f"data: {_json.dumps({'step': 'done', 'label': f'行业: {industry}'}, ensure_ascii=False)}\n\n"

        yield f"data: {_json.dumps({'step': 'collect', 'label': '正在调用 AI 生成分析报告...'}, ensure_ascii=False)}\n\n"

        prompt = _build_prompt(symbol, name, realtime, history, finance, industry)
        yield from _stream_llm(prompt)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
