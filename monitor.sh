#!/bin/bash
# 隧道守护: 检测断了立即重启, 加保活心跳
PROJECT_DIR="/mnt/c/Project/AIShareDataAPP"
cd "$PROJECT_DIR"

LOG="/tmp/monitor.log"
TS=$(date '+%m-%d %H:%M:%S')

# 读取当前 config.js 里的 URL
CURRENT_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' frontend/config.js 2>/dev/null | head -1)

if [ -z "$CURRENT_URL" ]; then
  echo "$TS 无URL,启动服务" >> "$LOG"
  bash start.sh >> "$LOG" 2>&1
  exit 0
fi

# 测试隧道是否可达 (3秒超时)
HTTP_CODE=$(curl -sS --max-time 8 -o /dev/null -w "%{http_code}" "${CURRENT_URL}/api/health" 2>/dev/null)

if [ "$HTTP_CODE" = "200" ]; then
  # 隧道正常, 不输出日志(减少噪音)
  exit 0
fi

# 隧道异常, 立即重启
echo "$TS 隧道异常(HTTP $HTTP_CODE),重启服务" >> "$LOG"

# 强制杀掉旧进程
pkill -f "cloudflared tunnel" 2>/dev/null
sleep 2

# 重新启动
bash start.sh >> "$LOG" 2>&1
echo "$TS 重启完成" >> "$LOG"
