# AIShareData 股票分析应用

基于 [akshare](https://github.com/akfamily/akshare) 的股票分析应用,手机和 PC 均可通过 URL 访问。

## 架构

- **前端**:纯静态页(`frontend/`),部署到 GitHub Pages
- **后端**:FastAPI + akshare(`backend/`),运行在本地电脑,通过内网穿透暴露到公网

## 本地开发

### 后端

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
.venv/bin/uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

访问 http://127.0.0.1:8000/docs 查看 API 文档。

### 前端

直接用浏览器打开 `frontend/index.html`,或在 `frontend/` 目录起任意静态服务器。

默认连接 `http://127.0.0.1:8000/api`,部署前修改 `frontend/config.js` 中的 `API_BASE` 为你的内网穿透公网地址。

## 部署前端到 GitHub Pages

推送到 `main` 分支后,GitHub Actions 自动部署 `frontend/` 到 Pages。
在仓库 Settings → Pages → Source 选择 "GitHub Actions"。

## 内网穿透(让手机通过公网 URL 访问本地后端)

推荐 Cloudflare Tunnel(免费、无需公网 IP、稳定):

### 1. 安装 cloudflared

- Windows: 从 https://github.com/cloudflare/cloudflared/releases 下载 `cloudflared.exe`
- macOS: `brew install cloudflared`
- Linux: `curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared`

### 2. 启动隧道(免登录快速模式)

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

输出形如:

```
Your quick Tunnel has been created! Visit it at:
  https://random-words-xxx.trycloudflare.com
```

### 3. 更新前端配置

把 `frontend/config.js` 的 `API_BASE` 改为:

```js
window.API_BASE = "https://random-words-xxx.trycloudflare.com/api";
```

提交推送,GitHub Pages 上的前端即可通过该公网地址调用你电脑上的后端。

> 注意:快速模式 URL 每次重启会变。需固定域名则 `cloudflared tunnel login` 后创建命名隧道。
