#!/bin/bash
# 保活心跳: 每2分钟ping隧道, 防止Cloudflare回收
PROJECT_DIR="/mnt/c/Project/AIShareDataAPP"
cd "$PROJECT_DIR"

CURRENT_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' frontend/config.js 2>/dev/null | head -1)

if [ -n "$CURRENT_URL" ]; then
  curl -sS --max-time 5 -o /dev/null "${CURRENT_URL}/api/health" 2>/dev/null
fi
