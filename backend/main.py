from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .api import stocks, analysis

app = FastAPI(title="AIShareData API", version="0.1.0")


@app.middleware("http")
async def ensure_utf8_charset(request: Request, call_next):
    response: Response = await call_next(request)
    ct = response.headers.get("content-type", "")
    if "application/json" in ct and "charset" not in ct:
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stocks.router, prefix="/api", tags=["stocks"])
app.include_router(analysis.router, prefix="/api", tags=["analysis"])
