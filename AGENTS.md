# AGENTS.md

## 日常启动(最重要)

```bash
cd /mnt/c/Project/AIShareDataAPP && bash start.sh
```

一条命令完成:清理旧进程 → 启动后端 → 启动隧道 → 更新公网 URL → 推送 GitHub。等 1-2 分钟访问 https://aiwolflow666.github.io/AIShareDataAPP/

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
- **后端**:本地运行 + Cloudflare Tunnel 穿透。
- **一键启动(日常使用)**:`bash start.sh` — 自动清理旧进程 → 启动后端 → 启动隧道(强制 HTTP/2)→ 抓取新公网 URL → 更新 `frontend/config.js` → 提交推送 GitHub。等 Actions 部署完(1-2 分钟)访问 https://aiwolflow666.github.io/AIShareDataAPP/ 即可。
- **停止服务**:`kill <后端PID> <隧道PID>`(PID 见 start.sh 输出),或 `pkill -f "uvicorn backend"; pkill -f "cloudflared"`。
- 快速模式 URL 每次重启都变,start.sh 已自动处理更新与推送;无需固定域名。
- cloudflared 二进制在仓库根目录 `./cloudflared`(ARM64 Linux 版,已加入 .gitignore),勿提交。

## API 接口

- `GET /api/health` — 健康检查
- `GET /api/search?keyword=` — 搜索股票(代码或名称)
- `GET /api/stocks/{symbol}/info` — 公司信息
- `GET /api/stocks/{symbol}/history?start_date=&end_date=&adjust=` — 历史股价
- `GET /api/stocks/{symbol}/finance` — 财务摘要
- `GET /api/stocks/{symbol}/industry` — 所属行业
- `GET /api/stocks/{symbol}/orderbook` — 实时行情/订单簿
- `GET /api/stocks/{symbol}/predict?days=` — 股价预测(均线+漂移简化模型,非投资建议)
- `GET /api/stocks/{symbol}/analysis` — AI 深度分析(SSE 流式,调用火山引擎 LLM,需 `.env` 中配置 `LLM_API_KEY`)

## AI 分析

- 模型: 火山引擎 OpenAI 兼容 API(coding 端点),模型 `deepseek-v4-pro`
- 配置: `.env` 文件(`LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL`),不入仓;模板见 `.env.example`
- 流程: 后端收集实时行情+历史K线+财务+行业 → 组装 prompt → LLM 流式输出 → 前端 SSE 逐字渲染(markdown)
- 注意: `LLM_BASE_URL` 用的是 coding 端点(`/api/coding/v3`),标准端点(`/api/v3`)需要 endpoint ID 而非模型名

## 待完善

- 尚未配置 lint/typecheck/test 命令;引入前勿假设存在。
- 股价预测为简化线性漂移模型,可替换为更复杂算法。
