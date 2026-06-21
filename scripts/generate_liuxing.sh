#!/usr/bin/env bash
set -euo pipefail

REPO="studyzy/imewlconverter"
OUTPUT_DIR="$(dirname "$0")/imewlconverter"

# 自动检测架构
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64)  SUFFIX="linux-x64" ;;
  aarch64) SUFFIX="linux-arm64" ;;
  *)
    echo "错误：不支持的架构: $ARCH" >&2
    exit 1
    ;;
esac

echo "==> 检测到架构: $ARCH -> $SUFFIX"

RELEASE_URL="https://github.com/$REPO/releases/latest/download/imewlconverter_${SUFFIX}.tar.gz"
TMP_FILE="/tmp/imewlconverter_${SUFFIX}.tar.gz"

echo "==> 下载 imewlconverter_${SUFFIX}.tar.gz ..."
curl -fSL --retry 3 --retry-delay 2 "$RELEASE_URL" -o "$TMP_FILE"

echo "==> 解压缩到 $OUTPUT_DIR ..."
mkdir -p "$OUTPUT_DIR"
tar -xzf "$TMP_FILE" -C "$OUTPUT_DIR"

echo "==> 清理临时文件 ..."
rm -f "$TMP_FILE"

echo "==> 完成！文件已解压到: $OUTPUT_DIR"
ls -lh "$OUTPUT_DIR"


# 注册 Microsoft 包源
wget https://dot.net/v1/dotnet-install.sh -O /tmp/dotnet-install.sh
chmod +x /tmp/dotnet-install.sh

# 安装 .NET 10.0 SDK（包含运行时）
/tmp/dotnet-install.sh --channel 10.0 --install-dir "$HOME/.dotnet"

