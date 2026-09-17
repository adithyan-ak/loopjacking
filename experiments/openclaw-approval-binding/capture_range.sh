#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 OPENCLAW_WORKTREE TSX_BINARY OUTPUT_DIR" >&2
  exit 2
fi

target_root=$1
tsx_binary=$2
output_dir=$3
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
probe="$repo_root/experiments/openclaw-approval-binding/range_probe.ts"
fix_commit=0f0a680d3df81739ea5088a2f88e65f938b7936b

mkdir -p "$output_dir"
OPENCLAW_ROOT="$target_root" "$tsx_binary" "$probe" 2>&1 \
  | tee "$output_dir/stdout.txt"
rg '^OPENCLAW_RANGE_RESULT=' "$output_dir/stdout.txt" \
  | sed 's/^OPENCLAW_RANGE_RESULT=//' \
  | jq . > "$output_dir/results.json"

(
  cd "$target_root"
  contains_fix=false
  if git merge-base --is-ancestor "$fix_commit" HEAD; then
    contains_fix=true
  fi
  jq -n \
    --arg commit "$(git rev-parse HEAD)" \
    --arg describe "$(git describe --tags --exact-match HEAD)" \
    --argjson contains_fix "$contains_fix" \
    --arg fix_commit "$fix_commit" \
    '{git_commit:$commit,git_tag:$describe,contains_fix_commit:$contains_fix,fix_commit:$fix_commit}'
) > "$output_dir/source-boundary.json"

jq -n \
  --arg target "openclaw@$(jq -r .version "$target_root/package.json")" \
  --arg verified_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{
    claim:"The pinned May target derives the complete shell-wrapper argv representation and rejects a payload-only rawCommand; no command was executed.",
    execution_scope:"released source and resolver behavior",
    target:$target,
    reproduction_command:"bash experiments/openclaw-approval-binding/capture_range.sh <worktree> <tsx> <output>",
    oracle:{executed:false,raw_a_rejected:true,complete_b_derived:true,contains_fix_commit:true},
    result:"fixed_path_present",
    limitations:["This is a source-native resolver check, not a second full gateway execution."],
    contradicting_evidence:["GHSA-2j8v-hwgc-x698 lists an affected range through 2026.5.16 despite the available May tags containing the February fix."],
    verified_at:$verified_at,
    next_falsifying_experiment:"Produce an immutable stable 2026.5.16 artifact lacking the fix, if one exists."
  }' > "$output_dir/claim.json"

jq -n \
  --arg readme_sha "$(shasum -a 256 "$repo_root/experiments/openclaw-approval-binding/README.md" | awk '{print $1}')" \
  --arg capture_sha "$(shasum -a 256 "$repo_root/experiments/openclaw-approval-binding/capture_range.sh" | awk '{print $1}')" \
  --arg probe_sha "$(shasum -a 256 "$probe" | awk '{print $1}')" \
  '{files:{
    "README.md":{sha256:$readme_sha},
    "capture_range.sh":{sha256:$capture_sha},
    "range_probe.ts":{sha256:$probe_sha}
  }}' > "$output_dir/harness-checksums.json"

(
  cd "$output_dir"
  shasum -a 256 claim.json harness-checksums.json results.json source-boundary.json stdout.txt \
    > SHA256SUMS
)
