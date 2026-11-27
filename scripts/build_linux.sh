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

# bfcl-eval 依赖链会拉入过时的 pathlib backport，PyInstaller 拒绝与其共存
pip uninstall -y pathlib 2>/dev/null || true
pyinstaller --noconfirm --clean packaging/ucm-accept.spec
rm -rf "dist/ucm-accept-linux-${ARCH}"
mv dist/ucm-accept "dist/ucm-accept-linux-${ARCH}"

case "$ARCH" in
  amd64) RPM_ARCH="x86_64" ;;
  arm64) RPM_ARCH="aarch64" ;;
  *) echo "不支持的架构：$ARCH（只支持 amd64 / arm64）" >&2; exit 1 ;;
esac

mkdir -p dist
render_config() {
  local pkg_arch="$1"
  local out="$2"
  sed -e "s|\${PKG_ARCH}|${pkg_arch}|g"       -e "s|\${DIR_ARCH}|${ARCH}|g"       -e "s|\${VERSION}|${VERSION}|g" packaging/nfpm.yaml > "$out"
}

render_config "$ARCH" /tmp/ucm-nfpm-deb.yaml
nfpm package -f /tmp/ucm-nfpm-deb.yaml -p deb \
  -t "dist/ucm-accept_${VERSION}_${ARCH}.deb"

render_config "$RPM_ARCH" /tmp/ucm-nfpm-rpm.yaml
nfpm package -f /tmp/ucm-nfpm-rpm.yaml -p rpm \
  -t "dist/ucm-accept-${VERSION}-1.${RPM_ARCH}.rpm"

tar -C dist -czf "dist/ucm-accept-linux-${ARCH}.tar.gz" "ucm-accept-linux-${ARCH}"

echo "完成："
ls -lh "dist/ucm-accept-linux-${ARCH}.tar.gz" dist/*.deb dist/*.rpm
