#!/usr/bin/env bash
# 构建 Linux PyInstaller onedir + deb/rpm。需在目标架构构建机上执行。
set -euo pipefail

VERSION="${1:-1.1.0}"
ARCH="${2:-amd64}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "缺少 pyinstaller：pip install '.[build]'" >&2
  exit 1
fi
if ! command -v nfpm >/dev/null 2>&1; then
  echo "缺少 nfpm：https://nfpm.goreleaser.com/install/" >&2
  exit 1
fi

pyinstaller --noconfirm --clean packaging/ucm-accept.spec
rm -rf "dist/ucm-accept-linux-${ARCH}"
mv dist/ucm-accept "dist/ucm-accept-linux-${ARCH}"

mkdir -p dist
ARCH="$ARCH" VERSION="$VERSION" nfpm package -f packaging/nfpm.yaml -p deb \
  -t "dist/ucm-accept_${VERSION}_${ARCH}.deb"
ARCH="$ARCH" VERSION="$VERSION" nfpm package -f packaging/nfpm.yaml -p rpm \
  -t "dist/ucm-accept-${VERSION}-1.${ARCH}.rpm"

echo "完成："
ls -lh dist/ucm-accept-linux-"${ARCH}" dist/*.deb dist/*.rpm
