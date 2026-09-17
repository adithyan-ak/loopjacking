#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for AGNO_VERSION in 2.5.5 2.5.6; do
  bash "${SCRIPT_DIR}/run_version.sh" "${AGNO_VERSION}"
done
