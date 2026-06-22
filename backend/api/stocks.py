import re
import requests
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

SESSION = requests.Session()
SESSION.headers.update({
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})


def _symbol_to_secid(symbol: str) -> str:
    symbol = symbol.strip()
    if symbol.startswith(("6", "9")):
        return f"1.{symbol}"
    return f"0.{symbol}"


def _symbol_to_sina(symbol: str) -> str:
    symbol = symbol.strip()
    if symbol.startswith(("6", "9")):
        return f"sh{symbol}"
    return f"sz{symbol}"


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/search")
def search_stock(keyword: str = Query(..., description="股票代码或名称关键词")):
    try:
        r = SESSION.get(
            "https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15",
            params={"key": keyword, "name": "suggestdata"},
            timeout=10,
        )
        r.raise_for_status()
        m = re.search(r'"([^"]*)"', r.text)
        if not m or not m.group(1).strip():
            return []
        import json
        results = []
        for item in m.group(1).split(";"):
            if not item.strip():
                continue
            parts = item.split(",")
            if len(parts) >= 5:
                name = parts[4].strip() or parts[0].strip()
                code = parts[2].strip()
                market = parts[3].strip()[:2].upper()
                if code and name:
                    results.append({
                        "代码": code,
                        "名称": name,
                        "市场": market,
                    })
        return results[:20]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {e}")


@router.get("/stocks/{symbol}/info")
def stock_info(symbol: str):
    try:
        sina_code = _symbol_to_sina(symbol)
        r = SESSION.get(f"https://hq.sinajs.cn/list={sina_code}", timeout=10)
        r.raise_for_status()
        m = re.search(r'"([^"]+)"', r.text)
        if not m or not m.group(1):
            raise HTTPException(status_code=404, detail="未找到该股票")
        parts = m.group(1).split(",")
        fields = [
            "名称", "今开", "昨收", "最新价", "最高", "最低",
            "买一价", "卖一价", "成交量(手)", "成交额",
        ]
        return [{"item": f, "value": v} for f, v in zip(fields, parts[:10])]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/stocks/{symbol}/history")
def stock_history(
    symbol: str,
    start_date: str = Query("20200101", description="开始日期 YYYYMMDD"),
    end_date: str = Query("20991231", description="结束日期 YYYYMMDD"),
    adjust: str = Query("qfq", description="复权类型 qfq前复权/hfq后复权/空"),
):
    try:
        r = SESSION.get(
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
            params={
                "symbol": _symbol_to_sina(symbol),
                "scale": "240",
                "ma": "no",
                "datalen": "1023",
            },
            timeout=15,
        )
        r.raise_for_status()
        import json
        data = json.loads(r.text) if r.text else []
        sd = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        ed = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
        filtered = [d for d in data if sd <= d["day"] <= ed]
        for d in filtered:
            d["日期"] = d.pop("day")
            d["开盘"] = d.pop("open")
            d["最高"] = d.pop("high")
            d["最低"] = d.pop("low")
            d["收盘"] = d.pop("close")
            d["成交量"] = d.pop("volume")
        return filtered
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/stocks/{symbol}/finance")
def stock_finance(symbol: str):
    try:
        r = SESSION.get(
            f"https://money.finance.sina.com.cn/corp/go.php/vFD_FinanceSummary/stockid/{symbol}.phtml",
            timeout=15,
        )
        r.raise_for_status()
        r.encoding = "gb2312"
        text = r.text

        tables = re.findall(r'<table[^>]*class="tbl_table[^"]*"[^>]*>(.*?)</table>', text, re.S)
        result = []
        for table in tables[:4]:
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)
            for row in rows:
                cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
                cells = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
                if len(cells) >= 2 and cells[0]:
                    result.append({"项目": cells[0], "数值": cells[1]})
        if not result:
            return [{"项目": "提示", "数值": "暂无财务数据或需访问完整页面"}]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/stocks/{symbol}/industry")
def stock_industry(symbol: str):
    try:
        r = SESSION.get(
            f"https://money.finance.sina.com.cn/corp/go.php/vCI_StockHolder/stockid/{symbol}.phtml",
            timeout=15,
        )
        r.raise_for_status()
        r.encoding = "gb2312"

        industry = None
        m = re.search(r"所属行业[：:]\s*([^<\s]+)", r.text)
        if m:
            industry = m.group(1).strip()

        if not industry:
            r2 = SESSION.get(
                f"https://hq.sinajs.cn/list={_symbol_to_sina(symbol)}",
                timeout=10,
            )
            parts = re.search(r'"([^"]+)"', r2.text)
            name = parts.group(1).split(",")[0] if parts and parts.group(1) else symbol

        return {"symbol": symbol, "industry": industry or "未知", "name": symbol}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/stocks/{symbol}/orderbook")
def stock_orderbook(symbol: str):
    try:
        sina_code = _symbol_to_sina(symbol)
        r = SESSION.get(f"https://hq.sinajs.cn/list={sina_code}", timeout=10)
        r.raise_for_status()
        m = re.search(r'"([^"]+)"', r.text)
        if not m or not m.group(1):
            raise HTTPException(status_code=404, detail="未找到该股票实时行情")
        parts = m.group(1).split(",")

        result = {
            "名称": parts[0],
            "今开": parts[1],
            "昨收": parts[2],
            "最新价": parts[3],
            "最高": parts[4],
            "最低": parts[5],
        }
        if len(parts) >= 24:
            for i in range(5):
                base = 10 + i * 2
                result[f"买{i+1}量"] = parts[base]
                result[f"买{i+1}价"] = parts[base + 1]
                sbase = 20 + i * 2
                result[f"卖{i+1}量"] = parts[sbase]
                result[f"卖{i+1}价"] = parts[sbase + 1]
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/stocks/{symbol}/predict")
def stock_predict(
    symbol: str,
    days: int = Query(30, ge=1, le=90, description="预测天数"),
):
    import numpy as np

    try:
        r = SESSION.get(
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
            params={
                "symbol": _symbol_to_sina(symbol),
                "scale": "240",
                "ma": "no",
                "datalen": "1023",
            },
            timeout=15,
        )
        r.raise_for_status()
        import json
        data = json.loads(r.text) if r.text else []
        if not data:
            raise HTTPException(status_code=404, detail="无历史数据可预测")

        closes = np.array([float(d["close"]) for d in data])

        ma5 = float(np.mean(closes[-5:])) if len(closes) >= 5 else float(np.mean(closes))
        ma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else float(np.mean(closes))
        ma60 = float(np.mean(closes[-60:])) if len(closes) >= 60 else float(np.mean(closes))

        recent = closes[-20:] if len(closes) >= 20 else closes
        drift = float(np.mean(np.diff(recent)))

        last_close = float(closes[-1])
        predictions = [round(last_close + drift * (i + 1), 2) for i in range(days)]

        recent_n = min(60, len(closes))
        recent_closes = [
            {"day": data[-recent_n + i]["day"] if "day" in data[-recent_n + i] else str(i),
             "close": round(float(closes[-recent_n + i]), 2)}
            for i in range(recent_n)
        ]

        return {
            "symbol": symbol,
            "last_close": round(last_close, 2),
            "ma5": round(ma5, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2),
            "method": "linear_drift_ma",
            "recent_closes": recent_closes,
            "predictions": predictions,
            "disclaimer": "仅基于均线与近期漂移的简化推算,不构成投资建议",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")
