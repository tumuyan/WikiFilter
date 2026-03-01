#!/bin/bash

# 下载 GitHub Release 文件的脚本
# 用法: ./download-release.sh [url]
# 无参数时自动获取最新 release，使用 Python 计算版本日期

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="tumuyan/WikiFilter"

# 获取下载 URL
if [ -n "$1" ]; then
    # 使用用户提供的 URL
    DOWNLOAD_URL="$1"
else
    # 自动获取最新 release
    echo "正在获取最新 Release..."

    # 使用 Python 获取版本日期
    VERSION_OUTPUT=$(python3 "$SCRIPT_DIR/get-wiki-version.py")
    VERSION=$(echo "$VERSION_OUTPUT" | grep "^WIKI_VERSION=" | cut -d'=' -f2)
    echo "当前 Wiki dump 版本: $VERSION"

    # 通过 GitHub API 获取最新 release 的下载链接
    API_URL="https://api.github.com/repos/$REPO/releases/latest"
    DOWNLOAD_URL=$(curl -s "$API_URL" | grep "browser_download_url.*tar.gz" | head -1 | cut -d'"' -f4)

    if [ -z "$DOWNLOAD_URL" ]; then
        echo "错误: 无法获取下载链接"
        exit 1
    fi
fi

echo "Download URL: $DOWNLOAD_URL"

# 提取文件名
FILENAME=$(basename "$DOWNLOAD_URL" | cut -d'?' -f1)
echo "Filename: $FILENAME"

# 检查文件是否已存在
if [ -f "$FILENAME" ]; then
    echo "File already exists: $FILENAME"
    read -p "Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Download cancelled"
        exit 0
    fi
    rm -f "$FILENAME"
fi

# 下载文件
echo "Downloading..."
wget -q --show-progress -O "$FILENAME" "$DOWNLOAD_URL"

# 验证下载
if [ -f "$FILENAME" ]; then
    FILE_SIZE=$(stat -c%s "$FILENAME" 2>/dev/null || stat -f%z "$FILENAME" 2>/dev/null)
    FILE_SIZE_MB=$((FILE_SIZE / 1024 / 1024))
    echo "Download complete: $FILENAME (${FILE_SIZE_MB} MB)"
else
    echo "Download failed"
    exit 1
fi
