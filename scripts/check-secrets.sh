#!/usr/bin/env bash
# 시크릿·식별자가 커밋되는 것을 막는다(pre-commit 훅이 호출).
#
# .gitignore 는 .env "파일"만 지킨다 — 문서·스크립트·yml 에 값을 하드코딩하는 실수는 못 잡는다.
# 유출된 값은 git 이력에 영원히 남는다(프라이빗 레포라도 마찬가지 — 접근 통제일 뿐 삭제가 아니다).
# 이 레포는 슬랙 토큰과 워크스페이스 식별자를 다루므로 **식별자까지** 검사한다(CLAUDE.md 규칙).
#
# 사용: scripts/check-secrets.sh              스테이지된 변경 검사(훅과 동일)
#       SKIP_SECRET_GUARD=1 git commit …      우회(오탐 확인 후에만)

set -uo pipefail
cd "$(dirname "$0")/.."

if [ "${SKIP_SECRET_GUARD:-}" = "1" ]; then
  echo "⏭  시크릿 검사 건너뜀(SKIP_SECRET_GUARD=1)"
  exit 0
fi

STAGED=$(git diff --cached --name-only --diff-filter=ACM)
[ -z "$STAGED" ] && exit 0

FAIL=0

# ── ① .env 파일 자체 스테이징 차단(.example 은 허용) ─────────────────────────
ENV_STAGED=$(echo "$STAGED" | grep -E '(^|/)\.env(\.[A-Za-z0-9_-]+)?$' | grep -v '\.example$' || true)
if [ -n "$ENV_STAGED" ]; then
  FAIL=1
  echo "❌ .env 파일이 스테이지돼 있습니다(시크릿 유출):" >&2
  echo "$ENV_STAGED" | sed 's/^/   /' >&2
  echo "   git restore --staged <파일> 로 내리세요. 공유할 항목이면 .env.example 에 이름만." >&2
  echo >&2
fi

# ── ② 토큰 패턴 ────────────────────────────────────────────────────────────
TOKENS='xox[baprs]-[A-Za-z0-9-]{10,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|sk-ant-[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
# ── ③ 슬랙 식별자(채널 C…/그룹 G…/사용자 U…) — 값이 아니라 이름을 쓰라는 규칙의 강제 ──
#     .env.example 은 이름만 담으므로 검사 대상에서 빼지 않아도 걸리지 않는다.
SLACK_IDS='\b[CGU]0[A-Z0-9]{8,}\b'

while IFS= read -r f; do
  [ -z "$f" ] && continue
  CONTENT=$(git show ":$f" 2>/dev/null) || continue

  HITS=$(echo "$CONTENT" | grep -nIE "$TOKENS" || true)
  if [ -n "$HITS" ]; then
    FAIL=1
    echo "❌ $f 에 토큰으로 보이는 패턴(값은 마스킹됨):" >&2
    echo "$HITS" \
      | sed -E 's/(xox[baprs]-|ghp_|github_pat_|sk-ant-)[A-Za-z0-9_-]+/\1████/g; s/-----BEGIN [A-Z ]*PRIVATE KEY-----/[PRIVATE KEY 블록]/' \
      | cut -c1-120 | head -5 | sed 's/^/   /' >&2
    echo >&2
  fi

  ID_HITS=$(echo "$CONTENT" | grep -nIE "$SLACK_IDS" || true)
  if [ -n "$ID_HITS" ]; then
    FAIL=1
    echo "❌ $f 에 슬랙 원시 ID 로 보이는 값(마스킹됨) — 환경변수 이름으로 바꾸세요:" >&2
    echo "$ID_HITS" | sed -E 's/\b([CGU]0)[A-Z0-9]{8,}\b/\1████/g' \
      | cut -c1-120 | head -5 | sed 's/^/   /' >&2
    echo "   예: SLACK_CHANNEL_ID_<프로젝트> (값은 .env·루틴 시크릿에만)" >&2
    echo >&2
  fi
done <<< "$STAGED"

if [ "$FAIL" = "1" ]; then
  echo "   진짜 토큰이면: 제거 후 즉시 폐기·재발급하세요(이미 노출 가정)." >&2
  echo "   오탐이면: SKIP_SECRET_GUARD=1 git commit …" >&2
  exit 1
fi
exit 0
