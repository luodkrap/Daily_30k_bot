#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# Daily 30K — 배포 가이드 진단 (Deploy Advisor)
# ────────────────────────────────────────────────────────────────
# 사용법:
#   bash deploy/advise.sh                   # unpushed 커밋 전체 분석
#   bash deploy/advise.sh --since=HEAD~3    # 지정 범위
#   bash deploy/advise.sh --files a.py b.py # 직접 파일 지정 (Claude 호출용)
#
# 동작:
#   변경 파일 목록을 수집 → 유형별 규칙 매칭 → 상황별 배포 체크리스트 출력
#   (update.sh 를 대체하지 않음. 배포 전에 선행 실행 권장.)
# ────────────────────────────────────────────────────────────────
set -euo pipefail

RED=$'\033[31m'
ORANGE=$'\033[33m'
YELLOW=$'\033[93m'
GREEN=$'\033[32m'
BOLD=$'\033[1m'
DIM=$'\033[2m'
NC=$'\033[0m'

usage() {
    sed -n '2,13p' "$0"
    exit 0
}

MODE="unpushed"
SINCE=""
FILES_ARG=()

while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage ;;
        --since=*) MODE="since"; SINCE="${1#--since=}"; shift ;;
        --files)
            MODE="files"
            shift
            while [ $# -gt 0 ] && [[ "$1" != --* ]]; do
                FILES_ARG+=("$1")
                shift
            done
            ;;
        *) echo "알 수 없는 인자: $1" >&2; exit 1 ;;
    esac
done

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "${RED}이 디렉터리는 git 저장소가 아닙니다.${NC}" >&2
    exit 1
fi

collect_files() {
    case "$MODE" in
        unpushed)
            if ! git rev-parse --verify origin/main >/dev/null 2>&1; then
                echo "" ; return
            fi
            git log --name-only --pretty=format: origin/main..HEAD 2>/dev/null | sort -u | grep -v '^$' || true
            ;;
        since)
            git log --name-only --pretty=format: "${SINCE}..HEAD" 2>/dev/null | sort -u | grep -v '^$' || true
            ;;
        files)
            printf '%s\n' "${FILES_ARG[@]}" | sort -u
            ;;
    esac
}

FILES="$(collect_files)"

if [ -z "$FILES" ]; then
    echo "${GREEN}배포할 커밋이 없습니다.${NC} (unpushed 변경 없음)"
    exit 0
fi

has() { grep -Fxq "$1" <<<"$FILES"; }
has_prefix() { grep -q "^$1" <<<"$FILES"; }
has_pattern() { grep -Eq "$1" <<<"$FILES"; }

FLAG_SCHEMA=0
FLAG_ENV=0
FLAG_SERVICE=0
FLAG_TRADING=0
FLAG_REQS=0
FLAG_OTHER=0

# 배포 필요성 분류: 각 파일을 skip / optional / required 로 분류.
# - skip:     봇 런타임·배포 도구가 로드하지 않음 → git commit/push 만 하면 됨
# - optional: 런타임 미사용이나 서버에서 참조 가능 (원한다면 pull)
# - required: 봇 런타임·systemd·Supabase 가 로드 → 배포 필요
classify_file() {
    local f="$1"
    case "$f" in
        WORKFLOW.md|TODO.md|PROJECT.md|README.md|CLAUDE.md) echo "skip" ;;
        skills/*|.claude/*|.claudeignore|.gitignore)        echo "skip" ;;
        docs/*|*.md)                                        echo "skip" ;;
        deploy/advise.sh|.env.example|test.py)              echo "optional" ;;
        deploy/schema.sql|deploy/daily30k.service)          echo "required" ;;
        deploy/setup.sh|deploy/update.sh)                   echo "required" ;;
        requirements.txt)                                   echo "required" ;;
        *.py)                                               echo "required" ;;
        *)                                                  echo "required" ;;
    esac
}

DEPLOY_STATUS="skip"
while IFS= read -r f; do
    [ -z "$f" ] && continue
    case "$f" in
        deploy/schema.sql)       FLAG_SCHEMA=1 ;;
        .env.example)            FLAG_ENV=1 ;;
        deploy/daily30k.service) FLAG_SERVICE=1 ;;
        executor.py|screener.py) FLAG_TRADING=1 ;;
        requirements.txt)        FLAG_REQS=1 ;;
        *)                       FLAG_OTHER=1 ;;
    esac
    cls=$(classify_file "$f")
    case "$cls" in
        required) DEPLOY_STATUS="required" ;;
        optional) [ "$DEPLOY_STATUS" = "skip" ] && DEPLOY_STATUS="optional" ;;
    esac
done <<<"$FILES"

TRADING_LINES=0
if [ "$FLAG_TRADING" = "1" ] && [ "$MODE" != "files" ]; then
    RANGE=""
    case "$MODE" in
        unpushed) RANGE="origin/main..HEAD" ;;
        since)    RANGE="${SINCE}..HEAD" ;;
    esac
    if [ -n "$RANGE" ]; then
        TRADING_LINES=$(git diff --numstat "$RANGE" -- executor.py screener.py 2>/dev/null \
            | awk '{add+=$1; del+=$2} END {print (add+del)+0}')
    fi
fi

case "$DEPLOY_STATUS" in
    required) BADGE="${RED}${BOLD}🚨 배포 필요${NC}";        SUBTITLE="봇 런타임에 영향 — 서버 반영 권장" ;;
    optional) BADGE="${YELLOW}${BOLD}🟢 배포 선택${NC}";      SUBTITLE="봇 동작 영향 없음 — 서버 참조 원하면 pull" ;;
    skip)     BADGE="${GREEN}${BOLD}🔘 배포 불필요${NC}";     SUBTITLE="런타임·배포 스크립트 영향 없음 — 커밋/푸시만" ;;
esac

echo ""
echo "${BOLD}📦 배포 체크리스트${NC}  ${DIM}(mode=${MODE})${NC}"
echo "${DIM}─────────────────────────────────────────────${NC}"
echo "${BOLD}판정:${NC} ${BADGE}  ${DIM}${SUBTITLE}${NC}"
echo ""
echo "${BOLD}변경 파일:${NC}"
while IFS= read -r f; do
    [ -z "$f" ] && continue
    cls=$(classify_file "$f")
    case "$cls" in
        required) tag="${RED}[필요]${NC}" ;;
        optional) tag="${YELLOW}[선택]${NC}" ;;
        skip)     tag="${GREEN}[불필요]${NC}" ;;
    esac
    echo "  • $f  $tag"
done <<<"$FILES"
echo ""

if [ "$FLAG_SCHEMA" = "1" ]; then
    cat <<EOF
${RED}${BOLD}🔴 [BEFORE DEPLOY] Supabase 스키마 변경 감지${NC}
   ${BOLD}코드 배포 전에 반드시 스키마를 먼저 적용할 것.${NC}
   1) Supabase 웹 콘솔 → SQL Editor
   2) deploy/schema.sql 의 변경분 확인 → ALTER TABLE 문 작성·실행
   3) Table Editor 에서 컬럼/타입 반영 확인
   4) 그 다음에만 서버 update.sh 실행

EOF
fi

if [ "$FLAG_ENV" = "1" ]; then
    ENV_DIFF=""
    if [ "$MODE" != "files" ]; then
        RANGE=""
        case "$MODE" in
            unpushed) RANGE="origin/main..HEAD" ;;
            since)    RANGE="${SINCE}..HEAD" ;;
        esac
        if [ -n "$RANGE" ]; then
            ENV_DIFF=$(git diff "$RANGE" -- .env.example 2>/dev/null \
                | grep -E '^\+[A-Z_][A-Z0-9_]*=' | sed 's/^+/   + /' || true)
        fi
    fi
    cat <<EOF
${ORANGE}${BOLD}🟠 [ENV UPDATE] .env.example 변경 감지${NC}
   서버 .env 에 신규 환경변수를 수동으로 추가해야 합니다.
   1) ssh ubuntu@3.36.26.177
   2) vi ~/Daily_30k_bot/.env
   3) 아래 신규 변수 추가 (값은 실제 환경에 맞춰 입력):
EOF
    if [ -n "$ENV_DIFF" ]; then
        echo "$ENV_DIFF"
    else
        echo "   ${DIM}(diff 해석 불가 — .env.example 을 직접 비교해서 추가할 것)${NC}"
    fi
    cat <<EOF
   4) chmod 600 ~/Daily_30k_bot/.env  (권한 유지)
   5) 그 다음 update.sh 실행

EOF
fi

if [ "$FLAG_SERVICE" = "1" ]; then
    cat <<EOF
${ORANGE}${BOLD}🟠 [SYSTEMD RELOAD] daily30k.service 변경 감지${NC}
   update.sh 는 파일만 pull 하고 daemon-reload 는 수행하지 않습니다.
   서버에서 추가로 실행:
     sudo cp deploy/daily30k.service /etc/systemd/system/daily30k.service
     sudo systemctl daemon-reload
     sudo systemctl restart daily30k

EOF
fi

if [ "$FLAG_TRADING" = "1" ]; then
    EXTRA=""
    if [ "$TRADING_LINES" -ge 50 ]; then
        EXTRA="   ${RED}⚠️  변경 ${TRADING_LINES} 라인 — 대규모 수정. 재시작 전 test.py 필수.${NC}"
    elif [ "$TRADING_LINES" -gt 0 ]; then
        EXTRA="   ${DIM}변경 ${TRADING_LINES} 라인.${NC}"
    fi
    cat <<EOF
${YELLOW}${BOLD}🟡 [TIMING WARNING] 매매 로직 변경 감지 (executor / screener)${NC}
   재시작 시 recover_state() 가 발동 → 미체결 주문 취소 + 포지션 청산.
   페이퍼 운영 중이라도 진행 중 그리드는 소실됩니다.
   ${BOLD}권장 타이밍:${NC} KST 04:00 ~ 06:00 (시장 한산)
   비상 절차:
     • 재시작 전  → sudo systemctl stop daily30k
     • 포지션 확인 → Binance testnet UI
     • 문제 없으면 → 평상시 재시작 (update.sh)
EOF
    [ -n "$EXTRA" ] && echo "$EXTRA"
    echo ""
fi

if [ "$FLAG_REQS" = "1" ]; then
    cat <<EOF
${GREEN}[AUTO] requirements.txt 변경 감지${NC}
   update.sh 가 sha256 비교로 자동 pip install 수행 — 별도 액션 불필요.

EOF
fi

if [ "$DEPLOY_STATUS" = "required" ] && [ "$FLAG_SCHEMA" = "0" ] && [ "$FLAG_ENV" = "0" ] && [ "$FLAG_SERVICE" = "0" ] && [ "$FLAG_TRADING" = "0" ] && [ "$FLAG_REQS" = "0" ]; then
    echo "${GREEN}[STANDARD] 특수 액션 없음 — update.sh 표준 루틴으로 충분.${NC}"
    echo ""
fi

echo "${BOLD}─────────────────────────────────────────────${NC}"

case "$DEPLOY_STATUS" in
    skip)
        cat <<EOF
${BOLD}조치 사항${NC}
  ${DIM}# 로컬만${NC}
  git add -A && git commit -m "..."
  git push origin main
  ${DIM}# 서버 재시작 불필요 — recover_state 발동 회피${NC}
EOF
        ;;
    optional)
        cat <<EOF
${BOLD}조치 사항${NC}
  ${DIM}# 로컬${NC}
  git push origin main
  ${DIM}# 서버 (선택) — 봇 재시작 원치 않으면 git pull 만${NC}
  ssh ubuntu@3.36.26.177
  cd ~/Daily_30k_bot && git pull --ff-only
  ${DIM}# update.sh 는 재시작을 동반하므로 실제 봇 코드 배포 시에만 실행${NC}
EOF
        ;;
    required)
        cat <<EOF
${BOLD}표준 배포 명령${NC}
  ${DIM}# 로컬${NC}
  git push origin main
  ${DIM}# 서버${NC}
  ssh ubuntu@3.36.26.177
  cd ~/Daily_30k_bot && bash deploy/update.sh
  ${DIM}# 검증${NC}
  tail -f logs/daily30k.err.log
  ${DIM}# 텔레그램 [MODE=TESTNET] 부팅 메시지 재수신 확인${NC}
EOF
        ;;
esac
