#!/bin/bash
# 合并结果并生成最终输出

set -e

# 参数
INPUT_DIR="${1:-text/AA}"
OUTPUT_FILTER="${2:-0}"
OPENCC_CONFIG="${3:-scripts/a2s2.json}"

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

echo "=== 合并结果 ==="
echo "输入目录: $INPUT_DIR"
echo "输出过滤阈值: $OUTPUT_FILTER"
echo "OpenCC 配置: $OPENCC_CONFIG"

cd "$PROJECT_ROOT"

# 移动 opencc 配置文件
if ls "$INPUT_DIR"/*.opencc.txt 1>/dev/null 2>&1; then
    mv "$INPUT_DIR"/*.opencc.txt scripts/ 2>/dev/null || true
fi

# 删除原始文件
rm -f "$INPUT_DIR"/*.raw.txt 2>/dev/null || true

# 第一次合并
echo "第一次合并 (filted.csv)..."
$PYTHON scripts/merge_csv.py "$INPUT_DIR" merge "$OUTPUT_FILTER" filted.csv

# 删除中间文件
rm -f "$INPUT_DIR"/*.txt.filted.csv 2>/dev/null || true

# OpenCC 转换
if [ -f "$INPUT_DIR/merge.csv" ] && [ -f "$OPENCC_CONFIG" ]; then
    echo "OpenCC 转换..."
    opencc -i "$INPUT_DIR/merge.csv" -o "$INPUT_DIR/merge.chs.csv" -c "$OPENCC_CONFIG"
    
    # 第二次合并
    echo "第二次合并 (chs.csv)..."
    $PYTHON scripts/merge_csv.py "$INPUT_DIR" filted.chs 8 merge.chs.csv
fi

echo "=== 合并完成 ==="
echo "输出文件:"
ls -lh "$INPUT_DIR"/*.csv 2>/dev/null || true
ls -lh "$INPUT_DIR"/*.txt 2>/dev/null || true
ls -lh "$INPUT_DIR"/*.chs.* 2>/dev/null || true
ls -lh "$INPUT_DIR"/*.merge.* 2>/dev/null || true
