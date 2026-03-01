#!/bin/bash
# 下载维基百科 dump 文件

set -e

# 默认参数
VERSION="${1:-}"
OUTPUT_DIR="${2:-.}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== 下载维基百科 Dump ==="

# 如果没有提供版本号，使用 Python 脚本自动计算（带文件可用性检查）
if [ -z "$VERSION" ]; then
    echo "自动计算版本号..."
    eval $(python3 "$SCRIPT_DIR/get-wiki-version.py" --check-file)
    VERSION="$WIKI_VERSION"
    echo "版本: $VERSION (回退: ${WIKI_FALLBACK:-否})"
fi

cd "$OUTPUT_DIR"
echo "输出目录: $(pwd)"

FILENAME="zhwiki-${VERSION}-pages-articles-multistream.xml.bz2"

if [ -f "$FILENAME" ]; then
    echo "文件已存在: $FILENAME"
else
    URL="https://dumps.wikimedia.org/zhwiki/${VERSION}/${FILENAME}"
    echo "下载: $URL"
    curl -o "$FILENAME" "$URL"
fi

# 解压
XML_FILE="zhwiki-${VERSION}-pages-articles-multistream.xml"
if [ ! -f "$XML_FILE" ]; then
    echo "解压 $FILENAME ..."
    7z x "$FILENAME"
fi

# 重命名为标准名称
if [ -f "$XML_FILE" ] && [ ! -f "zhwiki.xml" ]; then
    mv "$XML_FILE" zhwiki.xml
fi

echo "=== 下载完成 ==="
echo "VERSION=$VERSION"
ls -lh zhwiki.xml 2>/dev/null || echo "警告: zhwiki.xml 不存在"
