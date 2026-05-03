#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# Daily 30K — 배포 업데이트 (git pull → deps → restart)
# ────────────────────────────────────────────────────────────────
# 사용법 (Lightsail 서버에서):
#   cd ~/Daily_30k_bot && bash deploy/update.sh
#
# 동작:
#   1) git pull (fast-forward only — 로컬 수정 있으면 실패)
#   2) requirements.txt 변경 감지 시 pip install
#   3) systemctl restart daily30k
#   4) 재시작 직후 상태 출력
# ────────────────────────────────────────────────────────────────
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/home/ubuntu/Daily_30k_bot}"
SERVICE_NAME="daily30k"

cd "$INSTALL_DIR"

echo "[1/3] git pull"
REQ_BEFORE=$(sha256sum requirements.txt | cut -d' ' -f1)
git pull --ff-only
REQ_AFTER=$(sha256sum requirements.txt | cut -d' ' -f1)

if [ "$REQ_BEFORE" != "$REQ_AFTER" ]; then
    echo "[2/3] requirements.txt 변경 감지 — pip install"
    ./venv/bin/pip install -r requirements.txt
else
    echo "[2/3] requirements.txt 동일 — pip 스킵"
fi

echo "[3/3] systemctl restart $SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"
sleep 2
sudo systemctl status "$SERVICE_NAME" --no-pager -l | head -20

echo ""
echo "배포 완료. 로그:  sudo journalctl -u $SERVICE_NAME -f"
