#!/bin/bash
# 下载词库文件

set -e

# 参数
SOURCE="${1:-wiki}"  # wiki, release, url
VERSION="${2:-}"
DICT_URL="${3:-}"
DICT_NAME="${4:-dict.txt}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=== 下载词库 ==="
echo "来源: $SOURCE"
echo "词库名: $DICT_NAME"

cd "$PROJECT_ROOT"

# 如果没有提供版本号，使用 Python 脚本自动计算（带文件可用性检查）
if [ -z "$VERSION" ]; then
    eval $(python3 "$SCRIPT_DIR/get-wiki-version.py" --check-file)
    VERSION="$WIKI_VERSION"
fi

echo "版本: $VERSION"
if [ -n "$WIKI_FALLBACK" ]; then
    echo "注意: 使用了回退版本"
fi

# 检查词库文件是否已存在
if [ -f "$DICT_NAME" ]; then
    echo "词库文件已存在: $DICT_NAME"
    echo "跳过下载"
    echo "如需重新下载，请先删除该文件"
    exit 0
fi

case "$SOURCE" in
    url)
        if [ -z "$DICT_URL" ]; then
            echo "错误: 使用 url 来源时必须提供下载地址"
            exit 1
        fi
        echo "从 URL 下载: $DICT_URL"
        wget -O "$DICT_NAME" "$DICT_URL"
        ;;
    release)
        echo "从 GitHub Release 下载..."
        REPO_URL="https://api.github.com/repos/${GITHUB_REPOSITORY:-tumuyan/wikiparse}/releases/latest"
        RELEASE_INFO=$(wget -qO- "$REPO_URL" 2>/dev/null || curl -s "$REPO_URL")
        DOWNLOAD_URL=$(echo "$RELEASE_INFO" | jq -r '.assets[] | select(.name | contains("'"$DICT_NAME"'")) | .browser_download_url' | head -1)
        
        if [ -z "$DOWNLOAD_URL" ] || [ "$DOWNLOAD_URL" = "null" ]; then
            echo "错误: 无法找到包含 '$DICT_NAME' 的 release 资源"
            exit 1
        fi
        
        echo "下载地址: $DOWNLOAD_URL"
        wget -O "$DICT_NAME" "$DOWNLOAD_URL"
        ;;
    wiki|*)
        echo "从维基百科下载标题列表..."
        FILENAME="zhwiki-${VERSION}-all-titles-in-ns0"
        
        # 检查压缩包是否已存在
        if [ -f "${FILENAME}" ]; then
            echo "标题列表文件已存在: ${FILENAME}"
            mv "$FILENAME" "$DICT_NAME"
        elif [ -f "${FILENAME}.gz" ]; then
            echo "压缩包已存在，解压中..."
            7z x "${FILENAME}.gz"
            mv "$FILENAME" "$DICT_NAME"
            rm -f "${FILENAME}.gz"
        else
            wget "https://dumps.wikimedia.org/zhwiki/${VERSION}/${FILENAME}.gz"
            7z x "${FILENAME}.gz"
            mv "$FILENAME" "$DICT_NAME"
            rm -f "${FILENAME}.gz"
        fi
        ;;
esac

echo "=== 下载完成 ==="
ls -lh "$DICT_NAME"
