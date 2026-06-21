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
echo "==> 获取最新发行版信息 ..."
LATEST_JSON="$(curl -sfL "https://api.github.com/repos/$REPO/releases/latest")"

# 根据架构查找对应的下载链接
DOWNLOAD_URL="$(echo "$LATEST_JSON" | grep -oP '"browser_download_url":\s*"[^"]*'"$SUFFIX"'[^"]*\.tar\.gz"' | grep -oP 'https://[^"]+')"

if [[ -z "$DOWNLOAD_URL" ]]; then
  echo "错误：未找到 $SUFFIX 的 tar.gz 下载链接" >&2
  exit 1
fi

TMP_FILE="/tmp/imewlconverter_${SUFFIX}.tar.gz"

echo "==> 下载 $(basename "$DOWNLOAD_URL") ..."
curl -fSL "$DOWNLOAD_URL" -o "$TMP_FILE"

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

# 添加到当前 shell 环境变量
export DOTNET_ROOT="$HOME/.dotnet"
export PATH="$DOTNET_ROOT:$PATH"

cd imewlconverter

wget 'https://pinyin.sogou.com/d/dict/download_cell.php?id=4&name=%E7%BD%91%E7%BB%9C%E6%B5%81%E8%A1%8C%E6%96%B0%E8%AF%8D&f=detail' -O liuxing.scel

./ImeWlConverterCmd  liuxing.scel  -i scel -o rime -O liuxing.yaml -t pinyin

python3 ../optimize_dict.py  liuxing.yaml --fix

# 为优化后的词库添加文件头
HEADER="""# Rime dictionary
# encoding: utf-8
#
# pinyin_simp_liuxing.dict.yaml
#
# 网络流行新词细胞词库
#
---
name: pinyin_simp_liuxing
version: \"$(date +%Y%m%d)\"
sort: by_weight
use_preset_vocabulary: false
...
"""

# 将文件头写入临时文件，再拼接词库内容
echo "$HEADER" > liuxing_optimized_header.yaml
cat liuxing_optimized.yaml >> liuxing_optimized_header.yaml
mv liuxing_optimized_header.yaml pinyin_simp_liuxing.dict.yaml

echo "finish dump pinyin_simp_liuxing.dict.yaml"
