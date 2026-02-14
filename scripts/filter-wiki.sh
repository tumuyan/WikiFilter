#!/bin/bash
# 过滤维基百科内容（使用词库过滤）

set -e

# 设置 locale 以支持中文处理（尝试多个可用 locale，覆盖 CJK 区域）
setup_locale() {
    for loc in \
        en_US.UTF-8 en_US.utf8 en_GB.UTF-8 en_GB.utf8 \
        C.UTF-8 C.utf8 POSIX.UTF-8 \
        zh_CN.UTF-8 zh_CN.utf8 zh_TW.UTF-8 zh_TW.utf8 \
        zh_HK.UTF-8 zh_HK.utf8 zh_SG.UTF-8 zh_SG.utf8 \
        ja_JP.UTF-8 ja_JP.utf8 \
        ko_KR.UTF-8 ko_KR.utf8; do
        if locale -a 2>/dev/null | grep -iq "^${loc}$"; then
            export LANG="$loc"
            export LC_ALL="$loc"
            echo "使用 locale: $loc"
            return 0
        fi
    done
    
    # 尝试安装 en_US.UTF-8 locale（仅限 apt 系统）
    if command -v apt-get &> /dev/null; then
        echo "尝试生成 en_US.UTF-8 locale..."
        apt-get install -y locales 2>/dev/null || true
        sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen 2>/dev/null || true
        locale-gen en_US.UTF-8 2>/dev/null || true
        if locale -a 2>/dev/null | grep -iq "en_US.UTF-8"; then
            export LANG="en_US.UTF-8"
            export LC_ALL="en_US.UTF-8"
            echo "使用 locale: en_US.UTF-8"
            return 0
        fi
    fi
    
    # 回退到基本 C locale
    export LANG="C"
    export LC_ALL="C"
    echo "警告: 未找到 UTF-8 locale，使用 C locale（可能影响中文处理）"
}
setup_locale

# 参数
DICT_NAME="${1:-dict.txt}"
INPUT_DIR="${2:-text/AA}"
OUTPUT_DIR="${3:-text/AA}"
SPLIT_COUNT="${4:-1}"  # 分片数量，默认1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 检测 Python 命令
if command -v python3 &> /dev/null; then
    PYTHON="python3"
elif command -v python &> /dev/null; then
    PYTHON="python"
else
    echo "错误: 未找到 Python"
    exit 1
fi

echo "=== 过滤维基百科内容 ==="
echo "词库文件: $DICT_NAME"
echo "输入目录: $INPUT_DIR"
echo "输出目录: $OUTPUT_DIR"
echo "分片数量: $SPLIT_COUNT"

cd "$PROJECT_ROOT"

# 检查词库
if [ ! -f "$DICT_NAME" ]; then
    echo "错误: 词库文件不存在: $DICT_NAME"
    exit 1
fi

# 检查并构建 WikiFilter
if [ ! -f "WikiFilter/WikiFilter" ]; then
    echo "构建 WikiFilter..."
    g++ -o WikiFilter/WikiFilter WikiFilter/WikiFilter.cpp
    chmod +x WikiFilter/WikiFilter
fi

# 检查输入文件
if [ -f "$INPUT_DIR/zhwiki.txt" ]; then
    # 需要切分文件
    echo "切分输入文件..."
    $PYTHON scripts/split_file.py "$INPUT_DIR/zhwiki.txt" "$INPUT_DIR/" "$SPLIT_COUNT"
fi

# 处理每个分片
for i in $(seq -f "%02g" 0 $((SPLIT_COUNT - 1))); do
    INPUT_FILE="$INPUT_DIR/wiki_${i}.txt"
    
    if [ ! -f "$INPUT_FILE" ]; then
        echo "跳过不存在的文件: $INPUT_FILE"
        continue
    fi
    
    echo "处理: $INPUT_FILE"
    ./WikiFilter/WikiFilter "$DICT_NAME" "$INPUT_FILE" 1
    
    # 移动输出文件
    if [ -f "${INPUT_FILE}.filted.csv" ]; then
        mv "${INPUT_FILE}.filted.csv" "$OUTPUT_DIR/"
    fi
done

echo "=== 过滤完成 ==="
ls -lh "$OUTPUT_DIR"/*.csv 2>/dev/null || echo "没有生成 CSV 文件"
