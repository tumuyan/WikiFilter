#!/bin/bash
# 完整处理流程脚本
# 用法: ./run-all.sh [版本号] [词库来源] [分片数]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 参数
VERSION="${1:-}"
DICT_SOURCE="${2:-wiki}"
SPLIT_COUNT="${3:-1}"

echo "=========================================="
echo "维基百科数据处理完整流程"
echo "=========================================="
echo "版本: ${VERSION:-自动计算}"
echo "词库来源: $DICT_SOURCE"
echo "分片数量: $SPLIT_COUNT"
echo "=========================================="

cd "$PROJECT_ROOT"

# 1. 设置环境
echo -e "\n[1/8] 设置环境..."
"$SCRIPT_DIR/setup-env.sh"

# 2. 构建 WikiFilter
echo -e "\n[2/8] 构建 WikiFilter..."
"$SCRIPT_DIR/build-wikifilter.sh"

# 3. 下载维基百科 dump 或从 release 解压
echo -e "\n[3/8] 检查/下载维基数据..."

# 检查是否已通过 download-release.sh 下载并解压
if [ -f "extracted/zhwiki" ]; then
    echo "已存在 extracted/zhwiki，跳过下载和提取步骤"
    echo "如需重新下载，请先删除 extracted 目录"
else
    # 查找已下载的文件
    RELEASE_FILE=$(ls zhwiki-*-extracted.tar.gz 2>/dev/null | head -1)
    DUMP_FILE=$(ls zhwiki-*-pages-articles-multistream.xml.bz2 2>/dev/null | head -1)
    XML_FILE=$(ls zhwiki-*-pages-articles-multistream.xml 2>/dev/null | head -1)
    
    if [ -n "$RELEASE_FILE" ]; then
        # 从 release 文件解压（已提取的内容）
        echo "发现 release 文件: $RELEASE_FILE"
        echo "解压中..."
        mkdir -p extracted
        tar -xzf "$RELEASE_FILE"
        mv zhwiki extracted/ 2>/dev/null || true
        echo "解压完成"
    elif [ -n "$XML_FILE" ]; then
        # 已有解压的 XML 文件，只需提取
        echo "发现已解压的 XML 文件: $XML_FILE"
        echo -e "\n[4/8] 提取维基百科内容..."
        mv "$XML_FILE" zhwiki.xml 2>/dev/null || true
        "$SCRIPT_DIR/extract-wiki.sh" "zhwiki.xml" "extracted" 100
    elif [ -n "$DUMP_FILE" ]; then
        # 有压缩的 dump 文件，解压并提取
        echo "发现已下载的 dump 文件: $DUMP_FILE"
        echo -e "\n[4/8] 提取维基百科内容..."
        7z x "$DUMP_FILE"
        mv "${DUMP_FILE%.bz2}" zhwiki.xml 2>/dev/null || true
        "$SCRIPT_DIR/extract-wiki.sh" "zhwiki.xml" "extracted" 100
    else
        # 下载维基百科 dump
        "$SCRIPT_DIR/download-wiki.sh" "$VERSION" "$PROJECT_ROOT"
        
        # 4. 提取维基百科内容
        echo -e "\n[4/8] 提取维基百科内容..."
        "$SCRIPT_DIR/extract-wiki.sh" "zhwiki.xml" "extracted" 100
    fi
fi

# 验证 extracted 文件是否存在
if [ ! -f "extracted/zhwiki" ]; then
    echo "错误: extracted/zhwiki 不存在"
    echo "请先运行 download-release.sh 或 download-wiki.sh"
    exit 1
fi

# 检测 Python 命令
if command -v python3 &> /dev/null; then
    PYTHON="python3"
elif command -v python &> /dev/null; then
    PYTHON="python"
else
    echo "错误: 未找到 Python"
    exit 1
fi

# 生成单行格式的 zhwiki.txt（如果不存在）
if [ ! -f "extracted/zhwiki.txt" ]; then
    echo -e "\n[4/8] 转换为单行格式..."
    $PYTHON scripts/one_line.py extracted 100
    echo "生成 extracted/zhwiki.txt"
else
    echo -e "\n[4/8] 单行格式文件已存在，跳过转换"
fi

# 切分文件
echo -e "\n准备切分文件..."
mkdir -p text/AA
rm -f text/AA/*.txt 2>/dev/null || true
$PYTHON scripts/split_file.py extracted/zhwiki.txt text/AA/ "$SPLIT_COUNT"
echo "切分完成，分片数: $SPLIT_COUNT"
ls -lh text/AA/*.txt 2>/dev/null || true

# 5. 下载词库
echo -e "\n[5/8] 下载词库..."
"$SCRIPT_DIR/download-dict.sh" "$DICT_SOURCE" "$VERSION" "" "dict.txt"

# 6. 处理词库
echo -e "\n[6/8] 处理词库..."
"$SCRIPT_DIR/process-dict.sh" "dict.txt"

# 7. 过滤维基百科内容
echo -e "\n[7/8] 过滤维基百科内容..."
"$SCRIPT_DIR/filter-wiki.sh" "dict.txt" "text/AA" "text/AA" "$SPLIT_COUNT"

# 8. 合并结果
echo -e "\n[8/8] 合并结果..."
"$SCRIPT_DIR/merge-result.sh" "text/AA" 0

echo -e "\n=========================================="
echo "处理完成!"
echo "=========================================="
echo "结果文件:"
ls -lh text/AA/*.txt 2>/dev/null || true
ls -lh text/AA/*.csv 2>/dev/null || true
