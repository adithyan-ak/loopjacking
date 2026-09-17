#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/../.." && pwd)"
harness_dir="$repo_root/experiments/langgraph-agent-server"
evidence_dir="$repo_root/evidence/langgraph-agent-server/langgraph-api-0.13.2-linux-inmem"
image="loopjacking-langgraph-inmem:0.13.2"
container="loopjacking-langgraph-linux-inmem"
run_dir="$(mktemp -d /tmp/loopjacking-langgraph-linux-client.XXXXXX)"
venv_dir="$run_dir/.venv"
mkdir -p "$evidence_dir"

cleanup() {
  docker rm -f "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker build \
  -f "$harness_dir/Dockerfile.linux-inmem" \
  -t "$image" \
  "$harness_dir" \
  > "$evidence_dir/build.log" 2>&1
docker image inspect "$image" > "$evidence_dir/image-inspect.json"

docker run -d \
  --name "$container" \
  -p 127.0.0.1:8143:8000 \
  -e LEDGER_PATH=/evidence/ledger.jsonl \
  -e ATTEMPTS_PATH=/evidence/attempts.jsonl \
  -e AUTH_LOG_PATH=/evidence/auth.jsonl \
  -e LAB_JWT_SECRET=loopback-only-research-secret-32-bytes-minimum \
  -e LANGSMITH_TRACING=false \
  -v "$evidence_dir:/evidence" \
  "$image" >/dev/null

uv venv --python 3.12 "$venv_dir" >/dev/null
uv pip install --python "$venv_dir/bin/python" \
  httpx==0.28.1 PyJWT==2.13.0 >/dev/null

set +e
"$venv_dir/bin/python" "$harness_dir/client.py" \
  --base-url http://127.0.0.1:8143 \
  --output-dir "$evidence_dir" \
  --version 0.13.2 \
  --langchain-version 1.3.18 \
  --expected attack \
  > "$evidence_dir/stdout.txt" 2>&1
client_status=$?
set -e
docker logs "$container" > "$evidence_dir/server.log" 2>&1

printf '%s\n' \
  'bash experiments/langgraph-agent-server/run_linux_inmem.sh' \
  > "$evidence_dir/reproduction-command.txt"
printf '%s\n' "$client_status" > "$evidence_dir/client-exit-status.txt"

(
  cd "$repo_root"
  shasum -a 256 \
    experiments/langgraph-agent-server/Dockerfile.linux-inmem \
    experiments/langgraph-agent-server/auth.py \
    experiments/langgraph-agent-server/client.py \
    experiments/langgraph-agent-server/graph.py \
    experiments/langgraph-agent-server/langgraph.json \
    experiments/langgraph-agent-server/run_linux_inmem.sh \
    > "$evidence_dir/harness-SHA256SUMS"
)
(
  cd "$evidence_dir"
  shasum -a 256 \
    attempts.jsonl \
    auth.jsonl \
    build.log \
    client-exit-status.txt \
    harness-SHA256SUMS \
    image-inspect.json \
    ledger.jsonl \
    raw-http.jsonl \
    reproduction-command.txt \
    results.json \
    server.log \
    stdout.txt \
    > SHA256SUMS
)

if [[ "$client_status" -ne 0 ]] || ! jq -e '.strict_positive == true' "$evidence_dir/results.json" >/dev/null; then
  echo "Linux in-memory repeat failed" >&2
  exit 1
fi
jq . "$evidence_dir/results.json"
