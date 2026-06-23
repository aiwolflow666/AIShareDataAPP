#!/bin/bash
set -e

PROJECT_DIR="/mnt/c/Project/AIShareDataAPP"
LOG_DIR="/tmp"

cd "$PROJECT_DIR"

echo "===== 1. 清理旧进程 ====="
pkill -f "uvicorn backend.main" 2>/dev/null && echo "已停止旧后端" || echo "无旧后端"
pkill -f "cloudflared tunnel" 2>/dev/null && echo "已停止旧隧道" || echo "无旧隧道"
sleep 2

echo ""
echo "===== 2. 启动后端 ====="
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 > "$LOG_DIR/uvicorn.log" 2>&1 &
BACKEND_PID=$!
echo "后端 PID: $BACKEND_PID"
sleep 6

for i in $(seq 1 5); do
  if curl -sS --max-time 3 http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
    echo "✅ 后端运行中"
    break
  fi
  echo "等待后端就绪... ($i/5)"
  sleep 2
  if [ $i -eq 5 ]; then
    echo "❌ 后端启动失败,查看日志:"
    cat "$LOG_DIR/uvicorn.log" | tail -10
    exit 1
  fi
done

echo ""
echo "===== 3. 启动 cloudflared 隧道 ====="
./cloudflared tunnel --url http://127.0.0.1:8000 --protocol http2 --edge-ip-version 4 > "$LOG_DIR/cloudflared.log" 2>&1 &
TUNNEL_PID=$!
echo "隧道 PID: $TUNNEL_PID"

echo "等待公网 URL 生成..."
TUNNEL_URL=""
for i in $(seq 1 30); do
  sleep 1
  TUNNEL_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_DIR/cloudflared.log" 2>/dev/null | head -1)
  if [ -n "$TUNNEL_URL" ]; then
    break
  fi
done

if [ -z "$TUNNEL_URL" ]; then
  echo "❌ 未能获取隧道 URL,查看日志:"
  cat "$LOG_DIR/cloudflared.log" | tail -15
  exit 1
fi

echo "✅ 隧道公网地址: $TUNNEL_URL"

echo ""
echo "===== 4. 更新前端配置 ====="
sed -i "s|window.API_BASE = .*|window.API_BASE = \"${TUNNEL_URL}/api\";|" frontend/config.js
echo "✅ frontend/config.js 已更新:"
cat frontend/config.js

echo ""
echo "===== 5. 推送到 GitHub ====="
git add frontend/config.js
git commit -m "auto: update API_BASE to $TUNNEL_URL" > /dev/null 2>&1 && echo "✅ 已提交" || echo "⚠ 无变更可提交"
git push > /dev/null 2>&1 && echo "✅ 已推送" || echo "⚠ 推送失败,稍后手动 git push"

echo ""
echo "===== 完成 ====="
echo "前端地址: https://aiwolflow666.github.io/AIShareDataAPP/"
echo "后端地址: $TUNNEL_URL"
echo ""
echo "后端日志: tail -f $LOG_DIR/uvicorn.log"
echo "隧道日志: tail -f $LOG_DIR/cloudflared.log"
echo ""
echo "停止服务: kill $BACKEND_PID $TUNNEL_PID"
