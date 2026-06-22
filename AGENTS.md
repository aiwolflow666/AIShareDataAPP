# AGENTS.md

## 项目概述

基于 [akshare](https://github.com/akfamily/akshare) 的股票分析应用,手机和 PC 均可通过 URL 访问。
功能:公司信息、历史股价、财务、所属行业、订单/行情、股价预测。

## 架构(已落地)

- **前端**:纯静态页(`frontend/`),部署到 GitHub Pages。无构建步骤,无框架,原生 HTML/CSS/JS。
- **后端**:FastAPI + akshare(`backend/`),运行在开发者本地电脑,通过内网穿透(Cloudflare Tunnel)暴露到公网。
- **关键约束**:akshare 是 Python 库,无法在 GitHub Pages 静态站点中运行;必须由本地后端调用,前端通过 HTTP API 访问。

## 目录结构

- `backend/main.py` — FastAPI 入口,挂载 CORS 和路由
- `backend/api/stocks.py` — 所有股票相关接口,akshare 在此调用
- `frontend/` — 静态前端,部署到 GitHub Pages 的内容
- `frontend/config.js` — `API_BASE` 配置,部署前必须改为内网穿透公网地址
- `.github/workflows/deploy.yml` — 推送 main 分支自动部署 `frontend/` 到 Pages

## 开发命令

### 后端(已验证可用)

```bash
# 首次:创建虚拟环境(系统 Python 无 pip,需用 wheel 引导,见下方说明)
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档:http://127.0.0.1:8000/docs

### 前端

直接浏览器打开 `frontend/index.html`,无需构建。修改 `frontend/config.js` 指向后端地址。

## 环境注意事项

- 系统 Python 3.14 **无 pip、无 ensurepip**,必须通过 venv + 手动安装 pip wheel 引导;pip 需配置清华镜像(`https://pypi.tuna.tsinghua.edu.cn/simple`),直连 PyPI 在当前网络不稳定。
- akshare 调用国内数据源,沙箱环境可能出现连接重置(`RemoteDisconnected`);在开发者本地(国内网络)应正常。

## 部署

- **前端**:推送 `main` 分支 → GitHub Actions 自动部署 `frontend/` 到 Pages。仓库 Settings → Pages → Source 需选 "GitHub Actions"。
- **后端**:本地运行 + Cloudflare Tunnel 穿透。`cloudflared tunnel --url http://127.0.0.1:8000` 获取公网 URL,更新 `frontend/config.js` 的 `API_BASE` 并重新推送。快速模式 URL 每次重启会变;需固定域名用 `cloudflared tunnel login` 创建命名隧道。

## API 接口

- `GET /api/health` — 健康检查
- `GET /api/search?keyword=` — 搜索股票(代码或名称)
- `GET /api/stocks/{symbol}/info` — 公司信息
- `GET /api/stocks/{symbol}/history?start_date=&end_date=&adjust=` — 历史股价
- `GET /api/stocks/{symbol}/finance` — 财务摘要
- `GET /api/stocks/{symbol}/industry` — 所属行业
- `GET /api/stocks/{symbol}/orderbook` — 实时行情/订单簿
- `GET /api/stocks/{symbol}/predict?days=` — 股价预测(均线+漂移简化模型,非投资建议)

## 待完善

- 尚未配置 lint/typecheck/test 命令;引入前勿假设存在。
- 股价预测为简化线性漂移模型,可替换为更复杂算法。
