#!/usr/bin/env bash
set -euo pipefail

if [[ $# -gt 1 ]]; then
  echo "usage: $0 [openai-agents-version]" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENV_ROOT="$(mktemp -d /tmp/loopjacking-openai-control.XXXXXX)"
VENV_DIR="${VENV_ROOT}/venv"
OPENAI_AGENTS_VERSION="${1:-0.22.0}"

uv venv --python 3.12 "${VENV_DIR}"
uv pip install --python "${VENV_DIR}/bin/python" "openai-agents==${OPENAI_AGENTS_VERSION}"
OPENAI_AGENTS_DISABLE_TRACING=1 "${VENV_DIR}/bin/python" \
  "${SCRIPT_DIR}/run_experiment.py" \
  --output-root "${REPO_ROOT}/evidence/openai-agents-approval-control"
