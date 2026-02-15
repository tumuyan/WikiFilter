#!/bin/bash
# 构建 WikiFilter 工具

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
WIKIFILTER_DIR="$PROJECT_ROOT/WikiFilter"

echo "=== 构建 WikiFilter ==="

if [ ! -d "$WIKIFILTER_DIR" ]; then
    echo "错误: WikiFilter 目录不存在: $WIKIFILTER_DIR"
    exit 1
fi

cd "$WIKIFILTER_DIR"
echo "工作目录: $(pwd)"

# 编译（-O3 最高优化，-pthread 多线程支持）
g++ -O3 -pthread -o WikiFilter WikiFilter.cpp
chmod +x WikiFilter

echo "构建完成: $WIKIFILTER_DIR/WikiFilter"
ls -lh WikiFilter
