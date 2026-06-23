#!/bin/bash
# 隧道守护:检测断了自动重启
# 用法: bash monitor.sh &  或 crontab 定时运行

PROJECT_DIR="/mnt/c/Project/AIShareDataAPP"
cd "$PROJECT_DIR"

# 读取当前 config.js 里的 URL
CURRENT_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' frontend/config.js 2>/dev/null | head -1)

if [ -z "$CURRENT_URL" ]; then
  echo "$(date '+%H:%M:%S') 无URL,启动服务"
  bash start.sh
  exit 0
fi

# 测试隧道是否可达
HTTP_CODE=$(curl -sS --max-time 10 -o /dev/null -w "%{http_code}" "${CURRENT_URL}/api/health" 2>/dev/null)

if [ "$HTTP_CODE" = "200" ]; then
  echo "$(date '+%H:%M:%S') 隧道正常 ($CURRENT_URL)"
  exit 0
fi

echo "$(date '+%H:%M:%S') 隧道异常(HTTP $HTTP_CODE),重启服务"
bash start.sh
