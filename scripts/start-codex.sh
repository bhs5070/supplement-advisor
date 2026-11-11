#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PROMPT_FILE="$PROJECT_ROOT/docs/cli-start-prompt.md"

case "${1:-}" in
  --help|-h)
    printf '%s\n' '사용법: bash scripts/start-codex.sh [--check]' \
      '인수 없음: 팀 Agent 구현을 이어갈 Codex CLI 대화 시작' \
      '--check: CLI 설치와 인계 파일 확인 (모델 호출 없음)'
    exit 0
    ;;
  --check|'') ;;
  *) printf '%s\n' '지원하지 않는 인수입니다. --help를 확인하세요.' >&2; exit 2 ;;
esac
if (( $# > 1 )); then
  printf '%s\n' '인수는 하나까지만 지정할 수 있습니다.' >&2
  exit 2
fi

if ! command -v codex >/dev/null 2>&1; then
  printf '%s\n' 'Codex CLI를 찾지 못했습니다. README.md의 설치 안내를 확인하세요.' >&2
  exit 127
fi
for file in AGENTS.md docs/handoff.md docs/product-scope.md docs/architecture.md docs/contracts.md docs/tasks.md docs/cli-start-prompt.md; do
  if [[ ! -s "$PROJECT_ROOT/$file" ]]; then
    printf '필수 인계 파일이 없습니다: %s\n' "$file" >&2
    exit 1
  fi
done

if [[ "${1:-}" == --check ]]; then
  codex --version
  printf '프로젝트: %s\n인계 파일: 확인 완료\n' "$PROJECT_ROOT"
  exit 0
fi

exec codex --cd "$PROJECT_ROOT" --model gpt-6.1-sol --enable multi_agent \
  --sandbox workspace-write --ask-for-approval on-request \
  --search --no-alt-screen "$(cat "$PROMPT_FILE")"
