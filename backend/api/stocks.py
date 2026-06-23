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


def _fetch_report(symbol, page, year):
    try:
        r = SESSION.get(
            f"https://money.finance.sina.com.cn/corp/go.php/{page}/stockid/{symbol}/ctrl/{year}/displaytype/4.phtml",
            timeout=15,
        )
        r.raise_for_status()
        r.encoding = "gb2312"
        return _parse_report_table(r.text, page)
    except Exception:
        return None


def _get_row_value(report, item_name, col=None):
    if not report:
        return None
    for row in report["rows"]:
        if row.get("报表日期") == item_name:
            if col:
                v = row.get(col, "")
            else:
                vals = [v for k, v in row.items() if k != "报表日期" and v]
                v = vals[0] if vals else ""
            if not v or v == "--":
                return None
            try:
                return float(v.replace(",", ""))
            except (ValueError, AttributeError):
                return None
    return None


@router.get("/stocks/{symbol}/finance_summary")
def stock_finance_summary(symbol: str):
    import numpy as np

    pages = {
        "资产负债表": "vFD_BalanceSheet",
        "利润表": "vFD_ProfitStatement",
        "现金流量表": "vFD_CashFlow",
    }

    reports = {}
    for year in ["2024", "2023"]:
        for name, page in pages.items():
            key = f"{name}_{year}"
            if key not in reports:
                reports[key] = _fetch_report(symbol, page, year)

    bs_24 = reports.get("资产负债表_2024")
    pl_24 = reports.get("利润表_2024")
    cf_24 = reports.get("现金流量表_2024")
    pl_23 = reports.get("利润表_2023")
    bs_23 = reports.get("资产负债表_2023")

    if not pl_24:
        raise HTTPException(status_code=404, detail="无法获取利润表数据")

    cols_24 = pl_24["columns"] if pl_24 else []
    latest_col = cols_24[1] if len(cols_24) > 1 else None
    prev_col = cols_24[2] if len(cols_24) > 2 else latest_col

    revenue = _get_row_value(pl_24, "一、营业总收入", latest_col) or _get_row_value(pl_24, "营业收入", latest_col)
    revenue_prev = _get_row_value(pl_24, "一、营业总收入", prev_col) or _get_row_value(pl_24, "营业收入", prev_col)
    revenue_23 = _get_row_value(pl_23, "一、营业总收入") or _get_row_value(pl_23, "营业收入")

    net_profit = _get_row_value(pl_24, "五、净利润", latest_col)
    net_profit_prev = _get_row_value(pl_24, "五、净利润", prev_col)
    net_profit_23 = _get_row_value(pl_23, "五、净利润")

    op_profit = _get_row_value(pl_24, "三、营业利润", latest_col)
    total_profit = _get_row_value(pl_24, "四、利润总额", latest_col)
    tax_expense = _get_row_value(pl_24, "减：所得税费用", latest_col)
    sales_expense = _get_row_value(pl_24, "销售费用", latest_col)
    mgmt_expense = _get_row_value(pl_24, "管理费用", latest_col)
    rd_expense = _get_row_value(pl_24, "研发费用", latest_col)
    eps = _get_row_value(pl_24, "基本每股收益(元/股)", latest_col)

    total_assets = _get_row_value(bs_24, "资产总计", latest_col)
    total_liab = _get_row_value(bs_24, "负债合计", latest_col)
    equity = _get_row_value(bs_24, "归属于母公司股东权益合计", latest_col)
    current_assets = _get_row_value(bs_24, "流动资产合计", latest_col)
    current_liab = _get_row_value(bs_24, "流动负债合计", latest_col)
    inventory = _get_row_value(bs_24, "存货", latest_col)
    cash = _get_row_value(bs_24, "货币资金", latest_col)
    accounts_receivable = _get_row_value(bs_24, "应收账款", latest_col)

    op_cashflow = _get_row_value(cf_24, "经营活动产生现金流量净额", latest_col) or _get_row_value(cf_24, "五、经营活动产生现金流量净额", latest_col)
    inv_cashflow = _get_row_value(cf_24, "投资活动产生的现金流量净额", latest_col)
    fin_cashflow = _get_row_value(cf_24, "筹资活动产生的现金流量净额", latest_col)

    def safe_div(a, b):
        return round(a / b * 100, 2) if a is not None and b and b != 0 else None

    def safe_ratio(a, b):
        return round(a / b, 2) if a is not None and b and b != 0 else None

    gross_cost = None
    if revenue and (sales_expense or mgmt_expense):
        total_cost = (sales_expense or 0) + (mgmt_expense or 0) + (rd_expense or 0)
        gross_profit = revenue - total_cost
    else:
        gross_profit = None

    revenue_yoy = safe_div(net_profit - (net_profit_23 or 0), net_profit_23) if net_profit and net_profit_23 else None
    net_profit_yoy = safe_div(net_profit - (net_profit_23 or 0), net_profit_23) if net_profit and net_profit_23 else None

    # 估算Beta:用历史K线波动率
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
            market_avg_vol = 0.18
            beta = round(stock_vol / market_avg_vol, 3)
    except Exception:
        pass

    risk_signals = []
    if op_cashflow is not None and op_cashflow < 0:
        risk_signals.append({"signal": "经营现金流为负", "severity": "高", "detail": f"经营活动现金流量净额: {op_cashflow:,.0f}"})
    if total_liab and total_assets and total_liab / total_assets > 0.7:
        risk_signals.append({"signal": "资产负债率过高", "severity": "高", "detail": f"资产负债率: {safe_div(total_liab, total_assets)}%"})
    if current_assets and current_liab and current_assets / current_liab < 1:
        risk_signals.append({"signal": "流动比率低于1", "severity": "中", "detail": f"流动比率: {safe_ratio(current_assets, current_liab)}"})
    if accounts_receivable and revenue and accounts_receivable / revenue > 0.3:
        risk_signals.append({"signal": "应收账款占比过高", "severity": "中", "detail": f"应收账款/营收: {safe_div(accounts_receivable, revenue)}%"})
    if gross_profit is not None and gross_profit < 0:
        risk_signals.append({"signal": "毛利为负", "severity": "高", "detail": "营业成本超过营业收入"})
    if not risk_signals:
        risk_signals.append({"signal": "暂无明显风险信号", "severity": "低", "detail": "主要财务指标在正常范围内"})

    # 盈利预测:基于近期趋势
    forecast = None
    if net_profit and net_profit_23:
        growth_rate = (net_profit - net_profit_23) / net_profit_23
        next_year_forecast = round(net_profit * (1 + growth_rate), 0)
        forecast = {
            "growth_rate": round(growth_rate * 100, 2),
            "next_year_net_profit": next_year_forecast,
            "method": f"基于2023-2024净利润增速({round(growth_rate*100,1)}%)线性推算",
            "disclaimer": "仅为简单趋势外推,不构成投资建议",
        }

    rf = 2.5
    rm = 9.0
    capm = None
    if beta:
        expected_return = round(rf + beta * (rm - rf), 2)
        capm = {
            "rf": rf,
            "rm": rm,
            "beta": beta,
            "expected_return": expected_return,
            "explanation": f"预期收益率 = {rf}% + {beta} × ({rm}% - {rf}%) = {expected_return}%",
            "note": "无风险利率取10年期国债约2.5%,市场预期收益率取A股长期平均约9%。Beta基于个股年化波动率估算,非严格回归Beta。",
        }

    return {
        "revenue_profit_trend": {
            "revenue": revenue, "revenue_prev": revenue_prev, "revenue_2023": revenue_23,
            "net_profit": net_profit, "net_profit_prev": net_profit_prev, "net_profit_2023": net_profit_23,
            "revenue_yoy": safe_div(revenue - revenue_23, revenue_23) if revenue and revenue_23 else None,
            "net_profit_yoy": net_profit_yoy,
            "eps": eps,
        },
        "profitability": {
            "gross_margin": safe_div(gross_profit, revenue) if gross_profit and revenue else None,
            "net_margin": safe_div(net_profit, revenue),
            "roe": safe_div(net_profit, equity),
            "roa": safe_div(net_profit, total_assets),
            "operating_margin": safe_div(op_profit, revenue),
        },
        "balance_sheet": {
            "total_assets": total_assets, "total_liabilities": total_liab,
            "equity": equity, "current_assets": current_assets, "current_liabilities": current_liab,
            "inventory": inventory, "cash": cash,
            "debt_ratio": safe_div(total_liab, total_assets),
        },
        "solvency": {
            "current_ratio": safe_ratio(current_assets, current_liab),
            "quick_ratio": safe_ratio(current_assets - (inventory or 0), current_liab) if current_assets and current_liab else None,
            "debt_to_equity": safe_ratio(total_liab, equity),
            "cash_to_debt": safe_ratio(cash, total_liab),
        },
        "capm": capm,
        "risk_signals": risk_signals,
        "forecast": forecast,
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
