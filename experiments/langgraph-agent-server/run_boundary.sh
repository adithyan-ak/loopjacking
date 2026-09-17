#!/usr/bin/env bash
set -euo pipefail

harness_dir="$(cd "$(dirname "$0")" && pwd)"

bash "$harness_dir/run_version.sh" 0.7.4 1.3.15
bash "$harness_dir/run_version.sh" 0.7.5 1.3.15
