#!/bin/bash
cd "$(dirname "$0")"
python3 -m venv .venv 2>/dev/null
.venv/bin/pip install -r backend/requirements.txt -q 2>/dev/null
echo "启动 K线图服务: http://localhost:9000"
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 9000
