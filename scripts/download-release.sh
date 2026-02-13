#!/bin/bash

# 下载 GitHub Release 文件的脚本
# 用法: ./download-release.sh [url]
# 示例: ./download-release.sh https://github.com/user/repo/releases/download/tag/file.tar.gz

set -e

# 默认下载路径
DEFAULT_URL="https://github.com/tumuyan/WikiFilter/releases/download/pre-20240501/zhwiki-20260201-extracted.tar.gz"

# 接收参数或使用默认值
DOWNLOAD_URL="${1:-$DEFAULT_URL}"

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
