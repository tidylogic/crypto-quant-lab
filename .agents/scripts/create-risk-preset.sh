#!/usr/bin/env bash
# Keep this executable checked out with LF line endings; see .gitattributes.
set -euo pipefail
usage() { printf '%s\n' '사용법: bash .agents/scripts/create-risk-preset.sh <PRESET-ID> [--output-root DIR]' '기본 출력 경로: .agents/templates/trading-experiments/risk-presets'; }
if [[ "${1:-}" == "--help" ]]; then usage; exit 0; fi
if [[ $# -lt 1 ]]; then usage >&2; exit 1; fi
preset_id=$1; shift
if [[ ! $preset_id =~ ^(STOP|TP|SCALE)-[A-Z0-9][A-Z0-9-]*$ ]]; then echo "잘못된 프리셋 ID: $preset_id" >&2; exit 1; fi
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/../.." && pwd)
output_root="$repo_root/.agents/templates/trading-experiments/risk-presets"
if [[ $# -gt 0 ]]; then
    if [[ $1 != "--output-root" || $# -ne 2 || -z ${2:-} ]]; then usage >&2; exit 1; fi
    output_root=$2
fi
target="$output_root/$preset_id.md"
mkdir -p -- "$output_root"
temporary=$(mktemp "$output_root/.${preset_id}.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT
{
    printf '%s\n' '# 리스크 프리셋 카드' '' "- **프리셋 ID:** $preset_id" "- **계층:** ${preset_id%%-*}" '- **상태:** [초안 / 검토 완료 / 사용 중단]'
    cat <<'EOF'

## 적용 장세

- **허용 장세:** `[추세/횡보, 변동성, 유동성, 세션 등 관측 가능한 조건]`
- **제외 장세:** `[사용하면 안 되는 관측 가능한 조건]`

## 규칙

- **계산식과 필요 입력값:** `[완결된 캔들 기준의 정확한 식과 값]`
- **허용 범위:** `[사전 등록할 제한된 범위 또는 정확한 값]`
- **발동 조건:** `[주문·청산을 발생시키는 정확한 조건]`
- **금지 조건:** `[사용·추가 진입·조건 변경을 금지하는 조건]`
- **주문/청산 동작:** `[진입·부분청산·보호 주문·감소 전용 규칙]`

## 비용과 실패 조건

- **수수료·스프레드·슬리피지·펀딩 가정:** `[백테스트에 반영할 방법]`
- **실패/무효화 조건:** `[이 프리셋이 유효하지 않음을 뜻하는 조건]`
- **주의점:** `[편향, 유동성, 갭, 다른 프리셋과의 비호환성]`

## 검토 확인

- [ ] 모든 필드를 채웠고 규칙이 모호하지 않다.
- [ ] 하드 리스크 한도를 완화하지 않는다.
- [ ] 계층별 최대 두 ID와 전체 최대 여덟 조합 규칙을 지킨다.
EOF
} > "$temporary"
if ! ln -- "$temporary" "$target"; then echo "기존 프리셋 카드를 덮어쓸 수 없습니다: $target" >&2; exit 1; fi
rm -f -- "$temporary"
trap - EXIT
echo "리스크 프리셋 카드 생성됨: $target"
