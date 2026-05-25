#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# N29-A: daily30k 봇 사망 즉시 텔레그램 알림
# systemd ExecStopPost 훅으로 호출 — 봇 프로세스 죽음과 무관하게 실행됨.
# ────────────────────────────────────────────────────────────────
# 5/13 KILL_SWITCH 사건: 봇이 13:09 KST 정상 종료(exit 0) 후 systemd 가
# Restart=on-failure 정책상 재시작 안 함 → 34시간 멈춤 → 사용자는
# /status 무응답으로 우연히 감지. 봇 자체가 죽었으니 텔레그램 핸들러도
# 같이 죽어서 봇 내부 알림은 불가능. systemd 훅이 유일한 즉시 알림 경로.
# ────────────────────────────────────────────────────────────────
set -u

INSTALL_DIR="${INSTALL_DIR:-/home/ubuntu/Daily_30k_bot}"
ENV_FILE="$INSTALL_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "[notify_death] .env 미발견: $ENV_FILE" >&2
    exit 0  # 알림 실패가 systemd 재시작 정책에 영향 주지 않도록 0 반환
fi

# .env 에서 TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 만 추출 (전체 source 회피 — 따옴표 등 안전)
TOKEN=$(grep -E '^TELEGRAM_TOKEN=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'")
CHAT_ID=$(grep -E '^TELEGRAM_CHAT_ID=' "$ENV_FILE" | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'")

if [ -z "${TOKEN:-}" ] || [ -z "${CHAT_ID:-}" ]; then
    echo "[notify_death] TELEGRAM_TOKEN/CHAT_ID 미설정 — 알림 스킵" >&2
    exit 0
fi

EXIT_STATUS="${EXIT_STATUS:-unknown}"
SERVICE_RESULT="${SERVICE_RESULT:-unknown}"
NOW_KST=$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M:%S KST')

read -r -d '' MSG <<EOF || true
🔴 daily30k 봇 종료 감지

시각: ${NOW_KST}
종료 코드: ${EXIT_STATUS}
service 결과: ${SERVICE_RESULT}

KILL_SWITCH·DAILY_STOP·CRASH 모두 이 알림이 옵니다.
정상 종료라면 SSH 로 systemctl restart daily30k 필요.
EOF

curl -fsS --max-time 10 \
    -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    -d "chat_id=${CHAT_ID}" \
    --data-urlencode "text=${MSG}" \
    > /dev/null 2>&1 || echo "[notify_death] 텔레그램 전송 실패" >&2

exit 0
