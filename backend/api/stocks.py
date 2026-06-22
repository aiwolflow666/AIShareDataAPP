from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/search")
def search_stock(keyword: str = Query(..., description="股票代码或名称关键词")):
    import akshare as ak

    try:
        df = ak.stock_zh_a_spot_em()
        matched = df[df["名称"].str.contains(keyword) | df["代码"].str.contains(keyword)]
        return matched.head(20).to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"akshare 调用失败: {e}")


@router.get("/stocks/{symbol}/info")
def stock_info(symbol: str):
    import akshare as ak

    try:
        df = ak.stock_individual_info_em(symbol=symbol)
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"akshare 调用失败: {e}")


@router.get("/stocks/{symbol}/history")
def stock_history(
    symbol: str,
    start_date: str = Query("20200101", description="开始日期 YYYYMMDD"),
    end_date: str = Query("20991231", description="结束日期 YYYYMMDD"),
    adjust: str = Query("qfq", description="复权类型 qfq前复权/hfq后复权/空"),
):
    import akshare as ak

    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"akshare 调用失败: {e}")


@router.get("/stocks/{symbol}/finance")
def stock_finance(symbol: str):
    import akshare as ak

    try:
        df = ak.stock_financial_abstract(symbol=symbol)
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"akshare 调用失败: {e}")


@router.get("/stocks/{symbol}/industry")
def stock_industry(symbol: str):
    import akshare as ak

    try:
        df = ak.stock_individual_info_em(symbol=symbol)
        industry_rows = df[df["item"].isin(["行业", "所属板块", "所属行业"])]
        if industry_rows.empty:
            return {"symbol": symbol, "industry": None, "raw": df.to_dict(orient="records")}
        return {"symbol": symbol, "industry": industry_rows.iloc[0]["value"], "raw": df.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"akshare 调用失败: {e}")


@router.get("/stocks/{symbol}/orderbook")
def stock_orderbook(symbol: str):
    import akshare as ak

    try:
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == symbol]
        if row.empty:
            raise HTTPException(status_code=404, detail="未找到该股票实时行情")
        return row.iloc[0].to_dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"akshare 调用失败: {e}")


@router.get("/stocks/{symbol}/predict")
def stock_predict(
    symbol: str,
    days: int = Query(30, ge=1, le=90, description="预测天数"),
):
    import akshare as ak
    import numpy as np

    try:
        df = ak.stock_zh_a_hist(symbol=symbol, adjust="qfq")
        if df.empty:
            raise HTTPException(status_code=404, detail="无历史数据可预测")

        closes = df["收盘"].astype(float).to_numpy()

        ma5 = float(np.mean(closes[-5:])) if len(closes) >= 5 else float(np.mean(closes))
        ma20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else float(np.mean(closes))
        ma60 = float(np.mean(closes[-60:])) if len(closes) >= 60 else float(np.mean(closes))

        recent = closes[-20:] if len(closes) >= 20 else closes
        drift = float(np.mean(np.diff(recent)))

        last_close = float(closes[-1])
        predictions = [round(last_close + drift * (i + 1), 2) for i in range(days)]

        return {
            "symbol": symbol,
            "last_close": round(last_close, 2),
            "ma5": round(ma5, 2),
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2),
            "method": "linear_drift_ma",
            "predictions": predictions,
            "disclaimer": "仅基于均线与近期漂移的简化推算,不构成投资建议",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"akshare 调用失败: {e}")
