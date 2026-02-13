#!/bin/bash
# 处理词库文件（使用 Dict-Trick 清理）

set -e

# 参数
DICT_NAME="${1:-dict.txt}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== 处理词库 ==="
echo "词库文件: $DICT_NAME"

cd "$PROJECT_ROOT"

# 检查词库文件
if [ ! -f "$DICT_NAME" ]; then
    echo "错误: 词库文件不存在: $DICT_NAME"
    exit 1
fi

# 下载 Dict-Trick
if [ ! -f "Clean.jar" ]; then
    echo "下载 Dict-Trick..."
    # 使用 GitHub API 获取最新 release
    REPO_URL="https://api.github.com/repos/tumuyan/Dict-Trick/releases/latest"
    RELEASE_INFO=$(curl -s "$REPO_URL")
    DOWNLOAD_URL=$(echo "$RELEASE_INFO" | jq -r '.assets[] | select(.name == "Clean.jar") | .browser_download_url')
    
    if [ -z "$DOWNLOAD_URL" ] || [ "$DOWNLOAD_URL" = "null" ]; then
        echo "错误: 无法下载 Clean.jar"
        exit 1
    fi
    
    wget -O Clean.jar "$DOWNLOAD_URL"
fi

# 运行清理
echo "运行词库清理..."
java -jar Clean.jar -i "$DICT_NAME" -c scripts/dict-tick-preprocess.txt

# 重命名输出文件
filename="${DICT_NAME%.*}"
if [ -f "${filename}.dict.txt" ]; then
    echo "重命名输出文件..."
    mv "$DICT_NAME" "${filename}.raw.txt"
    mv "${filename}.dict.txt" "$DICT_NAME"
fi

echo "=== 处理完成 ==="
echo "词库文件:"
ls -lh "${filename}"*
