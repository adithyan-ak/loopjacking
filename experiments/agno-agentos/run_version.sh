#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 <agno-version>" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
EVIDENCE_ROOT="${REPO_ROOT}/evidence/agno-agentos"
AGNO_VERSION="$1"
VENV_ROOT="$(mktemp -d "/tmp/loopjacking-agno-${AGNO_VERSION}.XXXXXX")"
VENV_DIR="${VENV_ROOT}/venv"

echo "Temporary environment: ${VENV_DIR}"
echo "Evidence root: ${EVIDENCE_ROOT}"

uv venv --python 3.12 "${VENV_DIR}"
uv pip install --python "${VENV_DIR}/bin/python" \
  "agno==${AGNO_VERSION}" \
  "fastapi==0.141.1" \
  "uvicorn==0.52.4" \
  "httpx==0.28.1" \
  "PyJWT==2.13.0" \
  "SQLAlchemy==2.0.52" \
  "python-multipart==0.0.22"
"${VENV_DIR}/bin/python" "${SCRIPT_DIR}/run_matrix.py" --output-root "${EVIDENCE_ROOT}"
