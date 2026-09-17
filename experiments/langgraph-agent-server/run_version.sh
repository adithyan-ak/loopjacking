#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 <langgraph-api-version> [langchain-version]" >&2
  exit 2
fi

api_version="$1"
langchain_version="${2:-1.3.15}"
experiment_mode="${LANGGRAPH_EXPERIMENT_MODE:-attack}"
if [[ "$experiment_mode" != "attack" && "$experiment_mode" != "safe-policy" ]]; then
  echo "LANGGRAPH_EXPERIMENT_MODE must be attack or safe-policy" >&2
  exit 2
fi
repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
harness_dir="$repo_root/experiments/langgraph-agent-server"
evidence_suffix=""
if [[ "$experiment_mode" == "safe-policy" ]]; then
  evidence_suffix="-safe-policy"
fi
evidence_dir="$repo_root/evidence/langgraph-agent-server/langgraph-api-$api_version$evidence_suffix"
run_dir="$(mktemp -d "/tmp/loopjacking-langgraph-${api_version}.XXXXXX")"
venv_dir="$run_dir/.venv"
app_dir="$run_dir/app"
case "$api_version" in
  0.12.4) default_port=8124 ;;
  0.12.6) default_port=8126 ;;
  0.13.2) default_port=8132 ;;
  *) default_port=8137 ;;
esac
port="${LANGGRAPH_TEST_PORT:-$default_port}"

mkdir -p "$evidence_dir"
mkdir -p "$app_dir"
cp \
  "$harness_dir/auth.py" \
  "$harness_dir/graph.py" \
  "$harness_dir/langgraph.json" \
  "$app_dir/"
uv venv --python 3.12 "$venv_dir" >/dev/null
uv pip install --python "$venv_dir/bin/python" \
  "langgraph-api==$api_version" \
  "langgraph-cli[inmem]==0.4.31" \
  "langgraph==1.2.11" \
  "langchain==$langchain_version" >/dev/null

export LEDGER_PATH="$evidence_dir/ledger.jsonl"
export ATTEMPTS_PATH="$evidence_dir/attempts.jsonl"
export AUTH_LOG_PATH="$evidence_dir/auth.jsonl"
export LAB_JWT_SECRET="loopback-only-research-secret-32-bytes-minimum"
export LANGSMITH_TRACING=false
if [[ "$experiment_mode" == "safe-policy" ]]; then
  export SAFE_POLICY=deny-update
else
  unset SAFE_POLICY || true
fi

uv pip freeze --python "$venv_dir/bin/python" > "$evidence_dir/pip-freeze.txt"
(
  cd "$app_dir"
  exec "$venv_dir/bin/langgraph" dev \
    --allow-blocking \
    --no-browser \
    --no-reload \
    --host 127.0.0.1 \
    --port "$port" \
    --config langgraph.json
) > "$evidence_dir/server.log" 2>&1 &
server_pid=$!
cleanup() {
  kill "$server_pid" 2>/dev/null || true
  wait "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT

"$venv_dir/bin/python" "$harness_dir/client.py" \
  --base-url "http://127.0.0.1:$port" \
  --output-dir "$evidence_dir" \
  --version "$api_version" \
  --langchain-version "$langchain_version" \
  --expected "$experiment_mode" \
  | tee "$evidence_dir/stdout.txt"

cleanup
trap - EXIT

"$venv_dir/bin/python" "$harness_dir/collect_source_receipts.py" \
  > "$evidence_dir/source-receipts.json"
if [[ "$experiment_mode" == "safe-policy" ]]; then
  printf 'LANGGRAPH_EXPERIMENT_MODE=safe-policy bash experiments/langgraph-agent-server/run_version.sh %s %s\n' \
    "$api_version" "$langchain_version" > "$evidence_dir/reproduction-command.txt"
else
  printf 'bash experiments/langgraph-agent-server/run_version.sh %s %s\n' \
    "$api_version" "$langchain_version" > "$evidence_dir/reproduction-command.txt"
fi
(
  cd "$repo_root"
  shasum -a 256 \
    experiments/langgraph-agent-server/Dockerfile.linux-inmem \
    experiments/langgraph-agent-server/README.md \
    experiments/langgraph-agent-server/auth.py \
    experiments/langgraph-agent-server/client.py \
    experiments/langgraph-agent-server/collect_source_receipts.py \
    experiments/langgraph-agent-server/graph.py \
    experiments/langgraph-agent-server/langgraph.json \
    experiments/langgraph-agent-server/requirements.txt \
    experiments/langgraph-agent-server/run_all.sh \
    experiments/langgraph-agent-server/run_boundary.sh \
    experiments/langgraph-agent-server/run_linux_inmem.sh \
    experiments/langgraph-agent-server/run_range_matrix.sh \
    experiments/langgraph-agent-server/run_safe_policy.sh \
    experiments/langgraph-agent-server/scan_release_range.py \
    experiments/langgraph-agent-server/run_version.sh \
    > "$evidence_dir/harness-SHA256SUMS"
)
(
  cd "$evidence_dir"
  shasum -a 256 \
    attempts.jsonl \
    auth.jsonl \
    harness-SHA256SUMS \
    ledger.jsonl \
    pip-freeze.txt \
    raw-http.jsonl \
    reproduction-command.txt \
    results.json \
    server.log \
    source-receipts.json \
    stdout.txt \
    > SHA256SUMS
)
