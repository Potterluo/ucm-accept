#!/usr/bin/env bash
# CI / 构建机虚跑：不连接真实模型，验证完整链路。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT="${1:-/tmp/ucm-smoke}"

rm -rf "$OUT"
ucm-accept --mock --fast --all --outputs "$OUT"
REPORT="$(ls -d "$OUT"/runs/*/report.json | head -1)"
python scripts/verify_report.py "$REPORT"
ucm-accept --doctor --mock
ucm-accept --mock --fast --item perf --outputs "$OUT/export" --report "$OUT/export/report.html"
test -s "$OUT/export/report.html"
echo "虚跑通过：$REPORT"
