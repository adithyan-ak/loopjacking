#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 OPENCLAW_WORKTREE EXPECT_ATTACK OUTPUT_DIR" >&2
  exit 2
fi

target_root=$1
expect_attack=$2
output_dir=$3
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
test_source="$repo_root/experiments/openclaw-approval-binding/openclaw-loopjacking.integration.test.ts"
test_target="$target_root/src/gateway/loopjacking-approval-binding.integration.test.ts"

if [[ "$expect_attack" != "0" && "$expect_attack" != "1" ]]; then
  echo "EXPECT_ATTACK must be 0 or 1" >&2
  exit 2
fi
if [[ ! -x "$target_root/node_modules/.bin/vitest" ]]; then
  echo "install the pinned OpenClaw dependencies first" >&2
  exit 2
fi

mkdir -p "$output_dir"
installed_test=0
if [[ -e "$test_target" ]]; then
  cmp -s "$test_source" "$test_target" || {
    echo "refusing to overwrite a different target test" >&2
    exit 2
  }
else
  install -m 0644 "$test_source" "$test_target"
  installed_test=1
fi
cleanup() {
  if [[ "$installed_test" == "1" ]]; then
    rm -f "$test_target"
  fi
}
trap cleanup EXIT

for trial in 1 2 3; do
  (
    cd "$target_root"
    OPENCLAW_EXPECT_ATTACK="$expect_attack" \
      corepack pnpm exec vitest run \
      src/gateway/loopjacking-approval-binding.integration.test.ts \
      --config vitest.gateway.config.ts --reporter=verbose
  ) 2>&1 | tee "$output_dir/trial-$trial.stdout.txt"
  rg '^OPENCLAW_LOOPJACKING_RESULT=' "$output_dir/trial-$trial.stdout.txt" \
    | sed 's/^OPENCLAW_LOOPJACKING_RESULT=//' \
    | jq . > "$output_dir/trial-$trial.json"
done

jq -s . "$output_dir"/trial-*.json > "$output_dir/results.json"
(
  cd "$target_root"
  jq -n \
    --arg commit "$(git rev-parse HEAD)" \
    --arg describe "$(git describe --tags --exact-match HEAD)" \
    --arg node "$(node --version)" \
    --arg pnpm "$(corepack pnpm --version)" \
    --arg platform "$(uname -a)" \
    '{git_commit:$commit,git_tag:$describe,node:$node,pnpm:$pnpm,platform:$platform}'
) > "$output_dir/environment.json"

jq -n \
  --arg target "openclaw@$(jq -r .version "$target_root/package.json")" \
  --arg expected "$expect_attack" \
  --arg verified_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg reproduction "bash experiments/openclaw-approval-binding/capture_version.sh <pinned-openclaw-worktree> $expect_attack <output-dir>" \
  '{
    claim:(if $expected == "1" then
      "The released affected target consumed a genuine approval for displayed A to release materially different B through its native gateway and node-host path."
    else
      "The released fixed target rejected the displayed-A/complete-B mismatch before node execution while unchanged approved A still executed."
    end),
    execution_scope:"released product over loopback gateway transport",
    target:$target,
    reproduction_command:$reproduction,
    oracle:{trials:3,expected_attack:($expected == "1"),direct_b_denied:true,unchanged_a_executes:true},
    result:(if $expected == "1" then "strict_positive" else "fixed_rejection" end),
    limitations:[
      "Loopback transport and a harmless temporary marker were used.",
      "The distinct approval-role client was scripted after asserting the exact product event; human factors and GUI comprehension were not measured.",
      "This experiment establishes only the pinned released target and the tested shell-wrapper argv path."
    ],
    contradicting_evidence:[],
    verified_at:$verified_at,
    next_falsifying_experiment:"Rerun the same oracle on any disputed boundary or later release."
  }' > "$output_dir/claim.json"

jq -n \
  --arg version "$(jq -r .version "$target_root/package.json")" \
  --arg expected "$expect_attack" \
  '{
    experiment:"openclaw-representation-binding-native",
    target:{package:"openclaw",version:$version},
    execution_scope:"released product over loopback gateway transport",
    expected_attack:($expected == "1"),
    completed_trials:3,
    external_effects:"none; loopback gateway and temporary marker only"
  }' > "$output_dir/manifest.json"

jq -n \
  --arg resolver_commit "$(cd "$target_root" && git log -1 --format=%H -- src/infra/system-run-command.ts)" \
  --arg resolver_sha "$(shasum -a 256 "$target_root/src/infra/system-run-command.ts" | awk '{print $1}')" \
  --argjson resolver_size "$(wc -c < "$target_root/src/infra/system-run-command.ts" | tr -d ' ')" \
  --arg approval_sha "$(shasum -a 256 "$target_root/src/gateway/node-invoke-system-run-approval.ts" | awk '{print $1}')" \
  --argjson approval_size "$(wc -c < "$target_root/src/gateway/node-invoke-system-run-approval.ts" | tr -d ' ')" \
  --arg invoke_sha "$(shasum -a 256 "$target_root/src/node-host/invoke-system-run.ts" | awk '{print $1}')" \
  --argjson invoke_size "$(wc -c < "$target_root/src/node-host/invoke-system-run.ts" | tr -d ' ')" \
  '{
    resolver_commit:$resolver_commit,
    files:{
      "src/infra/system-run-command.ts":{sha256:$resolver_sha,size:$resolver_size},
      "src/gateway/node-invoke-system-run-approval.ts":{sha256:$approval_sha,size:$approval_size},
      "src/node-host/invoke-system-run.ts":{sha256:$invoke_sha,size:$invoke_size}
    }
  }' > "$output_dir/source-receipts.json"

jq -n \
  --arg readme_sha "$(shasum -a 256 "$repo_root/experiments/openclaw-approval-binding/README.md" | awk '{print $1}')" \
  --arg capture_sha "$(shasum -a 256 "$repo_root/experiments/openclaw-approval-binding/capture_version.sh" | awk '{print $1}')" \
  --arg test_sha "$(shasum -a 256 "$test_source" | awk '{print $1}')" \
  '{files:{
    "README.md":{sha256:$readme_sha},
    "capture_version.sh":{sha256:$capture_sha},
    "openclaw-loopjacking.integration.test.ts":{sha256:$test_sha}
  }}' > "$output_dir/harness-checksums.json"

(
  cd "$output_dir"
  shasum -a 256 claim.json environment.json harness-checksums.json manifest.json results.json \
    source-receipts.json trial-*.json trial-*.stdout.txt \
    > SHA256SUMS
)
