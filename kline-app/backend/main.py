import re
import json
import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

app = FastAPI(title="K线图 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSION = requests.Session()
SESSION.headers.update({
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0",
})


@app.middleware("http")
async def utf8(request, call_next):
    resp = await call_next(request)
    ct = resp.headers.get("content-type", "")
    if "application/json" in ct and "charset" not in ct:
        resp.headers["content-type"] = "application/json; charset=utf-8"
    return resp


@app.get("/api/search")
def search(keyword: str = Query(...)):
    r = SESSION.get(
        "https://suggest3.sinajs.cn/suggest/type=11,12,13,14,15",
        params={"key": keyword, "name": "suggestdata"},
        timeout=10,
    )
    m = re.search(r'"([^"]*)"', r.text)
    if not m or not m.group(1).strip():
        return []
    results = []
    for item in m.group(1).split(";"):
        if not item.strip():
            continue
        p = item.split(",")
        if len(p) >= 5:
            results.append({
                "code": p[2].strip(),
                "name": p[4].strip() or p[0].strip(),
                "sina": p[3].strip(),
            })
    return results[:20]


@app.get("/api/kline")
def kline(
    symbol: str = Query(...),
    scale: str = Query("240", description="240日线/1200周线/7200月线/60 60分/30 30分/15 15分/5 5分"),
    datalen: int = Query(500, ge=1, le=1023),
):
    r = SESSION.get(
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
        params={"symbol": symbol, "scale": scale, "ma": "no", "datalen": str(datalen)},
        timeout=15,
    )
    data = json.loads(r.text) if r.text else []
    return data


app.mount("/", StaticFiles(directory=str(Path(__file__).parent.parent / "frontend"), html=True))
