#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
versions=(
  0.7.4
  0.7.5
  0.7.103
  0.8.7
  0.9.1
  0.10.3
  0.11.4
  0.12.4
  0.12.6
  0.12.9
  0.13.2
)

for version in "${versions[@]}"; do
  bash "$script_dir/run_version.sh" "$version" 1.3.18
done
