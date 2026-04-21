#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# Daily 30K — Lightsail 초기 프로비저닝 (Ubuntu 22.04 전용, 1회 실행)
# ────────────────────────────────────────────────────────────────
# 사용법:
#   1) Lightsail 인스턴스 생성 (Seoul, $5 플랜, Ubuntu 22.04)
#   2) SSH 접속 후: sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/<you>/<repo>/main/deploy/setup.sh)"
#      또는 git clone 후 `bash deploy/setup.sh`
#
# 수행 내역:
#   · apt 패키지 최신화 + python3.11 설치
#   · repo 클론 (~/Daily_30k_bot)
#   · venv 생성 + requirements.txt 설치
#   · logs/ 디렉토리 생성
#   · systemd unit 등록 (enable 만 수행 — start 는 .env 입력 후 수동)
#
# ⚠ .env 파일은 이 스크립트가 생성하지 않는다 — 스크립트 종료 후
#   `cp .env.example .env && vi .env` 로 키를 직접 기입할 것.
# ────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/doulzang/Daily_30k_bot.git}"
INSTALL_DIR="${INSTALL_DIR:-/home/ubuntu/Daily_30k_bot}"
SERVICE_NAME="daily30k"

echo "[1/6] apt update + 의존 패키지 설치"
sudo apt-get update -y
sudo apt-get install -y software-properties-common git curl build-essential
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update -y
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev

echo "[2/6] 리포 클론 ($REPO_URL → $INSTALL_DIR)"
if [ ! -d "$INSTALL_DIR/.git" ]; then
    git clone "$REPO_URL" "$INSTALL_DIR"
else
    echo "      이미 클론됨. git pull 로 최신화."
    git -C "$INSTALL_DIR" pull --ff-only
fi

echo "[3/6] venv 생성 + requirements 설치"
cd "$INSTALL_DIR"
if [ ! -d venv ]; then
    python3.11 -m venv venv
fi
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "[4/6] 로그 디렉토리 생성"
mkdir -p logs

echo "[5/6] systemd unit 등록"
sudo cp "$INSTALL_DIR/deploy/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"

echo "[6/6] 완료."
cat <<EOF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
다음 단계 (사용자 수동):

  1) cd $INSTALL_DIR
  2) cp .env.example .env
  3) vi .env   # MODE, 바이낸스·텔레그램·Supabase 키 입력
  4) sudo systemctl start $SERVICE_NAME
  5) sudo systemctl status $SERVICE_NAME
  6) 텔레그램 부팅 메시지의 [MODE=...] 확인

로그 확인:  tail -f logs/daily30k.err.log
중지:       sudo systemctl stop $SERVICE_NAME
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
