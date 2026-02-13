#!/bin/bash
# 提取维基百科内容

set -e

# 参数
INPUT_FILE="${1:-zhwiki.xml}"
OUTPUT_DIR="${2:-extracted}"
MIN_LENGTH="${3:-100}"

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

echo "=== 提取维基百科内容 ==="
echo "输入文件: $INPUT_FILE"
echo "输出目录: $OUTPUT_DIR"
echo "最小长度: $MIN_LENGTH"

cd "$PROJECT_ROOT"

# 检查输入文件
if [ ! -f "$INPUT_FILE" ]; then
    echo "错误: 输入文件不存在: $INPUT_FILE"
    exit 1
fi

# 安装 wikiextractor
if [ ! -d "wikiextractor" ]; then
    echo "克隆 wikiextractor..."
    git clone https://github.com/tumuyan/wikiextractor
fi

# 运行 Wikiextractor
echo "运行 Wikiextractor..."
$PYTHON -m wikiextractor.wikiextractor.WikiExtractor -b 50G "$INPUT_FILE"

# 整理输出
mkdir -p "$OUTPUT_DIR"
if [ -f "text/AA/wiki_00" ]; then
    mv text/AA/wiki_00 "$OUTPUT_DIR/zhwiki"
    echo "已移动提取结果到 $OUTPUT_DIR/zhwiki"
fi

# 转换为一行一篇文章的格式
echo "转换为单行格式..."
$PYTHON scripts/one_line.py "$OUTPUT_DIR" "$MIN_LENGTH"

echo "=== 提取完成 ==="
ls -lh "$OUTPUT_DIR"
ls -lh scripts/*.opencc.txt 2>/dev/null || true
