#!/usr/bin/env bash

NAME="${1:-wiki}"
DESC="${2:-维基百科词库}"


python3 ../optimize_dict.py  "${NAME}.yaml" --fix

# 为优化后的词库添加文件头
OUTPUT_NAME="pinyin_simp_${NAME}"
HEADER="""# Rime dictionary
# encoding: utf-8
#
# ${OUTPUT_NAME}.dict.yaml
#
# ${DESC}
#
---
name: ${OUTPUT_NAME}
version: \"$(date +%Y%m%d)\"
sort: by_weight
use_preset_vocabulary: false
...
"""

# 将文件头写入文件，再拼接词库内容
echo "$HEADER" > "${OUTPUT_NAME}.dict.yaml"
cat "${NAME}_optimized.yaml" >> "${OUTPUT_NAME}.dict.yaml"

echo "finish dump ${OUTPUT_NAME}.dict.yaml"
