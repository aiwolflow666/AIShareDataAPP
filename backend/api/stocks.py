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


def _parse_report_table(html, report_name):
    tables = re.findall(r'<table[^>]*>(.*?)</table>', html, re.S)
    for t in tables:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', t, re.S)
        if len(rows) <= 5:
            continue
        header_cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', rows[1], re.S) if len(rows) > 1 else []
        header_cells = [re.sub(r'<[^>]+>', '', c).strip() for c in header_cells]
        if not header_cells or '报表日期' not in header_cells[0]:
            continue

        columns = header_cells
        data_rows = []
        for row in rows[2:]:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.S)
            cells = [re.sub(r'<[^>]+>', '', c).strip().replace('&nbsp;', '') for c in cells]
            if not cells or not cells[0]:
                continue
            row_data = {}
            for j, col in enumerate(columns):
                row_data[col] = cells[j] if j < len(cells) else ""
            data_rows.append(row_data)

        if data_rows:
            return {"columns": columns, "rows": data_rows}
    return None


@router.get("/stocks/{symbol}/finance")
def stock_finance(symbol: str):
    import json as _json

    reports = {
        "资产负债表": "vFD_BalanceSheet",
        "利润表": "vFD_ProfitStatement",
        "现金流量表": "vFD_CashFlow",
    }
    result = {}
    for name, page in reports.items():
        try:
            r = SESSION.get(
                f"https://money.finance.sina.com.cn/corp/go.php/{page}/stockid/{symbol}/ctrl/2024/displaytype/4.phtml",
                timeout=15,
            )
            r.raise_for_status()
            r.encoding = "gb2312"
            parsed = _parse_report_table(r.text, name)
            if parsed:
                result[name] = parsed
        except Exception:
            pass

    if not result:
        raise HTTPException(status_code=404, detail="暂无财务数据")
    return result



def _ak_financial_value(df, indicator, col=None):
    for _, row in df.iterrows():
        if row["指标"] == indicator:
            if col and col in df.columns:
                v = row[col]
            else:
                v = None
                for c in df.columns[2:]:
                    v = row[c]
                    if v is not None and str(v) not in ("nan", ""):
                        break
            if v is None or str(v) in ("nan", ""):
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None
    return None


@router.get("/stocks/{symbol}/finance_summary")
def stock_finance_summary(symbol: str):
    import numpy as np
    import akshare as ak

    try:
        df = ak.stock_financial_abstract(symbol=symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"akshare 获取财务数据失败: {e}")

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="暂无财务数据")

    cols = list(df.columns)
    recent_cols = [c for c in cols[2:] if c]
    latest = recent_cols[0] if recent_cols else None
    prev = recent_cols[1] if len(recent_cols) > 1 else latest
    year_ago = recent_cols[4] if len(recent_cols) > 4 else None

    def val(indicator, col=latest):
        return _ak_financial_value(df, indicator, col)

    revenue = val("营业总收入")
    revenue_prev = val("营业总收入", prev)
    revenue_ya = val("营业总收入", year_ago) if year_ago else None
    net_profit = val("归母净利润")
    net_profit_prev = val("归母净利润", prev)
    net_profit_ya = val("归母净利润", year_ago) if year_ago else None
    op_cashflow = val("经营活动产生的现金流量净额")
    eps = val("基本每股收益")
    equity = val("股东权益合计(净资产)")

    gross_margin = val("毛利率")
    net_margin = val("销售净利率") or val("净利率")
    roe = val("净资产收益率(ROE)") or val("净资产收益率")
    roa = val("总资产报酬率") or val("总资产净利率")
    operating_margin = val("营业利润率")

    current_ratio = val("流动比率")
    quick_ratio = val("速动比率")
    debt_ratio = val("资产负债率")
    equity_ratio = val("产权比率")
    cash_ratio = val("现金比率")

    total_assets = None
    total_liab = None
    if equity and debt_ratio and debt_ratio < 100:
        total_assets = round(equity / (1 - debt_ratio / 100), 2)
        total_liab = round(total_assets - equity, 2)

    revenue_yoy = round((revenue - revenue_ya) / revenue_ya * 100, 2) if revenue and revenue_ya else None
    np_yoy = round((net_profit - net_profit_ya) / net_profit_ya * 100, 2) if net_profit and net_profit_ya else None

    beta = None
    try:
        r = SESSION.get(
            "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
            params={"symbol": _symbol_to_sina(symbol), "scale": "240", "ma": "no", "datalen": "250"},
            timeout=15,
        )
        import json as _json
        hist = _json.loads(r.text) if r.text else []
        if len(hist) > 30:
            closes = np.array([float(d["close"]) for d in hist])
            returns = np.diff(np.log(closes))
            stock_vol = float(np.std(returns) * np.sqrt(250))
            beta = round(stock_vol / 0.18, 3)
    except Exception:
        pass

    risk_signals = []
    if op_cashflow is not None and op_cashflow < 0:
        risk_signals.append({"signal": "经营现金流为负", "severity": "高", "detail": "经营活动现金流量净额为负"})
    if debt_ratio and debt_ratio > 70:
        risk_signals.append({"signal": "资产负债率过高", "severity": "高", "detail": f"资产负债率: {debt_ratio:.1f}%"})
    if current_ratio and current_ratio < 1:
        risk_signals.append({"signal": "流动比率低于1", "severity": "中", "detail": f"流动比率: {current_ratio:.2f}"})
    if gross_margin is not None and gross_margin < 10:
        risk_signals.append({"signal": "毛利率过低", "severity": "中", "detail": f"毛利率: {gross_margin:.1f}%"})
    if roe is not None and roe < 3:
        risk_signals.append({"signal": "ROE过低", "severity": "中", "detail": f"ROE: {roe:.2f}%"})
    if not risk_signals:
        risk_signals.append({"signal": "暂无明显风险信号", "severity": "低", "detail": "主要财务指标在正常范围内"})

    forecast = None
    if net_profit and net_profit_ya:
        growth = (net_profit - net_profit_ya) / net_profit_ya
        forecast = {
            "growth_rate": round(growth * 100, 2),
            "next_year_net_profit": round(net_profit * (1 + growth), 0),
            "method": f"基于同期净利润增速({round(growth*100,1)}%)线性推算",
            "disclaimer": "仅为简单趋势外推,不构成投资建议",
        }

    rf, rm = 2.5, 9.0
    capm = None
    if beta:
        capm = {
            "rf": rf, "rm": rm, "beta": beta,
            "expected_return": round(rf + beta * (rm - rf), 2),
            "explanation": f"预期收益率 = {rf}% + {beta} × ({rm}% - {rf}%) = {round(rf + beta * (rm - rf), 2)}%",
            "note": "无风险利率取10年期国债约2.5%,市场预期收益率取A股长期平均约9%。Beta基于个股年化波动率估算。",
        }

    def fmt_amt(v):
        if v is None:
            return None
        if abs(v) >= 1e8:
            return round(v / 1e8, 2)
        return round(v / 1e4, 2)

    return {
        "revenue_profit_trend": {
            "revenue": fmt_amt(revenue), "revenue_prev": fmt_amt(revenue_prev),
            "revenue_year_ago": fmt_amt(revenue_ya), "revenue_yoy": revenue_yoy,
            "net_profit": fmt_amt(net_profit), "net_profit_prev": fmt_amt(net_profit_prev),
            "net_profit_year_ago": fmt_amt(net_profit_ya), "net_profit_yoy": np_yoy,
            "eps": eps, "unit": "亿",
        },
        "profitability": {
            "gross_margin": gross_margin, "net_margin": net_margin,
            "roe": roe, "roa": roa, "operating_margin": operating_margin,
        },
        "balance_sheet": {
            "total_assets": fmt_amt(total_assets), "total_liabilities": fmt_amt(total_liab),
            "equity": fmt_amt(equity), "debt_ratio": debt_ratio, "unit": "亿",
        },
        "solvency": {
            "current_ratio": current_ratio, "quick_ratio": quick_ratio,
            "debt_to_equity": equity_ratio, "cash_ratio": cash_ratio,
        },
        "capm": capm,
        "risk_signals": risk_signals,
        "forecast": forecast,
        "data_source": "akshare stock_financial_abstract",
        "latest_period": latest,
    }
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
