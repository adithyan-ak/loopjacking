#!/usr/bin/env bash
set -euo pipefail

LANGGRAPH_EXPERIMENT_MODE=safe-policy \
  bash "$(dirname "$0")/run_version.sh" 0.13.2 1.3.18
